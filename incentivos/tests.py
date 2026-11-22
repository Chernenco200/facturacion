from datetime import date, datetime, time
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase

from core.models import Producto
from incentivos import services as S
from incentivos.models import Asistencia, MovimientoPuntos, Tarea, TipoTarea, Trabajador, Turno
from incentivos.tiempo import LIMA


def a_las(fecha, h, m=0):
    import datetime as dt

    return mock.patch("django.utils.timezone.now",
                      lambda: datetime.combine(fecha, time(h, m)).replace(tzinfo=LIMA).astimezone(dt.timezone.utc))


class PuntosICTests(TestCase):
    def setUp(self):
        self.u = User.objects.create_user("ana", password="x")
        self.t = Trabajador.objects.create(usuario=self.u, nombre_vendedor="Ana")
        self.lunes = date(2026, 12, 7)
        Turno.objects.create(usuario=self.u, fecha=self.lunes, hora_entrada=time(9), hora_salida=time(18))

    def test_meta_diaria(self):
        self.assertEqual(S.meta_del_dia(self.lunes, 0), Decimal("50"))
        self.assertEqual(S.meta_del_dia(self.lunes, 3), Decimal("29"))
        self.assertEqual(S.meta_del_dia(self.lunes, 10), Decimal("10"))
        self.assertEqual(S.meta_del_dia(date(2026, 12, 12), 1), Decimal("13"))  # sábado

    def test_pago(self):
        p = date(2026, 12, 1)
        self.assertEqual(S.pago(Decimal(1050), Decimal(900), p), Decimal("285.00"))  # ejemplo de la ficha
        self.assertEqual(S.pago(Decimal(800), Decimal(900), p), Decimal("200.00"))
        self.assertEqual(S.pago(Decimal(3000), Decimal(900), p), Decimal("450.00"))  # tope

    def test_tardanzas(self):
        with a_las(self.lunes, 9, 0):
            ok, _ = S.marcar(self.u, "entrada")
        self.assertTrue(ok)
        self.assertEqual(MovimientoPuntos.suma(usuario=self.u), Decimal("1"))
        martes = date(2026, 12, 8)
        Turno.objects.create(usuario=self.u, fecha=martes, hora_entrada=time(9), hora_salida=time(18))
        with a_las(martes, 9, 20):
            S.marcar(self.u, "entrada")
        a = Asistencia.objects.get(usuario=self.u, fecha=martes)
        self.assertEqual(a.minutos_tarde, 20)
        self.assertEqual(MovimientoPuntos.suma(usuario=self.u, fecha=martes), Decimal("-5"))

    def test_falta_y_justificacion(self):
        with a_las(self.lunes, 23, 0):
            S.procesar_dia(self.lunes)
        self.assertEqual(MovimientoPuntos.suma(usuario=self.u), Decimal("-10"))
        a = Asistencia.objects.get(usuario=self.u, fecha=self.lunes)
        S.justificar(a, "Descanso médico", None)
        self.assertEqual(MovimientoPuntos.suma(usuario=self.u), Decimal("0"))

    def test_reversion_al_borrar_fotos(self):
        p = Producto.objects.create(cod="T1", tipo="Monturas oftálmicas", stock=1, imagenF="a.jpg",
                                    imagenD="b.jpg", imagenL="c.jpg")
        tarea = Tarea.objects.create(tipo=TipoTarea.objects.get(codigo="FOTO"), producto=p, asignada_a=self.u,
                                     estado=Tarea.EN_CURSO)
        with a_las(self.lunes, 10):
            tarea.inicio = S.ahora()
            tarea.save()
            S.acreditar(tarea, Decimal("1"), "fotos")
        self.assertEqual(MovimientoPuntos.suma(usuario=self.u), Decimal("1"))
        p.imagenD = ""
        with self.captureOnCommitCallbacks(execute=True):
            p.save()
        self.assertEqual(Tarea.objects.get(pk=tarea.pk).estado, Tarea.ELIMINADA)
        self.assertEqual(MovimientoPuntos.suma(usuario=self.u), Decimal("0"))

    def test_una_sola_tarea_en_curso(self):
        tipo = TipoTarea.objects.get(codigo="INV")
        Tarea.objects.create(tipo=tipo, exhibidor="A")
        Tarea.objects.create(tipo=tipo, exhibidor="B")
        with mock.patch.object(S, "generar_tareas", return_value={}):
            t1, nueva1 = S.siguiente_tarea(self.u)
            t2, nueva2 = S.siguiente_tarea(self.u)
        self.assertTrue(nueva1)
        self.assertFalse(nueva2)
        self.assertEqual(t1.pk, t2.pk)

    def test_fecha_prometida(self):
        class T:
            fecha_entrega = "16/11/2026"
            hora_entrega = "4:00 p. m."
        self.assertEqual(S.fecha_prometida(T()).hour, 16)


