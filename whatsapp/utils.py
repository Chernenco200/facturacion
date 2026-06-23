import os
import requests

from django.utils import timezone
from datetime import timedelta
from .models import ConversacionWhatsApp

from django.conf import settings

def normalizar_numero(numero):
    if not numero:
        return None

    numero = str(numero).replace(" ", "").replace("+", "").replace("-", "")

    if len(numero) == 9:
        numero = "51" + numero

    return numero


def enviar_whatsapp_texto(numero, mensaje):
    access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")

    numero = normalizar_numero(numero)

    if not numero:
        print("ERROR: número vacío")
        return False

    url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    data = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {
            "body": mensaje
        }
    }

    response = requests.post(url, headers=headers, json=data)

    print("WHATSAPP STATUS:", response.status_code)
    print("WHATSAPP RESPUESTA:", response.text)

    return response.status_code in [200, 201]

def enviar_whatsapp_template(numero, template_name, parametros):
    access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")

    numero = normalizar_numero(numero)

    if not numero:
        print("ERROR: número vacío")
        return False

    url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    data = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {
                "code": "es_PE"
            },
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": str(p)}
                        for p in parametros
                    ]
                }
            ]
        }
    }

    response = requests.post(url, headers=headers, json=data)

    print("STATUS TEMPLATE:", response.status_code)
    print("RESPUESTA TEMPLATE:", response.text)

    return response.status_code in [200, 201]

def avisar_asesor(mensaje):
    numero_asesor = os.environ.get("NUMERO_ASESOR_WHATSAPP")

    if not numero_asesor:
        print("No existe NUMERO_ASESOR_WHATSAPP")
        return False

    return enviar_whatsapp_texto(numero_asesor, mensaje)








#def enviar_encuesta_7_dias(orden):
#    ticket = orden.ticket
#    cliente = ticket.cliente

#    if not cliente or not cliente.telefono:
#        print("Cliente sin teléfono")
#        return False

#    mensaje = (
#        f"Hola {cliente.nombre} 😊\n\n"
#        f"Queremos saber cómo fue tu experiencia en Óptica IC.\n\n"
#        f"Del 1 al 5, ¿cómo calificarías nuestra atención?\n\n"
#        f"Ticket N° {str(ticket.numero).zfill(6)}\n\n"
#        f"Óptica IC\n"
#        f"Innovación y Calidad"
#    )

#    return enviar_whatsapp_texto(cliente.telefono, mensaje)


#def enviar_control_menor_6_meses(orden):
#    ticket = orden.ticket
#    cliente = ticket.cliente

#    if not cliente or not cliente.telefono:
#        print("Cliente sin teléfono")
#        return False

#    mensaje = (
#        f"Hola {cliente.nombre} 😊\n\n"
#        f"Te recordamos que hoy se cumplen 6 meses desde que adquiriste tus lentes.\n\n"
#        f"Los menores deben realizar controles visuales periódicos según lo que indican los médicos.\n\n"
#        f"Puedes escribirnos para separar una cita de control.\n\n"
#        f"Óptica IC\n"
#        f"Innovación y Calidad"
#    )

#    return enviar_whatsapp_texto(cliente.telefono, mensaje)


#def enviar_renovacion_anual(orden):
#    ticket = orden.ticket
#    cliente = ticket.cliente

#    if not cliente or not cliente.telefono:
#        print("Cliente sin teléfono")
#        return False

#    mensaje = (
#        f"Hola {cliente.nombre} 😊\n\n"
#        f"Ha pasado un año desde tu compra en Óptica IC.\n\n"
#        f"Te recomendamos revisar tu medida y evaluar la renovación de tus lentes.\n\n"
#        f"Puedes escribirnos para separar una cita.\n\n"
#        f"Óptica IC\n"
#        f"Innovación y Calidad"
#    )

#    return enviar_whatsapp_texto(cliente.telefono, mensaje)


def cliente_esta_en_ventana_servicio(telefono):
    telefono = normalizar_numero(telefono)

    try:
        conversacion = ConversacionWhatsApp.objects.get(numero=telefono)
        return conversacion.actualizado >= timezone.now() - timedelta(hours=24)
    except ConversacionWhatsApp.DoesNotExist:
        return False


