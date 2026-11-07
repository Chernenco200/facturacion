"""
Pruebas de la toma de inventario con lectora y del ajuste mensual.

Ejecutar:
    python manage.py test core.test_inventario
"""

import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from contabilidad.models import AsientoContable, CuentaContable, PeriodoContable
from core import inventario as inv
from core.kardex import recalcular_kardex_producto
from core.models import (
    AjusteInventario,
    Compra,
    DetalleCompra,
    DetalleTicketVenta,
    KardexMovimiento,
    LecturaInventario,
    Producto,
    Proveedor,
    TicketVenta,
    TomaInventario,
)


def _usuario(nombre, rol):
    u = User.objects.create_user(nombre, password="x")
    u.profile.rol = rol
    u.profile.save()
    return u


class BaseInventario(TestCase):

    def setUp(self):
        self.admin = _usuario("admin1", "ADMIN")
        self.vendedor = _usuario("vende1", "VENDEDOR")
        self.ahora = timezone.localtime()
        hoy = self.ahora.date()

        proveedor = Proveedor.objects.create(ruc="20123456789", nombre="Prov")
        self.compra = Compra.objects.create(
            proveedor=proveedor, fecha=hoy - timedelta(days=10),
            tipo_comprobante="BO", serie="B001", numero="1",
        )
        self.a = self._montura("1001", compra=1)
        self.b = self._montura("1002", compra=1)
        self.c = self._montura("1003", compra=2)
        self.d = self._montura("1004", compra=0, precio_compra=Decimal("40"))
        self.e = self._montura("1005", compra=1)
        self.accesorio = Producto.objects.create(
            cod="9001", tipo="Accesorios", descripcion="Estuche", precio_venta=10,
        )

        fin = (hoy.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        PeriodoContable.objects.create(
            anio=hoy.year, mes=hoy.month, fecha_inicio=hoy.replace(day=1), fecha_fin=fin,
        )
        for codigo, tipo, nat in [
            ("20101", "ACTIVO", "DEUDORA"),
            ("65901", "GASTO", "DEUDORA"),
            ("75901", "INGRESO", "ACREEDORA"),
            ("50101", "PATRIMONIO", "ACREEDORA"),
        ]:
            CuentaContable.objects.get_or_create(
                codigo=codigo, defaults=dict(nombre=codigo, tipo=tipo, naturaleza=nat),
            )
        self.numero_ticket = 0

    def _montura(self, cod, compra=1, precio_compra=None):
        p = Producto.objects.create(
            cod=cod, tipo="Monturas oftálmicas", descripcion=f"Montura {cod}",
            precio_venta=Decimal("120"), precio_compra=precio_compra,
        )
        if compra:
            DetalleCompra.objects.create(
                compra=self.compra, producto=p, cantidad=compra,
                precio_compra=Decimal("50"), precio_venta=Decimal("120"),
                subtotal=Decimal("50") * compra,
            )
        # Las vistas recalculan el kardex al guardar (las señales no están activas).
        recalcular_kardex_producto(p)
        p.refresh_from_db()
        return p

    def _vender(self, producto, momento):
        self.numero_ticket += 1
        t = TicketVenta.objects.create(
            numero=self.numero_ticket, vendedor="X", total=Decimal("120"),
            a_cuenta=Decimal("120"), saldo=Decimal("0"),
        )
        local = timezone.localtime(momento)
        TicketVenta.objects.filter(pk=t.pk).update(
            fecha_emision=local.date(), hora_emision=local.time().replace(microsecond=0),
        )
        t.refresh_from_db()
        DetalleTicketVenta.objects.create(
            ticket_numero=t, producto=producto, descripcion="Montura",
            cantidad=1, precio=Decimal("120"),
        )
        recalcular_kardex_producto(producto)
        producto.refresh_from_db()
        return t

    def _escanear(self, toma, producto_o_codigo, momento):
        codigo = getattr(producto_o_codigo, "cod", producto_o_codigo)
        lectura, _, _ = inv.registrar_lectura(toma, codigo, self.vendedor)
        if lectura:
            LecturaInventario.objects.filter(pk=lectura.pk).update(fecha_hora=momento)
        return lectura

    def _escenario(self):
        """
        A: escaneada y vendida después -> coincide.
        B: vendida antes de escanear, no se escanea -> no aparece.
        C: 2 en sistema, 1 escaneada -> faltante 1.
        D: 0 en sistema, 1 escaneada -> sobrante 1.
        E: 1 en sistema, no escaneada -> faltante 1.
        """
        t0 = timezone.now() - timedelta(hours=2)
        toma = inv.abrir_toma(self.admin)
        TomaInventario.objects.filter(pk=toma.pk).update(fecha_inicio=t0)
        toma.refresh_from_db()

        self._vender(self.b, t0 + timedelta(minutes=5))
        self._escanear(toma, self.a, t0 + timedelta(minutes=10))
        self._escanear(toma, self.c, t0 + timedelta(minutes=30))
        self._escanear(toma, self.d, t0 + timedelta(minutes=40))
        self._escanear(toma, "999999", t0 + timedelta(minutes=45))
        self._vender(self.a, t0 + timedelta(minutes=60))
        return toma


class CalculoYCierreTests(BaseInventario):

    def test_lecturas_validan_alcance_y_codigos(self):
        toma = inv.abrir_toma(self.admin)
        lectura, producto, error = inv.registrar_lectura(toma, "9001", self.vendedor)
        self.assertIsNone(lectura)
        self.assertIn("no es montura", error)

        lectura, producto, error = inv.registrar_lectura(toma, "XYZ", self.vendedor)
        self.assertIsNotNone(lectura)
        self.assertIsNone(producto)
        self.assertIn("no existe", error)

        lectura, producto, error = inv.registrar_lectura(toma, " 1001 ", self.vendedor)
        self.assertEqual(producto, self.a)
        self.assertIsNone(error)

    def test_solo_una_toma_en_conteo(self):
        inv.abrir_toma(self.admin)
        with self.assertRaises(ValidationError):
            inv.abrir_toma(self.admin)

    def test_cierre_con_tienda_abierta(self):
        toma = self._escenario()
        inv.cerrar_toma(toma, self.admin)
        toma.refresh_from_db()
        self.assertEqual(toma.estado, TomaInventario.Estado.CERRADA)

        det = {d.producto.cod: d for d in toma.detalles.select_related("producto")}
        self.assertNotIn("1002", det)  # vendida antes de escanear
        self.assertEqual(det["1001"].vendido_tras_lectura, 1)
        self.assertEqual(det["1001"].diferencia, 0)
        self.assertEqual(det["1003"].diferencia, -1)
        self.assertEqual(det["1004"].diferencia, 1)
        self.assertEqual(det["1004"].costo_unitario, Decimal("40"))
        self.assertEqual(det["1005"].diferencia, -1)

        res = inv.resumen(list(toma.detalles.all()))
        self.assertEqual(res["unid_faltantes"], 2)
        self.assertEqual(res["valor_faltante"], Decimal("100.00"))
        self.assertEqual(res["unid_sobrantes"], 1)
        self.assertEqual(inv.no_reconocidos(toma)[0]["codigo_leido"], "999999")

    def test_deshacer_y_recontar(self):
        toma = inv.abrir_toma(self.admin)
        inv.registrar_lectura(toma, "1003", self.vendedor)
        inv.registrar_lectura(toma, "1003", self.vendedor)
        inv.deshacer_ultima_lectura(toma, self.vendedor)
        self.assertEqual(inv.contado_de(toma, self.c), 1)
        inv.recontar_producto(toma, self.c)
        self.assertEqual(inv.contado_de(toma, self.c), 0)

    def test_cierre_corrige_stock_desfasado_del_kardex(self):
        Producto.objects.filter(pk=self.e.pk).update(stock=5)  # editado a mano
        toma = inv.abrir_toma(self.admin)
        inv.registrar_lectura(toma, "1005", self.vendedor)
        inv.cerrar_toma(toma, self.admin)
        det = toma.detalles.get(producto=self.e)
        self.assertEqual(det.stock_sistema, 1)
        self.assertEqual(det.diferencia, 0)

    def test_reabrir(self):
        toma = self._escenario()
        inv.cerrar_toma(toma, self.admin)
        inv.reabrir_toma(toma)
        toma.refresh_from_db()
        self.assertEqual(toma.estado, TomaInventario.Estado.EN_CONTEO)
        self.assertFalse(toma.detalles.exists())


class AjusteTests(BaseInventario):

    def _aprobar(self):
        toma = self._escenario()
        inv.cerrar_toma(toma, self.admin)
        return toma, inv.aprobar_ajuste(toma, self.admin)

    def test_ajuste_deja_stock_igual_al_conteo(self):
        toma, ajuste = self._aprobar()
        for p, esperado in [(self.a, 0), (self.c, 1), (self.d, 1), (self.e, 0)]:
            p.refresh_from_db()
            self.assertEqual(p.stock, esperado, p.cod)
        toma.refresh_from_db()
        self.assertEqual(toma.estado, TomaInventario.Estado.AJUSTADA)
        self.assertEqual(
            KardexMovimiento.objects.filter(ajuste=ajuste).count(), 3
        )

    def test_ajuste_sobrevive_al_recalculo(self):
        _, ajuste = self._aprobar()
        self._vender(self.c, timezone.now() + timedelta(minutes=1))
        self.c.refresh_from_db()
        self.assertEqual(self.c.stock, 0)
        recalcular_kardex_producto(self.c)
        self.assertTrue(KardexMovimiento.objects.filter(producto=self.c, ajuste=ajuste).exists())

    def test_ajuste_no_cambia_el_costo_promedio(self):
        self._aprobar()
        ultimo = KardexMovimiento.objects.filter(producto=self.c).last()
        self.assertEqual(ultimo.costo_promedio, Decimal("50"))
        self.assertEqual(ultimo.costo_unitario, Decimal("50"))

    def test_asiento_contable(self):
        _, ajuste = self._aprobar()
        asiento = inv.asiento_de(ajuste)
        self.assertEqual(asiento.estado, AsientoContable.Estado.CONTABILIZADO)
        lineas = {(d.cuenta.codigo, d.debe, d.haber) for d in asiento.detalles.all()}
        self.assertEqual(lineas, {
            ("65901", Decimal("100.00"), Decimal("0.00")),
            ("20101", Decimal("0.00"), Decimal("100.00")),
            ("20101", Decimal("40.00"), Decimal("0.00")),
            ("75901", Decimal("0.00"), Decimal("40.00")),
        })

    def test_sin_periodo_no_se_guarda_nada(self):
        PeriodoContable.objects.all().delete()
        toma = self._escenario()
        inv.cerrar_toma(toma, self.admin)
        with self.assertRaises(ValidationError):
            inv.aprobar_ajuste(toma, self.admin)
        self.assertFalse(AjusteInventario.objects.exists())
        self.c.refresh_from_db()
        self.assertEqual(self.c.stock, 2)
        toma.refresh_from_db()
        self.assertEqual(toma.estado, TomaInventario.Estado.CERRADA)

    def test_anular_ajuste(self):
        toma, ajuste = self._aprobar()
        inv.anular_ajuste(ajuste, self.admin)
        self.c.refresh_from_db()
        self.d.refresh_from_db()
        self.assertEqual(self.c.stock, 2)
        self.assertEqual(self.d.stock, 0)
        self.assertEqual(
            AsientoContable.objects.get(origen=inv.ORIGEN_ASIENTO, origen_id=ajuste.pk).estado,
            AsientoContable.Estado.ANULADO,
        )
        toma.refresh_from_db()
        self.assertEqual(toma.estado, TomaInventario.Estado.CERRADA)

    def test_faltantes_recurrentes(self):
        for _ in range(2):
            toma = inv.abrir_toma(self.admin)
            inv.registrar_lectura(toma, "1003", self.vendedor)
            inv.cerrar_toma(toma, self.admin)  # cerradas, aún sin ajustar
        cods = [f["producto__cod"] for f in inv.faltantes_recurrentes()]
        self.assertIn("1005", cods)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class VistasInventarioTests(BaseInventario):

    def test_vendedor_escanea_pero_no_cierra(self):
        toma = inv.abrir_toma(self.admin)
        self.client.force_login(self.vendedor)

        r = self.client.post(
            reverse("api_toma_lectura", args=[toma.pk]),
            data=json.dumps({"codigo": "1001"}), content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d["ok"])
        self.assertEqual(d["contado_producto"], 1)

        r = self.client.post(
            reverse("api_toma_lectura", args=[toma.pk]),
            data=json.dumps({"codigo": "NOEXISTE"}), content_type="application/json",
        )
        self.assertEqual(r.json()["nivel"], "aviso")

        self.assertEqual(self.client.get(reverse("toma_escanear", args=[toma.pk])).status_code, 200)
        self.assertEqual(self.client.post(reverse("toma_cerrar", args=[toma.pk])).status_code, 403)

    def test_flujo_completo_por_pantallas(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("toma_nueva"))
        toma = TomaInventario.objects.get()
        self.client.post(
            reverse("api_toma_lectura", args=[toma.pk]),
            data=json.dumps({"codigo": "1003"}), content_type="application/json",
        )
        self.assertEqual(self.client.get(reverse("tomas_lista")).status_code, 200)
        self.assertEqual(self.client.get(reverse("toma_avance", args=[toma.pk])).status_code, 200)
        self.client.post(reverse("toma_cerrar", args=[toma.pk]))
        r = self.client.get(reverse("toma_reporte", args=[toma.pk]))
        self.assertContains(r, "Aprobar ajuste")

        self.client.post(reverse("toma_aprobar_ajuste", args=[toma.pk]), {
            f"motivo_{self.e.pk}": "DANADO",
        })
        toma.refresh_from_db()
        self.assertEqual(toma.estado, TomaInventario.Estado.AJUSTADA)
        detalle = AjusteInventario.objects.get().detalles.get(producto=self.e)
        self.assertEqual(detalle.motivo, "DANADO")

        r = self.client.get(reverse("toma_exportar_excel", args=[toma.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get(reverse("faltantes_recurrentes")).status_code, 200)
        self.assertEqual(self.client.get(reverse("kardex_detalle", args=[self.e.pk])).status_code, 200)


class TomaInicialTests(BaseInventario):

    def _aprobar_inicial(self):
        t0 = timezone.now() - timedelta(hours=2)
        toma = inv.abrir_toma(self.admin, es_inicial=True)
        TomaInventario.objects.filter(pk=toma.pk).update(fecha_inicio=t0)
        toma.refresh_from_db()
        self._escanear(toma, self.c, t0 + timedelta(minutes=30))
        self._escanear(toma, self.d, t0 + timedelta(minutes=40))
        inv.cerrar_toma(toma, self.admin)
        return toma, inv.aprobar_ajuste(toma, self.admin)

    def test_asiento_de_apertura_contra_capital_al_dia_1(self):
        toma, ajuste = self._aprobar_inicial()
        primero = inv.inicio_de_mes(toma.fecha_inicio)
        self.assertEqual(ajuste.fecha, primero)

        asiento = inv.asiento_de(ajuste)
        self.assertEqual(asiento.tipo, AsientoContable.TipoAsiento.APERTURA)
        self.assertEqual(asiento.fecha, timezone.localtime(primero).date())
        lineas = {(d.cuenta.codigo, d.debe, d.haber) for d in asiento.detalles.all()}
        # D sobrante 1 x 40; faltantes: C 1 x 50, B 1 x 50, E 1 x 50 (A tampoco se escaneó)
        self.assertEqual(lineas, {
            ("20101", Decimal("40.00"), Decimal("0.00")),
            ("50101", Decimal("0.00"), Decimal("40.00")),
            ("50101", Decimal("200.00"), Decimal("0.00")),
            ("20101", Decimal("0.00"), Decimal("200.00")),
        })
        cuentas = {d.cuenta.codigo for d in asiento.detalles.all()}
        self.assertFalse(cuentas & {"65901", "75901"})

    def test_stock_final_igual_al_conteo_aunque_se_feche_el_dia_1(self):
        self._aprobar_inicial()
        for p, esperado in [(self.c, 1), (self.d, 1), (self.a, 0), (self.e, 0)]:
            p.refresh_from_db()
            self.assertEqual(p.stock, esperado, p.cod)

    def test_inicial_solo_antes_del_primer_ajuste(self):
        self._aprobar_inicial()
        self.assertFalse(inv.puede_ser_inicial())
        with self.assertRaises(ValidationError):
            inv.abrir_toma(self.admin, es_inicial=True)


class SenalKardexTests(BaseInventario):

    def test_compra_recalcula_kardex_sola(self):
        p = Producto.objects.create(cod="7777", tipo="Monturas Solares")
        DetalleCompra.objects.create(
            compra=self.compra, producto=p, cantidad=3,
            precio_compra=Decimal("10"), precio_venta=Decimal("30"), subtotal=Decimal("30"),
        )
        p.refresh_from_db()
        self.assertEqual(p.stock, 3)
        self.assertEqual(KardexMovimiento.objects.filter(producto=p).count(), 1)

    def test_no_altera_el_total_con_descuento(self):
        t = TicketVenta.objects.create(
            numero=900, vendedor="X", total=Decimal("100"),  # 120 con descuento
            a_cuenta=Decimal("100"), saldo=Decimal("0"),
        )
        DetalleTicketVenta.objects.create(
            ticket_numero=t, producto=self.a, descripcion="Montura",
            cantidad=1, precio=Decimal("120"),
        )
        t.refresh_from_db()
        self.a.refresh_from_db()
        self.assertEqual(t.total, Decimal("100"))
        self.assertEqual(self.a.stock, 0)


class RecalculoPostergadoTests(BaseInventario):

    def test_carga_masiva_recalcula_una_vez_al_final(self):
        from unittest.mock import patch
        from core import signals

        p = Producto.objects.create(cod="8888", tipo="Monturas Solares")
        with patch.object(
            signals, "recalcular_kardex_producto",
            wraps=signals.recalcular_kardex_producto,
        ) as espia:
            with signals.recalculo_kardex_postergado():
                for _ in range(5):
                    DetalleCompra.objects.create(
                        compra=self.compra, producto=p, cantidad=1,
                        precio_compra=Decimal("10"), precio_venta=Decimal("30"),
                        subtotal=Decimal("10"),
                    )
                p.refresh_from_db()
                self.assertEqual(p.stock, 0)  # todavía no se recalcula
            self.assertEqual(espia.call_count, 1)
        p.refresh_from_db()
        self.assertEqual(p.stock, 5)

    def test_si_falla_no_recalcula(self):
        from core import signals

        p = Producto.objects.create(cod="8889", tipo="Monturas Solares")
        with self.assertRaises(RuntimeError):
            with signals.recalculo_kardex_postergado():
                DetalleCompra.objects.create(
                    compra=self.compra, producto=p, cantidad=2,
                    precio_compra=Decimal("10"), precio_venta=Decimal("30"),
                    subtotal=Decimal("20"),
                )
                raise RuntimeError("error en la carga")
        self.assertFalse(KardexMovimiento.objects.filter(producto=p).exists())
        # Fuera del bloque, el recálculo vuelve a ser inmediato.
        DetalleCompra.objects.create(
            compra=self.compra, producto=p, cantidad=1,
            precio_compra=Decimal("10"), precio_venta=Decimal("30"),
            subtotal=Decimal("10"),
        )
        p.refresh_from_db()
        self.assertEqual(p.stock, 3)
