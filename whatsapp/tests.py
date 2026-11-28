"""
Pruebas de privacidad de números en la bandeja y el chat de WhatsApp.

Ejecutar:
    python manage.py test whatsapp
"""

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp
from whatsapp.privacidad import enmascarar_numero


AJUSTES_PRUEBA = dict(
    SECURE_SSL_REDIRECT=False,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)

NUMERO = "51987654321"
ENMASCARADO = "+51 987 *** 321"


def crear_usuario(username, rol, superuser=False):
    user = User.objects.create_user(username, password="Clave-segura-123")
    user.is_superuser = superuser
    user.is_staff = superuser
    user.save()
    user.profile.rol = rol
    user.profile.save()
    return user


class EnmascararNumeroTests(TestCase):

    def test_formatos(self):
        self.assertEqual(enmascarar_numero("51987654321"), "+51 987 *** 321")
        self.assertEqual(enmascarar_numero("+51 987-654-321"), "+51 987 *** 321")
        self.assertEqual(enmascarar_numero("987654321"), "987 *** 321")
        self.assertEqual(enmascarar_numero("12345"), "**345")
        self.assertEqual(enmascarar_numero(""), "")
        self.assertEqual(enmascarar_numero(None), "")


@override_settings(**AJUSTES_PRUEBA)
class PrivacidadBandejaTests(TestCase):

    def setUp(self):
        self.conversacion = ConversacionWhatsApp.objects.create(numero=NUMERO)
        MensajeWhatsApp.objects.create(
            numero=NUMERO, tipo="ENTRANTE", mensaje="Hola, quiero una cita"
        )

    def entrar(self, rol, **extra):
        self.client.force_login(crear_usuario(f"u_{rol.lower()}", rol, **extra))

    def test_vendedor_no_ve_numero_en_bandeja(self):
        self.entrar("VENDEDOR")
        r = self.client.get("/whatsapp/bandeja/")

        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, NUMERO)
        self.assertNotContains(r, "987654321")
        self.assertContains(r, ENMASCARADO)
        self.assertContains(r, f"/whatsapp/chat/{self.conversacion.id}/")

    def test_vendedor_no_ve_numero_en_chat(self):
        self.entrar("VENDEDOR")
        r = self.client.get(f"/whatsapp/chat/{self.conversacion.id}/")

        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, NUMERO)
        self.assertContains(r, ENMASCARADO)
        self.assertContains(r, "Hola, quiero una cita")

    def test_supervisor_y_admin_ven_numero_completo(self):
        for rol in ("SUPERVISOR", "ADMIN"):
            with self.subTest(rol=rol):
                self.entrar(rol)
                r = self.client.get("/whatsapp/bandeja/")
                self.assertContains(r, NUMERO)

    def test_superusuario_ve_numero_completo(self):
        self.entrar("VENDEDOR", superuser=True)
        r = self.client.get(f"/whatsapp/chat/{self.conversacion.id}/")
        self.assertContains(r, NUMERO)

    def test_url_con_numero_ya_no_funciona(self):
        self.entrar("VENDEDOR")
        r = self.client.get(f"/whatsapp/chat/{NUMERO}/")
        self.assertEqual(r.status_code, 404)

    def test_cambiar_modo_por_enlace_no_hace_nada(self):
        self.entrar("VENDEDOR")
        r = self.client.get(f"/whatsapp/chat/{self.conversacion.id}/modo/")

        self.assertEqual(r.status_code, 405)
        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.modo, "BOT")

    def test_cambiar_modo_por_formulario(self):
        self.entrar("VENDEDOR")
        self.client.post(f"/whatsapp/chat/{self.conversacion.id}/modo/")

        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.modo, "HUMANO")



class MejorasBotTests(TestCase):
    def test_numero_se_guarda_normalizado(self):
        from whatsapp.models import MensajeWhatsApp
        m = MensajeWhatsApp.objects.create(numero="987654321", tipo="BOT", mensaje="Tus lentes están listos")
        self.assertEqual(m.numero, "51987654321")

    def test_calificacion(self):
        from whatsapp.views import extraer_calificacion
        self.assertEqual(extraer_calificacion("5"), "5")
        self.assertEqual(extraer_calificacion("5️⃣"), "5")
        self.assertEqual(extraer_calificacion("le pongo un 4"), "4")
        self.assertEqual(extraer_calificacion("⭐⭐⭐"), "3")
        self.assertIsNone(extraer_calificacion("todo bien gracias"))
        self.assertIsNone(extraer_calificacion("entre 3 y 4"))

    def test_palabras_completas(self):
        from whatsapp.views import contiene_palabra
        self.assertFalse(contiene_palabra("todo normal", ["mal"]))
        self.assertTrue(contiene_palabra("veo mal de lejos", ["mal"]))

    def test_mascara_ticket(self):
        from whatsapp.privacidad import enmascarar_para_ticket
        self.assertEqual(enmascarar_para_ticket("959123913"), "95****913")
        self.assertEqual(enmascarar_para_ticket("51959123913"), "95****913")

    def test_encuesta_tardia_se_reconoce(self):
        """Una calificación enviada horas después ya no se pierde como opción del menú."""
        from datetime import timedelta
        from unittest import mock
        from django.utils import timezone
        from whatsapp.models import ConversacionWhatsApp
        from whatsapp import views
        conv = ConversacionWhatsApp.objects.create(numero="51987654321", estado="ESPERANDO_ENCUESTA")
        ConversacionWhatsApp.objects.filter(pk=conv.pk).update(estado_desde=timezone.now() - timedelta(hours=5))
        with mock.patch.object(views, "enviar_whatsapp_texto_y_guardar") as enviar:
            views.responder_mensaje("51987654321", "5")
        self.assertIn("5/5", enviar.call_args[0][1])

    def test_historial_incluye_mensajes_sin_51(self):
        from unittest import mock
        from whatsapp.models import MensajeWhatsApp
        from whatsapp import ai
        MensajeWhatsApp.objects.bulk_create([  # bulk_create no normaliza: simula datos antiguos
            MensajeWhatsApp(numero="987654321", tipo="BOT", mensaje="Tus lentes del ticket 2545 ya están listos"),
        ])
        MensajeWhatsApp.objects.create(numero="51987654321", tipo="ENTRANTE", mensaje="ok voy mañana")
        respuesta = mock.Mock()
        respuesta.choices = [mock.Mock(message=mock.Mock(content="¡Te esperamos!"))]
        with mock.patch.object(ai.client.chat.completions, "create", return_value=respuesta) as crear:
            ai.responder_con_openai("51987654321", "ok voy mañana")
        enviados = crear.call_args.kwargs["messages"]
        self.assertTrue(any("ya están listos" in (m["content"] or "") for m in enviados))
