from datetime import date, datetime, time, timedelta
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
        self.assertEqual(a.minutos_tarde, 15)  # tolerancia de 5 min que se descuenta (opción B)
        self.assertEqual(MovimientoPuntos.suma(usuario=self.u, fecha=martes), Decimal("-3"))
        miercoles = date(2026, 12, 9)
        Turno.objects.create(usuario=self.u, fecha=miercoles, hora_entrada=time(9), hora_salida=time(19, 45))
        with a_las(miercoles, 9, 5):
            S.marcar(self.u, "entrada")
        self.assertEqual(MovimientoPuntos.suma(usuario=self.u, fecha=miercoles), Decimal("1"))  # 9:05 a tiempo

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

    def test_turnos_horario_nuevo(self):
        u = self.trabs[0].usuario
        S.generar_turnos(self.periodo, {u.id: {"lunes_a_sabado": True, "descanso": 2,
                                               "domingos": [date(2026, 12, 6), date(2026, 12, 8)]}})
        self.assertFalse(Turno.objects.filter(usuario=u, fecha=date(2026, 12, 2)).exists())  # miércoles libre
        self.assertEqual(Turno.objects.get(usuario=u, fecha=date(2026, 12, 6)).hora_entrada, time(10, 30))
        self.assertEqual(Turno.objects.get(usuario=u, fecha=date(2026, 12, 7)).hora_salida, time(19, 45))
        self.assertEqual(Turno.objects.get(usuario=u, fecha=date(2026, 12, 8)).hora_entrada, time(10, 30))  # feriado
        self.assertFalse(Turno.objects.filter(usuario=u, fecha=date(2026, 12, 9)).exists())  # feriado no marcado
        self.assertFalse(Turno.objects.filter(usuario=u, fecha=date(2026, 12, 13)).exists())  # domingo no marcado


