"""
Pruebas del seguimiento comercial por WhatsApp.

Ejecutar:
    python manage.py test core.test_seguimiento_whatsapp

No envían mensajes reales: las llamadas a Meta se simulan.
"""

from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Cliente, OrdenTrabajo, ReactivacionWhatsApp, TicketVenta
from core.seguimiento import (
    categoria_por_monto,
    clientes_reactivacion_lista,
    clientes_reactivacion_qs,
    ordenes_renovacion,
)
from whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp
from whatsapp.utils import enviar_reactivacion, enviar_renovacion_anual


TEMPLATE = "whatsapp.utils.enviar_whatsapp_template"
TEXTO = "whatsapp.utils.enviar_whatsapp_texto"


class BaseSeguimiento(TestCase):

    def setUp(self):
        self.hoy = timezone.localdate()
        self._numero = 0
        self._telefono = 900000000

    def meses_atras(self, meses, dias=0):
        return self.hoy - relativedelta(months=meses) - timedelta(days=dias)

    def cliente(self, nombre="PEREZ LOPEZ JUAN", edad=30, telefono="auto", **extra):
        if telefono == "auto":
            self._telefono += 1
            telefono = str(self._telefono)

        return Cliente.objects.create(
            nombre=nombre,
            telefono=telefono,
            Edad=edad,
            **extra,
        )

    def compra(self, cliente, fecha, total="200.00", orden=True, estado="ENTREGADO"):
        self._numero += 1

        ticket = TicketVenta.objects.create(
            numero=self._numero,
            cliente=cliente,
            vendedor="Prueba",
            fecha_emision=fecha,
            total=Decimal(total),
            a_cuenta=Decimal(total),
            saldo=Decimal("0.00"),
        )

        if not orden:
            return ticket, None

        entrega = timezone.make_aware(datetime.combine(fecha + timedelta(days=3), time(12, 0)))

        ot = OrdenTrabajo.objects.create(
            ticket=ticket,
            estado=estado,
            ts_entregado=entrega if estado == "ENTREGADO" else None,
        )

        return ticket, ot

    def ids_renovacion(self):
        return set(ordenes_renovacion(self.hoy).values_list("ticket__cliente_id", flat=True))

    def ids_reactivacion(self):
        return set(clientes_reactivacion_qs(self.hoy).values_list("id", flat=True))


# ==================================================================
# REGLAS DE LOS LISTADOS
# ==================================================================

