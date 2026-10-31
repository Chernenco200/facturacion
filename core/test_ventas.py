"""
Pruebas de registro de ventas: aviso de venta duplicada y hora de entrega.

Ejecutar:
    python manage.py test core.test_ventas
"""

import json
from datetime import time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from core.horas import leer_hora, normalizar_hora_entrega
from core.models import Cliente, OrdenTrabajo, ReciboCorrelativo, TicketVenta


class HoraEntregaTests(SimpleTestCase):

    def test_formatos_validos(self):
        casos = {
            "5:30p. m.": "5:30 p. m.",
            "5:30 p. m.": "5:30 p. m.",
            "5:30pm": "5:30 p. m.",
            "5:30 PM": "5:30 p. m.",
            "5:30 p.m.": "5:30 p. m.",
            "5.30 pm": "5:30 p. m.",
            "5 pm": "5:00 p. m.",
            "17:30": "5:30 p. m.",
            "09:15 a.m.": "9:15 a. m.",
            "12:00 p. m.": "12:00 p. m.",
            "12:15 a. m.": "12:15 a. m.",
            "": "",
            "   ": "",
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(normalizar_hora_entrega(texto), esperado)

    def test_formatos_invalidos(self):
        for texto in ["5:30", "13:00 pm", "25:00", "abc", "5:75 pm", "0 pm"]:
            with self.subTest(texto=texto):
                self.assertIsNone(normalizar_hora_entrega(texto))

    def test_tickets_antiguos_en_24_horas_se_siguen_leyendo(self):
        self.assertEqual(leer_hora("10:00", estricto=False), time(10, 0))
        self.assertIsNone(leer_hora("10:00"))


class HoraEnOrdenTests(TestCase):

    def orden_con_hora(self, hora):
        ticket = TicketVenta.objects.create(
            numero=1, vendedor="X", total=Decimal("10"), a_cuenta=Decimal("10"),
            saldo=Decimal("0"), fecha_entrega="31/10/2026", hora_entrega=hora,
        )
        return OrdenTrabajo.objects.create(ticket=ticket)

    def test_hora_sin_espacio_ahora_se_reconoce(self):
        due = self.orden_con_hora("5:30p. m.").due_datetime()
        self.assertEqual((due.hour, due.minute), (17, 30))

    def test_hora_en_24_horas_de_tickets_antiguos(self):
        due = self.orden_con_hora("10:00").due_datetime()
        self.assertEqual((due.hour, due.minute), (10, 0))

    def test_hora_invalida(self):
        self.assertIsNone(self.orden_con_hora("tarde").due_datetime())


@override_settings(SECURE_SSL_REDIRECT=False)
@patch("core.views.enviar_agradecimiento_ticket", return_value=True)
class VentaDuplicadaTests(TestCase):

    def setUp(self):
        user = User.objects.create_user("vendedor", password="x")
        user.profile.rol = "VENDEDOR"
        user.profile.save()
        self.client.force_login(user)

        self.cliente = Cliente.objects.create(nombre="MELCHORA MENDOZA", telefono="935762834")
        self.hoy = timezone.localdate().strftime("%d/%m/%Y")

    def datos(self, **cambios):
        datos = {
            "cliente": "MELCHORA MENDOZA",
            "vendedor": "Xiomara",
            "fecha_emision": self.hoy,
            "total": "180.00",
            "a_cuenta": "100.00",
            "saldo": "80.00",
            "detalles": [
                {"cod": "", "descripcion": "MONTURA X", "cantidad": 1, "precio": 100},
                {"cod": "", "descripcion": "LUNAS Y", "cantidad": 1, "precio": 80},
            ],
            "fecha_entrega": self.hoy,
            "hora_entrega": "5:30 p. m.",
            "puntos_ic": 9,
            "medio_pago": "EFECTIVO",
        }
        datos.update(cambios)
        return datos

    def enviar(self, datos):
        return self.client.post(
            "/guardar-ticket/", data=json.dumps(datos), content_type="application/json",
        )

    def correlativo(self):
        return ReciboCorrelativo.objects.get(pk=1).numero_actual

    def test_segunda_venta_igual_pide_confirmacion(self, _):
        r1 = self.enviar(self.datos())
        self.assertEqual(r1.status_code, 200)
        numero = r1.json()["numero"]

        r2 = self.enviar(self.datos())

        self.assertEqual(r2.status_code, 409)
        self.assertTrue(r2.json()["duplicado"])
        self.assertEqual(r2.json()["numero_existente"], numero)
        self.assertEqual(TicketVenta.objects.count(), 1)
        self.assertEqual(self.correlativo(), numero)  # no se gastó un número

    def test_si_confirma_se_crea_otra_venta(self, _):
        self.enviar(self.datos())
        r = self.enviar(self.datos(confirmar_duplicado=True))

        self.assertEqual(r.status_code, 200)
        self.assertEqual(TicketVenta.objects.count(), 2)

    def test_otro_total_no_es_duplicado(self, _):
        self.enviar(self.datos())
        r = self.enviar(self.datos(total="250.00", detalles=[
            {"cod": "", "descripcion": "MONTURA X", "cantidad": 1, "precio": 250},
        ]))
        self.assertEqual(r.status_code, 200)

    def test_mismo_total_otros_productos_no_es_duplicado(self, _):
        self.enviar(self.datos())
        r = self.enviar(self.datos(detalles=[
            {"cod": "", "descripcion": "LENTES DE CONTACTO", "cantidad": 2, "precio": 180},
        ]))
        self.assertEqual(r.status_code, 200)

    def test_otro_cliente_no_es_duplicado(self, _):
        Cliente.objects.create(nombre="OTRA PERSONA", telefono="999888777")
        self.enviar(self.datos())
        r = self.enviar(self.datos(cliente="OTRA PERSONA"))
        self.assertEqual(r.status_code, 200)

    def test_otro_dia_no_es_duplicado(self, _):
        self.enviar(self.datos())
        ayer = (timezone.localdate() - timedelta(days=1)).strftime("%d/%m/%Y")
        r = self.enviar(self.datos(fecha_emision=ayer))
        self.assertEqual(r.status_code, 200)

    def test_venta_sin_cliente_no_se_bloquea(self, _):
        self.enviar(self.datos(cliente=""))
        r = self.enviar(self.datos(cliente=""))
        self.assertEqual(r.status_code, 200)

    def test_hora_sin_espacio_se_guarda_normalizada(self, _):
        r = self.enviar(self.datos(hora_entrega="5:30p. m."))
        ticket = TicketVenta.objects.get(numero=r.json()["numero"])
        self.assertEqual(ticket.hora_entrega, "5:30 p. m.")

    def test_hora_invalida_no_registra_la_venta(self, _):
        r = self.enviar(self.datos(hora_entrega="tarde"))

        self.assertEqual(r.status_code, 400)
        self.assertFalse(TicketVenta.objects.exists())
        self.assertIn("Hora de entrega inválida", r.json()["error"])

    def test_sin_hora_de_entrega_se_permite(self, _):
        r = self.enviar(self.datos(hora_entrega="", fecha_entrega=""))
        self.assertEqual(r.status_code, 200)
