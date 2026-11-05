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