def enviar_agradecimiento_ticket(ticket):
    cliente = ticket.cliente

    if not cliente.telefono:
        print("Cliente sin teléfono. No se envía WhatsApp.")
        return False

    mensaje = (
        f"Hola {cliente.nombre} 😊\n\n"
        f"Gracias por tu compra en Óptica IC.\n\n"
        f"Tu N° de ticket es: {ticket.numero}\n\n"
        f"Tu pedido pasará por estas etapas:\n"
        f"1️⃣ Pedido enviado al laboratorio\n"
        f"2️⃣ En proceso de laboratorio\n"
        f"3️⃣ En taller de Biselado\n"
        f"4️⃣ Contro de calidad\n"
        f"5️⃣ Listo para recoger ✅\n\n"
        f"Puedes consultar el estado de tu ticket escribiendo Menú a este número y seleccionando la opción 2 :\n"
        f"Óptica IC\n"
        f"Innovación y Calidad"
    )

    if cliente_esta_en_ventana_servicio(cliente.telefono):
        return enviar_whatsapp_texto(cliente.telefono, mensaje)

    return enviar_whatsapp_template(
        numero=cliente.telefono,
        template_name="agradecimiento",
        parametros=[
            cliente.nombre,
            str(ticket.numero).zfill(6),
        ],
    )

def enviar_encuesta_7_dias(orden):
    ticket = orden.ticket
    cliente = ticket.cliente

    print("=== ENVIAR ENCUESTA 7 DIAS ===")
    print("ORDEN:", orden.id)
    print("TICKET:", ticket.numero)
    print("CLIENTE:", cliente.nombre if cliente else None)
    print("TELEFONO:", cliente.telefono if cliente else None)

    if not cliente or not cliente.telefono:
        print("Cliente sin teléfono. No se envía WhatsApp.")
        return False

    mensaje = (
        f"Hola {cliente.nombre} 😊\n\n"
        f"Queremos saber cómo fue tu experiencia en Óptica IC.\n\n"
        f"Del 1 al 5, ¿cómo calificarías nuestra atención?\n\n"
        f"Ticket N° {str(ticket.numero).zfill(6)}\n\n"
        f"Óptica IC\n"
        f"Innovación y Calidad"
    )

    if cliente_esta_en_ventana_servicio(cliente.telefono):
        print("Cliente dentro de ventana 24h. Enviando texto libre.")
        return enviar_whatsapp_texto(cliente.telefono, mensaje)

    print("Cliente fuera de ventana 24h. Enviando plantilla encuesta_7_dias.")

    return enviar_whatsapp_template(
        numero=cliente.telefono,
        template_name="encuesta_7_dias",
        parametros=[
            cliente.nombre,
        ],
    )

def enviar_control_menor_6_meses(orden):
    ticket = orden.ticket
    cliente = ticket.cliente

    if not cliente or not cliente.telefono:
        return False

    mensaje = (
        f"Hola {cliente.nombre} 😊\n\n"
        f"Te recordamos que hoy se cumplen 6 meses desde que adquiriste tus lentes.\n\n"
        f"Los menores deben realizar controles visuales periódicos según lo que indican los médicos.\n\n"
        f"Puedes escribirnos para separar una cita de control.\n\n"
        f"Óptica IC\n"
        f"Innovación y Calidad"
    )

    if cliente_esta_en_ventana_servicio(cliente.telefono):
        return enviar_whatsapp_texto(cliente.telefono, mensaje)

    return enviar_whatsapp_template(
        numero=cliente.telefono,
        template_name="control_6_meses",
        parametros=[
            cliente.nombre,
        ],
    )

def enviar_renovacion_anual(orden):
    ticket = orden.ticket
    cliente = ticket.cliente

    if not cliente or not cliente.telefono:
        return False

    mensaje = (
        f"Hola {cliente.nombre} 😊\n\n"
        f"Ha pasado un año desde tu compra en Óptica IC.\n\n"
        f"Te recomendamos revisar tu medida y evaluar la renovación de tus lentes.\n\n"
        f"Puedes escribirnos para separar una cita.\n\n"
        f"Óptica IC\n"
        f"Innovación y Calidad"
    )

    if cliente_esta_en_ventana_servicio(cliente.telefono):
        return enviar_whatsapp_texto(cliente.telefono, mensaje)

    return enviar_whatsapp_template(
        numero=cliente.telefono,
        template_name="renovacion_anual",
        parametros=[
            cliente.nombre,
        ],
    )

def enviar_aviso_lentes_listos(orden):
    ticket = orden.ticket
    cliente = ticket.cliente

    if not cliente.telefono:
        print("Cliente sin teléfono. No se envía WhatsApp.")
        return False

    mensaje = (
        f"Hola {cliente.nombre} 😊\n\n"
        f"Tus lentes del ticket N° {ticket.numero} ya están listos ✅\n\n"
        f"Puedes acercarte a recogerlos en nuestra tienda.\n\n"
        f"Gracias por confiar en Óptica IC.\n\n"
        f"Óptica IC\n"
        f"Innovación y Calidad"
    )

    if cliente_esta_en_ventana_servicio(cliente.telefono):
        return enviar_whatsapp_texto(cliente.telefono, mensaje)

    return enviar_whatsapp_template(
        numero=cliente.telefono,
        template_name="lentes_listos",
        parametros=[
            cliente.nombre,
        ],
    )
