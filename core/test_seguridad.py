"""
Pruebas de permisos y seguridad.

Ejecutar:
    python manage.py test core.test_seguridad

No envían mensajes reales: las llamadas a Meta se simulan.
"""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import CajaDia, Cliente, MovimientoCaja


AJUSTES_PRUEBA = dict(
    SECURE_SSL_REDIRECT=False,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)


def crear_usuario(username, rol, superuser=False, staff=False):
    user = User.objects.create_user(username, password="Clave-segura-123")
    user.is_superuser = superuser
    user.is_staff = staff or superuser
    user.save()
    user.profile.rol = rol
    user.profile.save()
    return user


# Rutas que antes funcionaban sin iniciar sesión
RUTAS_ANTES_ABIERTAS = [
    "/ventas/",
    "/whatsapp/chat/51999999999/",
    "/dashboard/data/",
    "/buscar-codigos/?q=a",
    "/producto-por-codigo/?codigo=a",
    "/productos/buscar-codigo/?q=a",
    "/clientes/buscar-por-nombre/?q=a",
    "/ticket-pdf/?numero=1",
    "/ticket/imprimir/",
    "/receta/1/pdf/",
    "/editar-producto/1/",
    "/clientes/1/medida/1/editar/",
    "/caja/2026-10-01/reporte-pdf/",
]