class ReglasListadosTests(BaseSeguimiento):

    def test_11_meses_no_aparece_en_ninguna(self):
        c = self.cliente()
        self.compra(c, self.meses_atras(11))

        self.assertNotIn(c.id, self.ids_renovacion())
        self.assertNotIn(c.id, self.ids_reactivacion())

    def test_exactamente_12_meses_aparece_en_renovacion(self):
        c = self.cliente()
        self.compra(c, self.meses_atras(12))

        self.assertIn(c.id, self.ids_renovacion())
        self.assertNotIn(c.id, self.ids_reactivacion())

    def test_17_meses_aparece_en_renovacion(self):
        c = self.cliente()
        self.compra(c, self.meses_atras(17, dias=20))

        self.assertIn(c.id, self.ids_renovacion())
        self.assertNotIn(c.id, self.ids_reactivacion())

    def test_exactamente_18_meses_pasa_a_reactivacion(self):
        c = self.cliente()
        self.compra(c, self.meses_atras(18))

        self.assertNotIn(c.id, self.ids_renovacion())
        self.assertIn(c.id, self.ids_reactivacion())

    def test_30_meses_aparece_en_reactivacion(self):
        c = self.cliente()
        self.compra(c, self.meses_atras(30))

        self.assertIn(c.id, self.ids_reactivacion())

    def test_compra_reciente_anula_orden_antigua(self):
        c = self.cliente()
        self.compra(c, self.meses_atras(16))
        self.compra(c, self.meses_atras(2))

        self.assertNotIn(c.id, self.ids_renovacion())
        self.assertNotIn(c.id, self.ids_reactivacion())

    def test_varias_ordenes_un_solo_registro_con_la_mas_reciente(self):
        c = self.cliente()
        self.compra(c, self.meses_atras(16))
        _, ot_reciente = self.compra(c, self.meses_atras(13))

        filas = list(ordenes_renovacion(self.hoy).filter(ticket__cliente=c))

        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0].id, ot_reciente.id)

    def test_ultima_compra_sin_orden_usa_la_ultima_orden_entregada(self):
        c = self.cliente()
        _, ot = self.compra(c, self.meses_atras(20))
        self.compra(c, self.meses_atras(14), orden=False)  # p. ej. un accesorio

        filas = list(ordenes_renovacion(self.hoy).filter(ticket__cliente=c))

        self.assertEqual([f.id for f in filas], [ot.id])
        self.assertNotIn(c.id, self.ids_reactivacion())

    def test_cliente_sin_orden_entregada_no_aparece_en_renovacion(self):
        c = self.cliente()
        self.compra(c, self.meses_atras(14), estado="LISTO")

        self.assertNotIn(c.id, self.ids_renovacion())

    def test_menor_no_aparece_en_renovacion(self):
        c = self.cliente(edad=15)
        self.compra(c, self.meses_atras(14))

        self.assertNotIn(c.id, self.ids_renovacion())

    def test_cliente_sin_edad_aparece_en_renovacion(self):
        c = self.cliente(edad=None)
        self.compra(c, self.meses_atras(14))

        self.assertIn(c.id, self.ids_renovacion())

    def test_sin_telefono_no_aparece(self):
        c1 = self.cliente(telefono=None)
        c2 = self.cliente(telefono="")
        for c in (c1, c2):
            self.compra(c, self.meses_atras(14))
            self.compra(c, self.meses_atras(14))

        c3 = self.cliente(telefono="")
        self.compra(c3, self.meses_atras(25))

        self.assertFalse({c1.id, c2.id} & self.ids_renovacion())
        self.assertNotIn(c3.id, self.ids_reactivacion())

    def test_renovacion_eliminada_no_aparece(self):
        c = self.cliente()
        _, ot = self.compra(c, self.meses_atras(14))
        ot.renovacion_enviada = True
        ot.save()

        self.assertNotIn(c.id, self.ids_renovacion())

    def test_excluido_no_aparece_en_reactivacion(self):
        c = self.cliente(excluir_reactivacion=True)
        self.compra(c, self.meses_atras(25))

        self.assertNotIn(c.id, self.ids_reactivacion())

    def test_renovacion_reciente_bloquea_reactivacion(self):
        c = self.cliente()
        _, ot = self.compra(c, self.meses_atras(19))
        ot.fecha_ultima_renovacion = self.meses_atras(2)
        ot.save()

        self.assertNotIn(c.id, self.ids_reactivacion())

    def test_renovacion_de_hace_12_meses_ya_no_bloquea(self):
        c = self.cliente()
        _, ot = self.compra(c, self.meses_atras(30))
        ot.fecha_ultima_renovacion = self.meses_atras(12)
        ot.save()

        self.assertIn(c.id, self.ids_reactivacion())

    def test_reactivacion_reciente_bloquea_renovacion(self):
        c = self.cliente(fecha_ultima_reactivacion=self.meses_atras(5))
        self.compra(c, self.meses_atras(14))

        self.assertNotIn(c.id, self.ids_renovacion())

    def test_reactivacion_reciente_bloquea_reactivacion(self):
        c = self.cliente(fecha_ultima_reactivacion=self.meses_atras(11))
        self.compra(c, self.meses_atras(40))

        self.assertNotIn(c.id, self.ids_reactivacion())

    def test_ningun_cliente_en_ambas_listas(self):
        for meses in range(0, 41):
            c = self.cliente(nombre=f"CLIENTE {meses}")
            self.compra(c, self.meses_atras(meses))
            self.compra(c, self.meses_atras(meses) - timedelta(days=200))

        renov = self.ids_renovacion()
        react = self.ids_reactivacion()

        self.assertFalse(renov & react)
        self.assertEqual(len(renov), 6)    # 12, 13, 14, 15, 16, 17 meses
        self.assertEqual(len(react), 23)   # 18 a 40 meses

        filas = list(ordenes_renovacion(self.hoy))
        self.assertEqual(len(filas), len({f.ticket.cliente_id for f in filas}))