class BonoVentasTests(TestCase):
    def setUp(self):
        from core.models import DetalleTicketVenta, TicketVenta

        self.trabs = []
        for n in ("Ana", "Karen", "Xiomara", "Hellen"):
            u = User.objects.create_user(n.lower(), password="x")
            self.trabs.append(Trabajador.objects.create(usuario=u, nombre_vendedor=n))
        self.periodo = date(2026, 12, 1)
        num = 5000

        def ticket(vendedor, total, lineas):
            nonlocal num
            num += 1
            t = TicketVenta.objects.create(numero=num, vendedor=vendedor, fecha_emision=date(2026, 12, 5),
                                           total=Decimal(total), a_cuenta=Decimal(total), saldo=0)
            for desc, cant, precio in lineas:
                DetalleTicketVenta.objects.create(ticket_numero=t, descripcion=desc, cantidad=cant,
                                                  precio=Decimal(precio))
        # Ana: par multifocal digital fotocromático (2 líneas, una por ojo) = 3 + 2 = 5 puntos
        ticket("Ana", 30000, [("Multifocal Digital: Resina UV + AR + Fotomatic (OD)", 1, 500),
                              ("Multifocal Digital: Resina UV + AR + Fotomatic (OI)", 1, 500)])
        # Karen: par monofocal fotocromático en una línea (cantidad 2) = 2 puntos
        ticket("Karen", 26000, [("Monofocal: Resina UV + AR + Fotomatic", 2, 150)])

    def test_tramo_2_reparto(self):
        b = S.bono_ventas(self.periodo)
        self.assertEqual(b["venta"], Decimal("56000"))
        self.assertEqual(b["adicional"], Decimal("300"))  # tramo 2
        filas = {f["trabajador"].nombre_vendedor: f for f in b["filas"]}
        self.assertEqual(filas["Ana"]["puntos_venta"], Decimal("5"))
        self.assertEqual(filas["Karen"]["puntos_venta"], Decimal("2"))
        self.assertEqual(filas["Xiomara"]["total"], Decimal("250.00"))
        self.assertEqual(filas["Ana"]["adicional"] + filas["Karen"]["adicional"], Decimal("300.00"))
        self.assertEqual(b["total"], Decimal("1300.00"))

    def test_sin_puntos_va_en_partes_iguales(self):
        from core.models import DetalleTicketVenta

        DetalleTicketVenta.objects.all().delete()
        b = S.bono_ventas(self.periodo)
        self.assertTrue(all(f["adicional"] == Decimal("75.00") for f in b["filas"]))

    def test_turnos_rotan_y_descanso(self):
        u = self.trabs[0].usuario
        S.generar_turnos(self.periodo, {u.id: {"lv": "09:00-18:00", "rotar": True, "sabado": True,
                                               "domingos": [date(2026, 12, 6)], "descanso": 2}})
        self.assertFalse(Turno.objects.filter(usuario=u, fecha=date(2026, 12, 2)).exists())  # miércoles libre
        self.assertEqual(Turno.objects.get(usuario=u, fecha=date(2026, 12, 6)).hora_entrada, time(10, 30))
        self.assertEqual(Turno.objects.get(usuario=u, fecha=date(2026, 12, 7)).hora_entrada, time(10))  # rota