@override_settings(**AJUSTES_PRUEBA)
class SinSesionTests(TestCase):

    def test_rutas_piden_iniciar_sesion(self):
        for ruta in RUTAS_ANTES_ABIERTAS:
            with self.subTest(ruta=ruta):
                r = self.client.get(ruta)
                self.assertEqual(r.status_code, 302, ruta)
                self.assertIn("/login/", r["Location"], ruta)

    @patch("whatsapp.views.enviar_whatsapp_texto", return_value="wamid.X")
    def test_no_puede_enviar_whatsapp(self, m_envio):
        self.client.post("/whatsapp/chat/51999999999/", {"mensaje": "hola"})
        m_envio.assert_not_called()

    def test_no_puede_borrar_movimientos_de_caja(self):
        caja = CajaDia.objects.create(fecha=timezone.localdate())
        mov = MovimientoCaja.objects.create(caja=caja, tipo="IN", monto=Decimal("50"))

        self.client.post(f"/caja/movimiento/{mov.id}/eliminar/")

        self.assertTrue(MovimientoCaja.objects.filter(id=mov.id).exists())

    def test_no_puede_borrar_medidas(self):
        r = self.client.post("/clientes/1/medida/1/eliminar/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])


@override_settings(**AJUSTES_PRUEBA)
class PermisosPorRolTests(TestCase):

    def entrar(self, rol, **extra):
        user = crear_usuario(f"u_{rol.lower()}", rol, **extra)
        self.client.force_login(user)
        return user

    def test_taller_no_ve_ventas_ni_reporte_de_caja(self):
        self.entrar("TALLER")

        self.assertEqual(self.client.get("/ventas/").status_code, 403)
        self.assertEqual(self.client.get("/caja/2026-10-01/reporte-pdf/").status_code, 403)

    def test_taller_no_quita_clientes_del_seguimiento(self):
        self.entrar("TALLER")
        cliente = Cliente.objects.create(nombre="X", telefono="999111222")

        r = self.client.post(f"/seguimiento-whatsapp/eliminar-renovacion/{cliente.id}/")

        self.assertEqual(r.status_code, 403)
        cliente.refresh_from_db()
        self.assertIsNone(cliente.renovacion_descartada)

    def test_taller_sigue_usando_ordenes_y_dashboard(self):
        self.entrar("TALLER")

        self.assertEqual(self.client.get("/dashboard/data/").status_code, 200)

    def test_vendedor_ve_ventas(self):
        self.entrar("VENDEDOR")
        self.assertEqual(self.client.get("/ventas/").status_code, 200)

    def test_vendedor_no_edita_productos_del_inventario(self):
        self.entrar("VENDEDOR")
        self.assertEqual(self.client.get("/editar-producto/1/").status_code, 403)

    def test_movimiento_se_borra_si_la_caja_esta_abierta(self):
        self.entrar("CAJA")
        caja = CajaDia.objects.create(fecha=timezone.localdate())
        mov = MovimientoCaja.objects.create(caja=caja, tipo="IN", monto=Decimal("50"))

        r = self.client.post(f"/caja/movimiento/{mov.id}/eliminar/")

        self.assertFalse(MovimientoCaja.objects.filter(id=mov.id).exists())
        self.assertIn(caja.fecha.strftime("%Y-%m-%d"), r["Location"])

    def test_movimiento_no_se_borra_si_la_caja_esta_cerrada(self):
        self.entrar("ADMIN")
        caja = CajaDia.objects.create(fecha=timezone.localdate(), cerrada=True)
        mov = MovimientoCaja.objects.create(caja=caja, tipo="IN", monto=Decimal("50"))

        r = self.client.post(f"/caja/movimiento/{mov.id}/eliminar/", follow=True)

        self.assertTrue(MovimientoCaja.objects.filter(id=mov.id).exists())
        self.assertContains(r, "La caja de este día está cerrada")


@override_settings(**AJUSTES_PRUEBA)
class GestionUsuariosTests(TestCase):

    def setUp(self):
        self.superusuario = crear_usuario("jefe", "ADMIN", superuser=True)
        self.admin = crear_usuario("admin1", "ADMIN")
        self.supervisor = crear_usuario("super1", "SUPERVISOR")
        self.vendedor = crear_usuario("vende1", "VENDEDOR")

    def datos_nuevo(self, username, rol):
        return {
            "username": username, "first_name": "", "last_name": "", "email": "",
            "is_active": "on", "password1": "Otra-clave-456",
            "password2": "Otra-clave-456", "rol": rol,
        }

    def reset(self, objetivo):
        return self.client.post(
            f"/accounts/usuarios/{objetivo.id}/reset-password/",
            {"password1": "Hackeada-789", "password2": "Hackeada-789"},
        )

    def test_supervisor_no_crea_admin(self):
        self.client.force_login(self.supervisor)
        self.client.post("/accounts/usuarios/nuevo/", self.datos_nuevo("nuevo_admin", "ADMIN"))
        self.assertFalse(User.objects.filter(username="nuevo_admin").exists())

    def test_supervisor_crea_vendedor(self):
        self.client.force_login(self.supervisor)
        self.client.post("/accounts/usuarios/nuevo/", self.datos_nuevo("nuevo_v", "VENDEDOR"))
        self.assertEqual(User.objects.get(username="nuevo_v").profile.rol, "VENDEDOR")

    def test_supervisor_no_se_asciende_a_admin(self):
        self.client.force_login(self.supervisor)
        self.client.post(
            f"/accounts/usuarios/{self.supervisor.id}/editar/",
            {"first_name": "", "last_name": "", "email": "", "is_active": "on", "rol": "ADMIN"},
        )
        self.supervisor.refresh_from_db()
        self.assertEqual(self.supervisor.profile.rol, "SUPERVISOR")

    def test_supervisor_no_cambia_contrasena_de_superusuario_ni_admin(self):
        self.client.force_login(self.supervisor)

        for objetivo in (self.superusuario, self.admin):
            self.reset(objetivo)
            objetivo.refresh_from_db()
            self.assertTrue(objetivo.check_password("Clave-segura-123"), objetivo.username)

    def test_supervisor_cambia_contrasena_de_vendedor(self):
        self.client.force_login(self.supervisor)
        self.reset(self.vendedor)
        self.vendedor.refresh_from_db()
        self.assertTrue(self.vendedor.check_password("Hackeada-789"))

    def test_admin_no_cambia_contrasena_de_superusuario(self):
        self.client.force_login(self.admin)
        self.reset(self.superusuario)
        self.superusuario.refresh_from_db()
        self.assertTrue(self.superusuario.check_password("Clave-segura-123"))

    def test_superusuario_gestiona_a_todos(self):
        self.client.force_login(self.superusuario)
        self.reset(self.admin)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password("Hackeada-789"))

    def test_supervisor_no_desactiva_admin(self):
        self.client.force_login(self.supervisor)
        self.client.post(f"/accounts/usuarios/{self.admin.id}/toggle/")
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_desactivar_por_enlace_no_hace_nada(self):
        self.client.force_login(self.admin)
        self.client.get(f"/accounts/usuarios/{self.vendedor.id}/toggle/")
        self.vendedor.refresh_from_db()
        self.assertTrue(self.vendedor.is_active)

    def test_desactivar_por_formulario_funciona(self):
        self.client.force_login(self.admin)
        self.client.post(f"/accounts/usuarios/{self.vendedor.id}/toggle/")
        self.vendedor.refresh_from_db()
        self.assertFalse(self.vendedor.is_active)

    def test_lista_muestra_botones_solo_donde_puede(self):
        self.client.force_login(self.supervisor)
        r = self.client.get("/accounts/usuarios/")

        self.assertEqual(r.status_code, 200)
        self.assertContains(r, f"/accounts/usuarios/{self.vendedor.id}/editar/")
        self.assertNotContains(r, f"/accounts/usuarios/{self.superusuario.id}/editar/")
        self.assertNotContains(r, f"/accounts/usuarios/{self.admin.id}/editar/")