class CategoriasTests(BaseSeguimiento):

    def test_umbrales(self):
        casos = [
            ("800", "BLUE"), ("799.99", "BLACK"), ("300", "BLACK"),
            ("299.99", "RED"), ("150", "RED"), ("149.99", "WHITE"),
            ("100", "WHITE"), ("99.99", "BROWN"), ("0", "BROWN"),
        ]
        for monto, esperado in casos:
            self.assertEqual(categoria_por_monto(Decimal(monto)), esperado, monto)

        self.assertEqual(categoria_por_monto(None), "BROWN")

    def test_mayor_compra_suma_el_mismo_dia(self):
        c = self.cliente()
        dia = self.meses_atras(24)
        self.compra(c, dia, total="150.00")
        self.compra(c, dia, total="200.00", orden=False)
        self.compra(c, self.meses_atras(30), total="300.00")

        fila = [x for x in clientes_reactivacion_lista(self.hoy) if x["cliente"].id == c.id][0]

        self.assertEqual(fila["maxima_compra_dia"], Decimal("350.00"))
        self.assertEqual(fila["categoria"], "BLACK")
        self.assertEqual(fila["ultima_compra"], dia)


# ==================================================================
# ENVÍO DE RENOVACIÓN
# ==================================================================

class EnvioRenovacionTests(BaseSeguimiento):

    def setUp(self):
        super().setUp()
        self.c = self.cliente(nombre="GARCIA RUIZ ANA", telefono="987654321")
        _, self.ot = self.compra(self.c, self.meses_atras(14))

    @patch(TEXTO)
    @patch(TEMPLATE, return_value="wamid.RENOV1")
    def test_envio_exitoso_fuera_de_ventana(self, m_template, m_texto):
        resultado = enviar_renovacion_anual(self.ot)

        self.assertTrue(resultado)
        m_texto.assert_not_called()
        m_template.assert_called_once_with(
            numero="51987654321",
            template_name="renovacion_anual",
            parametros=["GARCIA RUIZ ANA"],
            devolver_id=True,
        )

        self.ot.refresh_from_db()
        self.assertTrue(self.ot.renovacion_enviada)
        self.assertEqual(self.ot.fecha_ultima_renovacion, self.hoy)

        msg = MensajeWhatsApp.objects.get(wa_message_id="wamid.RENOV1")
        self.assertEqual(msg.tipo, "SALIENTE")
        self.assertEqual(msg.estado, "ENVIADO")
        self.assertEqual(msg.numero, "51987654321")
        self.assertEqual(msg.nombre, "GARCIA RUIZ ANA")

        self.assertTrue(ConversacionWhatsApp.objects.filter(numero="51987654321").exists())
        self.assertNotIn(self.c.id, self.ids_renovacion())

    @patch(TEMPLATE)
    @patch(TEXTO, return_value="wamid.TXT1")
    def test_dentro_de_ventana_envia_texto(self, m_texto, m_template):
        MensajeWhatsApp.objects.create(numero="51987654321", tipo="ENTRANTE", mensaje="Hola")

        self.assertTrue(enviar_renovacion_anual(self.ot))

        m_template.assert_not_called()
        args, kwargs = m_texto.call_args
        self.assertEqual(args[0], "51987654321")
        self.assertTrue(kwargs.get("devolver_id"))
        self.assertTrue(MensajeWhatsApp.objects.filter(wa_message_id="wamid.TXT1", tipo="SALIENTE").exists())

    @patch(TEMPLATE, return_value=None)
    def test_meta_rechaza_libera_la_reserva(self, m_template):
        fecha_antigua = self.meses_atras(30)
        self.ot.fecha_ultima_renovacion = fecha_antigua
        self.ot.save()

        resultado = enviar_renovacion_anual(self.ot)

        self.assertFalse(resultado)
        self.assertIn("no aceptó", resultado.motivo)

        self.ot.refresh_from_db()
        self.assertFalse(self.ot.renovacion_enviada)
        self.assertEqual(self.ot.fecha_ultima_renovacion, fecha_antigua)
        self.assertFalse(MensajeWhatsApp.objects.filter(tipo="SALIENTE").exists())
        self.assertIn(self.c.id, self.ids_renovacion())

    @patch(TEMPLATE, side_effect=RuntimeError("timeout"))
    def test_excepcion_de_red_libera_la_reserva(self, m_template):
        self.assertFalse(enviar_renovacion_anual(self.ot))

        self.ot.refresh_from_db()
        self.assertFalse(self.ot.renovacion_enviada)
        self.assertIsNone(self.ot.fecha_ultima_renovacion)

    @patch(TEMPLATE, return_value="wamid.X")
    def test_segundo_clic_no_reenvia(self, m_template):
        self.assertTrue(enviar_renovacion_anual(self.ot))
        self.assertFalse(enviar_renovacion_anual(self.ot))

        self.assertEqual(m_template.call_count, 1)
        self.assertEqual(MensajeWhatsApp.objects.filter(tipo="SALIENTE").count(), 1)

    @patch(TEMPLATE, return_value="wamid.X")
    def test_no_envia_si_compro_despues(self, m_template):
        self.compra(self.c, self.meses_atras(1))

        resultado = enviar_renovacion_anual(self.ot)

        self.assertFalse(resultado)
        m_template.assert_not_called()

    @patch(TEMPLATE, return_value="wamid.X")
    def test_no_envia_orden_antigua_si_hay_otra_mas_reciente(self, m_template):
        _, ot_nueva = self.compra(self.c, self.meses_atras(13))

        self.assertFalse(enviar_renovacion_anual(self.ot))
        self.assertTrue(enviar_renovacion_anual(ot_nueva))
        self.assertEqual(m_template.call_count, 1)

    @patch(TEMPLATE, return_value="wamid.X")
    def test_conserva_modo_humano(self, m_template):
        ConversacionWhatsApp.objects.create(numero="51987654321", modo="HUMANO", estado="ASESOR")

        self.assertTrue(enviar_renovacion_anual(self.ot))

        conv = ConversacionWhatsApp.objects.get(numero="51987654321")
        self.assertEqual(conv.modo, "HUMANO")
        self.assertEqual(conv.estado, "ASESOR")

    @patch(TEMPLATE, return_value="wamid.X")
    def test_telefono_invalido(self, m_template):
        self.c.telefono = "12345"
        self.c.save()
        self.ot.refresh_from_db()

        self.assertFalse(enviar_renovacion_anual(self.ot))
        m_template.assert_not_called()