class Version2Tests(TestCase):
    def setUp(self):
        self.u = User.objects.create_user("ana", password="x")
        self.t = Trabajador.objects.create(usuario=self.u, nombre_vendedor="Ana")

    def test_tienda_abierta_y_feriados(self):
        from incentivos.horario import tienda_abierta
        lunes = datetime(2026, 12, 7, 19, 50, tzinfo=LIMA)
        self.assertEqual(tienda_abierta(lunes), (False, "mañana martes a las 10:30 a. m."))  # 8/12 feriado
        self.assertTrue(tienda_abierta(datetime(2026, 12, 8, 11, 0, tzinfo=LIMA))[0])
        self.assertFalse(tienda_abierta(datetime(2026, 12, 8, 9, 30, tzinfo=LIMA))[0])

    def test_acceso_por_horario(self):
        from incentivos.middleware import dentro_de_horario
        self.assertTrue(dentro_de_horario(self.u, datetime(2026, 12, 7, 9, 0, tzinfo=LIMA)))
        self.assertTrue(dentro_de_horario(self.u, datetime(2026, 12, 7, 19, 55, tzinfo=LIMA)))  # margen 15 min
        self.assertFalse(dentro_de_horario(self.u, datetime(2026, 12, 7, 8, 50, tzinfo=LIMA)))
        self.assertFalse(dentro_de_horario(self.u, datetime(2026, 12, 13, 12, 0, tzinfo=LIMA)))  # domingo sin turno
        Turno.objects.create(usuario=self.u, fecha=date(2026, 12, 13), hora_entrada=time(10, 30),
                             hora_salida=time(18))
        self.assertTrue(dentro_de_horario(self.u, datetime(2026, 12, 13, 12, 0, tzinfo=LIMA)))

    def test_middleware_cierra_sesion_fuera_de_horario(self):
        from django.test import Client
        c = Client()
        c.force_login(self.u)
        with a_las(date(2026, 12, 7), 21, 0):
            r = c.get("/incentivos/", secure=True)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login", r["Location"])

    def test_limite_de_devoluciones(self):
        tipo_inv = TipoTarea.objects.get(codigo="INV")
        for i in range(4):
            Tarea.objects.create(tipo=tipo_inv, exhibidor=f"E{i}")
        with mock.patch.object(S, "generar_tareas", return_value={}):
            for i in range(3):
                t, _ = S.siguiente_tarea(self.u)
                ok, _ = S.soltar(t)
                self.assertTrue(ok)
                Tarea.objects.filter(pk=t.pk).update(prioridad=99)
            t, _ = S.siguiente_tarea(self.u)
            ok, msg = S.soltar(t)
        self.assertFalse(ok)
        self.assertEqual(Tarea.objects.get(pk=t.pk).estado, Tarea.EN_CURSO)

    def test_tarea_asignada_vencida_resta(self):
        t = S.asignar_tarea(self.u, "Reel de Ray-Ban", Decimal("5"), date(2026, 12, 10), None)
        with a_las(date(2026, 12, 10), 23, 0):
            S.vencer_tareas_asignadas(date(2026, 12, 10))
        self.assertEqual(Tarea.objects.get(pk=t.pk).estado, Tarea.ELIMINADA)
        self.assertEqual(MovimientoPuntos.suma(usuario=self.u), Decimal("-4"))

    def test_meta_biselador(self):
        self.assertEqual(S.meta_del_dia(date(2026, 12, 7), 1, 5), Decimal("33"))  # 50 - 7 - 2x5

    def test_lista_wa_solo_para_asignado(self):
        otro = User.objects.create_user("karen", password="x")
        Trabajador.objects.create(usuario=otro, nombre_vendedor="Karen")
        Tarea.objects.create(tipo=TipoTarea.objects.get(codigo="WA_LISTA"), fecha_objetivo=S.hoy(), asignada_a=self.u)
        self.assertTrue(S.puede_enviar_lista_wa(self.u))
        self.assertFalse(S.puede_enviar_lista_wa(otro))

    def test_venta_cerrada_por_whatsapp(self):
        from core.models import Cliente, TicketVenta
        from whatsapp.models import MensajeWhatsApp
        cli = Cliente.objects.create(nombre="Juan Pérez", telefono="987654321")
        dia = date(2026, 12, 10)
        with a_las(dia - timedelta(days=3), 11, 0):
            MensajeWhatsApp.objects.create(numero="51987654321", tipo="ENTRANTE", mensaje="¿Precio de multifocal?")
        with a_las(dia - timedelta(days=3), 11, 5):
            MensajeWhatsApp.objects.create(numero="51987654321", tipo="SALIENTE", mensaje="Desde S/ 350",
                                           enviado_por=self.u)
        TicketVenta.objects.create(numero=9001, cliente=cli, vendedor="Karen", fecha_emision=dia,
                                   total=Decimal("450"), a_cuenta=Decimal("450"), saldo=0)
        with a_las(dia, 23, 0):
            self.assertEqual(S.procesar_ventas_whatsapp(dia), 1)
            self.assertEqual(S.procesar_ventas_whatsapp(dia), 0)  # no se repite
        self.assertEqual(MovimientoPuntos.suma(usuario=self.u), Decimal("3"))

    def test_venta_whatsapp_no_cuenta_si_esperaba_pedido(self):
        from core.models import Cliente, TicketVenta
        from whatsapp.models import MensajeWhatsApp
        cli = Cliente.objects.create(nombre="Rosa", telefono="912345678")
        dia = date(2026, 12, 10)
        TicketVenta.objects.create(numero=9000, cliente=cli, vendedor="Ana", fecha_emision=dia - timedelta(days=12),
                                   total=Decimal("300"), a_cuenta=0, saldo=Decimal("300"))
        with a_las(dia - timedelta(days=2), 11, 0):
            MensajeWhatsApp.objects.create(numero="912345678", tipo="ENTRANTE", mensaje="¿Ya están mis lentes?")
        TicketVenta.objects.create(numero=9002, cliente=cli, vendedor="Ana", fecha_emision=dia,
                                   total=Decimal("200"), a_cuenta=Decimal("200"), saldo=0)
        with a_las(dia, 23, 0):
            self.assertEqual(S.procesar_ventas_whatsapp(dia), 0)


class VentaMinimaTests(TestCase):
    def test_requisito_venta_del_mes(self):
        from core.models import TicketVenta
        u = User.objects.create_user("ana", password="x")
        t = Trabajador.objects.create(usuario=u, nombre_vendedor="Ana", venta_minima_mes=Decimal("1000"))
        p = date(2026, 12, 1)
        TicketVenta.objects.create(numero=7001, vendedor="Ana", fecha_emision=date(2026, 12, 3),
                                   total=Decimal("600"), a_cuenta=Decimal("600"), saldo=0)
        r = S.requisitos(t, p, 10, 10, date(2026, 12, 31))
        self.assertFalse(r["venta_vendedor"]["ok"])
        self.assertNotIn("tickets", r)
        TicketVenta.objects.create(numero=7002, vendedor="ana", fecha_emision=date(2026, 12, 4),
                                   total=Decimal("400"), a_cuenta=Decimal("400"), saldo=0)
        self.assertTrue(S.requisitos(t, p, 10, 10, date(2026, 12, 31))["venta_vendedor"]["ok"])
        t.venta_minima_mes = None
        self.assertFalse(S.requisitos(t, p, 10, 10, date(2026, 12, 31))["venta_vendedor"]["ok"])  # general 10,000
