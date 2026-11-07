"""
Búsqueda de productos por código (lectora de códigos de barra).

Ejecutar:
    python manage.py test core.test_busqueda_codigo
"""

from decimal import Decimal

from django.test import TestCase, override_settings

from core.models import Producto
from core.test_seguridad import AJUSTES_PRUEBA, crear_usuario


@override_settings(**AJUSTES_PRUEBA)
class BusquedaPorCodigoTests(TestCase):

    def setUp(self):
        # Códigos parecidos: con icontains "100225" también aparece "2100225"
        for cod in ["2100225", "1002250", "100225", "10022", "100014"]:
            Producto.objects.create(
                cod=cod, descripcion=f"Montura {cod}",
                precio_venta=Decimal("150.00"), precio_compra=Decimal("60.00"), stock=3,
            )
        self.client.force_login(crear_usuario("admin_cod", "ADMIN", superuser=True))

    def test_sugerencias_ponen_primero_el_codigo_exacto(self):
        data = self.client.get("/buscar-codigos/?q=100225").json()
        codigos = [d["cod"] for d in data]
        self.assertEqual(codigos[0], "100225")
        self.assertEqual(codigos[1], "1002250")   # empieza con el código
        self.assertIn("2100225", codigos)         # solo lo contiene
        self.assertNotIn("10022", codigos)
        self.assertEqual(data[0]["descripcion"], "Montura 100225")

    def test_detalle_por_codigo_exacto(self):
        data = self.client.get("/producto-por-codigo/?cod=100225").json()
        self.assertEqual(data["cod"], "100225")
        self.assertEqual(data["descripcion"], "Montura 100225")

    def test_detalle_ignora_espacios(self):
        data = self.client.get("/producto-por-codigo/?cod=%20100225%20").json()
        self.assertEqual(data["cod"], "100225")

    def test_detalle_codigo_inexistente(self):
        self.assertEqual(self.client.get("/producto-por-codigo/?cod=999").json(), {})

    def test_compras_encuentra_el_exacto_aunque_haya_muchos_parecidos(self):
        for i in range(20):
            Producto.objects.create(cod=f"9{i:02d}100225", descripcion="otro")
        data = self.client.get("/productos/buscar-codigo/?q=100225").json()
        self.assertEqual(len(data), 10)
        self.assertEqual(data[0]["cod"], "100225")