# ==================================================================
# ENVÍO DE REACTIVACIÓN
# ==================================================================

class EnvioReactivacionTests(BaseSeguimiento):

    @patch(TEMPLATE, return_value="wamid.REACT1")
    def test_premium(self, m_template):
        c = self.cliente(nombre="TORRES DIAZ LUIS ALBERTO", telefono="51911222333")
        self.compra(c, self.meses_atras(20), total="900.00")

        self.assertTrue(enviar_reactivacion(c))

        m_template.assert_called_once_with(
            numero="51911222333",
            template_name="reactivar_cliente_premium",
            parametros=["Luis Torres"],
            devolver_id=True,
        )

        c.refresh_from_db()
        self.assertEqual(c.fecha_ultima_reactivacion, self.hoy)

        historial = ReactivacionWhatsApp.objects.get(cliente=c)
        self.assertEqual(historial.categoria, "BLUE")
        self.assertEqual(historial.monto_maximo, Decimal("900.00"))

        msg = MensajeWhatsApp.objects.get(wa_message_id="wamid.REACT1")
        self.assertEqual((msg.tipo, msg.estado), ("SALIENTE", "ENVIADO"))
        self.assertNotIn(c.id, self.ids_reactivacion())

    @patch(TEMPLATE, return_value="wamid.REACT2")
    def test_estandar(self, m_template):
        c = self.cliente()
        self.compra(c, self.meses_atras(20), total="120.00")

        self.assertTrue(enviar_reactivacion(c))
        self.assertEqual(m_template.call_args.kwargs["template_name"], "reactivacion_clientes")
        self.assertEqual(ReactivacionWhatsApp.objects.get(cliente=c).categoria, "WHITE")

    @patch(TEMPLATE, return_value=None)
    def test_meta_rechaza_restaura_fecha_anterior(self, m_template):
        anterior = self.meses_atras(24)
        c = self.cliente(fecha_ultima_reactivacion=anterior)
        self.compra(c, self.meses_atras(40))

        resultado = enviar_reactivacion(c)

        self.assertFalse(resultado)
        c.refresh_from_db()
        self.assertEqual(c.fecha_ultima_reactivacion, anterior)
        self.assertFalse(ReactivacionWhatsApp.objects.exists())
        self.assertFalse(MensajeWhatsApp.objects.exists())
        self.assertIn(c.id, self.ids_reactivacion())

    @patch(TEMPLATE, return_value="wamid.X")
    def test_no_envia_antes_de_18_meses(self, m_template):
        c = self.cliente()
        self.compra(c, self.meses_atras(15))

        self.assertFalse(enviar_reactivacion(c))
        m_template.assert_not_called()

    @patch(TEMPLATE, return_value="wamid.X")
    def test_no_envia_si_recibio_renovacion_reciente(self, m_template):
        c = self.cliente()
        _, ot = self.compra(c, self.meses_atras(20))
        ot.fecha_ultima_renovacion = self.meses_atras(3)
        ot.save()

        self.assertFalse(enviar_reactivacion(c))
        m_template.assert_not_called()

    @patch(TEMPLATE, return_value="wamid.X")
    def test_no_envia_a_excluido(self, m_template):
        c = self.cliente(excluir_reactivacion=True)
        self.compra(c, self.meses_atras(20))

        self.assertFalse(enviar_reactivacion(c))
        m_template.assert_not_called()

    @patch(TEMPLATE, return_value="wamid.X")
    def test_segundo_clic_no_reenvia(self, m_template):
        c = self.cliente()
        self.compra(c, self.meses_atras(20))

        self.assertTrue(enviar_reactivacion(c))
        self.assertFalse(enviar_reactivacion(c))
        self.assertEqual(m_template.call_count, 1)
        self.assertEqual(ReactivacionWhatsApp.objects.count(), 1)

    @patch(TEMPLATE, return_value="wamid.X")
    def test_renovacion_y_luego_reactivacion_bloqueada(self, m_template):
        c = self.cliente()
        _, ot = self.compra(c, self.meses_atras(17, dias=25))

        self.assertTrue(enviar_renovacion_anual(ot))

        # Aunque pase a 18+ meses, no recibe reactivación en 12 meses
        ot.ticket.fecha_emision = self.meses_atras(19)
        ot.ticket.save()

        self.assertFalse(enviar_reactivacion(c))
        self.assertEqual(m_template.call_count, 1)


# ==================================================================
# VISTAS (botones de la pantalla)
# ==================================================================

# En pruebas no existe el manifest de collectstatic (Heroku sí lo genera)
# y no se redirige a HTTPS (en producción sí, porque DEBUG está apagado).
@override_settings(SECURE_SSL_REDIRECT=False, STORAGES={
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class VistasSeguimientoTests(BaseSeguimiento):

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user("vendedor", password="clave-123")
        self.user.profile.rol = "VENDEDOR"
        self.user.profile.save()
        self.client.force_login(self.user)

    def test_pantalla_muestra_las_cuatro_listas(self):
        c_renov = self.cliente(nombre="CLIENTE RENOVACION")
        self.compra(c_renov, self.meses_atras(14))

        c_react = self.cliente(nombre="CLIENTE REACTIVACION")
        self.compra(c_react, self.meses_atras(25), total="400.00")

        c_enc = self.cliente(nombre="CLIENTE ENCUESTA")
        _, ot_enc = self.compra(c_enc, self.hoy - timedelta(days=20))
        ot_enc.ts_entregado = timezone.now() - timedelta(days=10)
        ot_enc.save()

        c_men = self.cliente(nombre="CLIENTE MENOR", edad=10)
        _, ot_men = self.compra(c_men, self.meses_atras(8))
        ot_men.ts_entregado = timezone.now() - relativedelta(months=7)
        ot_men.save()

        r = self.client.get(reverse("seguimiento_whatsapp"))

        self.assertEqual(r.status_code, 200)
        for nombre in ["CLIENTE RENOVACION", "CLIENTE REACTIVACION", "CLIENTE ENCUESTA", "CLIENTE MENOR"]:
            self.assertContains(r, nombre)

        self.assertEqual(len(r.context["renovaciones"]), 1)
        self.assertEqual(len(r.context["clientes_reactivacion"]), 1)
        self.assertEqual(r.context["clientes_reactivacion"][0]["categoria"], "BLACK")
        self.assertEqual(len(r.context["encuestas"]), 1)
        self.assertEqual(len(r.context["controles_menores"]), 1)

    def test_rol_taller_no_accede(self):
        self.user.profile.rol = "TALLER"
        self.user.profile.save()

        r = self.client.get(reverse("seguimiento_whatsapp"))
        self.assertEqual(r.status_code, 403)

    def test_eliminar_renovacion_la_quita_de_la_lista(self):
        c = self.cliente()
        _, ot = self.compra(c, self.meses_atras(14))

        r = self.client.post(reverse("eliminar_renovacion_manual", args=[ot.id]), follow=True)

        ot.refresh_from_db()
        self.assertTrue(ot.renovacion_enviada)
        self.assertIsNone(ot.fecha_ultima_renovacion)  # no cuenta como mensaje enviado
        self.assertContains(r, "Renovación eliminada de la lista.")
        self.assertNotIn(c.id, self.ids_renovacion())

    def test_eliminar_por_get_no_hace_nada(self):
        c = self.cliente()
        _, ot = self.compra(c, self.meses_atras(14))

        self.client.get(reverse("eliminar_renovacion_manual", args=[ot.id]))

        ot.refresh_from_db()
        self.assertFalse(ot.renovacion_enviada)

    @patch(TEMPLATE, return_value=None)
    def test_boton_renovacion_si_falla_no_marca(self, m_template):
        c = self.cliente()
        _, ot = self.compra(c, self.meses_atras(14))

        r = self.client.post(reverse("enviar_renovacion_manual", args=[ot.id]), follow=True)

        ot.refresh_from_db()
        self.assertIsNone(ot.fecha_ultima_renovacion)
        self.assertFalse(ot.renovacion_enviada)
        self.assertContains(r, "no aceptó el mensaje")

    @patch(TEMPLATE, return_value="wamid.OK")
    def test_boton_renovacion_exitoso(self, m_template):
        c = self.cliente()
        _, ot = self.compra(c, self.meses_atras(14))

        r = self.client.post(reverse("enviar_renovacion_manual", args=[ot.id]), follow=True)

        ot.refresh_from_db()
        self.assertEqual(ot.fecha_ultima_renovacion, self.hoy)
        self.assertContains(r, "Recordatorio de renovación enviado correctamente.")

    @patch(TEMPLATE, return_value=None)
    def test_boton_control_menor_si_falla_no_marca(self, m_template):
        c = self.cliente(edad=10)
        _, ot = self.compra(c, self.meses_atras(7))

        r = self.client.post(reverse("enviar_control_menor_manual", args=[ot.id]), follow=True)

        ot.refresh_from_db()
        self.assertFalse(ot.control_menor_enviado)
        self.assertIsNone(ot.fecha_ultimo_control_menor)
        self.assertContains(r, "No se pudo enviar el control")

    @patch(TEMPLATE, return_value="wamid.CTRL")
    def test_boton_control_menor_exitoso(self, m_template):
        c = self.cliente(edad=10)
        _, ot = self.compra(c, self.meses_atras(7))

        self.client.post(reverse("enviar_control_menor_manual", args=[ot.id]))

        ot.refresh_from_db()
        self.assertTrue(ot.control_menor_enviado)
        self.assertEqual(ot.fecha_ultimo_control_menor, self.hoy)

    @patch(TEMPLATE, return_value="wamid.ENC")
    def test_boton_encuesta_sin_cambios(self, m_template):
        c = self.cliente()
        _, ot = self.compra(c, self.hoy - timedelta(days=15))

        self.client.post(reverse("enviar_encuesta_manual", args=[ot.id]))

        ot.refresh_from_db()
        self.assertTrue(ot.encuesta_enviada)
        self.assertEqual(m_template.call_args.kwargs["template_name"], "encuesta_7_dias")

    @patch(TEMPLATE, return_value="wamid.R")
    def test_boton_reactivacion_exitoso(self, m_template):
        c = self.cliente()
        self.compra(c, self.meses_atras(25))

        r = self.client.post(reverse("enviar_reactivacion_whatsapp", args=[c.id]), follow=True)

        self.assertContains(r, "Reactivación enviada correctamente.")
        self.assertEqual(ReactivacionWhatsApp.objects.filter(cliente=c).count(), 1)

    @patch(TEMPLATE, return_value="wamid.R")
    def test_reactivacion_por_get_no_envia(self, m_template):
        c = self.cliente()
        self.compra(c, self.meses_atras(25))

        self.client.get(reverse("enviar_reactivacion_whatsapp", args=[c.id]))

        m_template.assert_not_called()

    @patch(TEMPLATE, return_value="wamid.R")
    def test_sin_sesion_no_envia_ni_excluye(self, m_template):
        c = self.cliente()
        self.compra(c, self.meses_atras(25))
        self.client.logout()

        r1 = self.client.post(reverse("enviar_reactivacion_whatsapp", args=[c.id]))
        r2 = self.client.post(reverse("excluir_cliente_reactivacion", args=[c.id]))

        self.assertEqual(r1.status_code, 302)
        self.assertEqual(r2.status_code, 302)
        m_template.assert_not_called()
        c.refresh_from_db()
        self.assertFalse(c.excluir_reactivacion)

    def test_excluir_reactivacion(self):
        c = self.cliente()
        self.compra(c, self.meses_atras(25))

        self.client.post(reverse("excluir_cliente_reactivacion", args=[c.id]))

        c.refresh_from_db()
        self.assertTrue(c.excluir_reactivacion)
        self.assertNotIn(c.id, self.ids_reactivacion())
