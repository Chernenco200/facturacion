import os
import requests

from django.utils import timezone
from datetime import timedelta
from .models import ConversacionWhatsApp, MensajeWhatsApp

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
#        f"Esperamos que estés disfrutando tus nuevos lentes de Óptica.\n\n"
#        f"Podrías confirmarnos con un like si todo va bien\n\n"
#        
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
        f"2️⃣ En taller de Biselado\n"
        f"3️⃣ Control de calidad\n"
        f"4️⃣ Listo para recoger ✅\n\n"
        f"Puedes consultar el estado de tu ticket escribiendo Menú a este número y seleccionando la opción 2.\n\n"
        f"Óptica IC\n"
        f"Innovación y Calidad"
    )

    if cliente_esta_en_ventana_servicio(cliente.telefono):
        enviado = enviar_whatsapp_texto(cliente.telefono, mensaje)
    else:
        enviado = enviar_whatsapp_template(
            numero=cliente.telefono,
            template_name="agradecimiento",
            parametros=[
                cliente.nombre,
                str(ticket.numero).zfill(6),
            ],
        )

    if enviado:
        MensajeWhatsApp.objects.create(
            numero=cliente.telefono,
            tipo="BOT",
            mensaje=mensaje,
        )

    return enviado

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
        f"Esperamos que estés disfrutando tus nuevos lentes de Óptica IC.\n\n"
        f"Podrías confirmarnos con un like si todo va bien\n\n"
    )

    if cliente_esta_en_ventana_servicio(cliente.telefono):
        enviado = enviar_whatsapp_texto(cliente.telefono, mensaje)
    else:
        enviado = enviar_whatsapp_template(
            numero=cliente.telefono,
            template_name="encuesta_7_dias",
            parametros=[cliente.nombre],
        )

    if enviado:
        MensajeWhatsApp.objects.create(
            numero=cliente.telefono,
            tipo="BOT",
            mensaje=mensaje,
        )

        conversacion, created = ConversacionWhatsApp.objects.get_or_create(
            numero=cliente.telefono,
            defaults={
                "modo": "BOT",
                "estado": "ESPERANDO_ENCUESTA",
            }
        )

        conversacion.modo = "BOT"
        conversacion.estado = "ESPERANDO_ENCUESTA"
        conversacion.save()

    return enviado

def enviar_control_menor_6_meses(orden):
    ticket = orden.ticket
    cliente = ticket.cliente

    if not cliente or not cliente.telefono:
        return False

    mensaje = (
        f"Hola {cliente.nombre} 😊\n\n"
        f"Te recordamos que hoy se cumplen 6 meses desde que adquiriste lentes con nosotros.\n\n"
        f"Puedes escribir 'Cita' para separar una cita de control. "
        f"Recuerda que en menores es recomendable realizar evaluaciones semestrales.\n\n"
        f"Óptica IC\n"
        f"Innovación y Calidad"
    )

    if cliente_esta_en_ventana_servicio(cliente.telefono):
        enviado = enviar_whatsapp_texto(cliente.telefono, mensaje)
    else:
        enviado = enviar_whatsapp_template(
            numero=cliente.telefono,
            template_name="control_6_meses",
            parametros=[cliente.nombre],
        )

    if enviado:
        MensajeWhatsApp.objects.create(
            numero=cliente.telefono,
            tipo="BOT",
            mensaje=mensaje,
        )

    return enviado

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
        enviado = enviar_whatsapp_texto(cliente.telefono, mensaje)
    else:
        enviado = enviar_whatsapp_template(
            numero=cliente.telefono,
            template_name="renovacion_anual",
            parametros=[cliente.nombre],
        )

    if enviado:
        MensajeWhatsApp.objects.create(
            numero=cliente.telefono,
            tipo="BOT",
            mensaje=mensaje,
        )

    return enviado

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
        enviado = enviar_whatsapp_texto(cliente.telefono, mensaje)
    else:
        enviado = enviar_whatsapp_template(
            numero=cliente.telefono,
            template_name="lentes_listos",
            parametros=[
                cliente.nombre,
            ],
        )

    if enviado:
        MensajeWhatsApp.objects.create(
            numero=cliente.telefono,
            tipo="BOT",
            mensaje=mensaje,
        )

    return enviado




def subir_media_whatsapp(archivo):
    access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")

    url = f"https://graph.facebook.com/v20.0/{phone_number_id}/media"

    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    files = {
        "file": (
            archivo.name,
            archivo,
            "application/pdf"
        )
    }

    data = {
        "messaging_product": "whatsapp",
        "type": "application/pdf",
    }

    response = requests.post(
        url,
        headers=headers,
        files=files,
        data=data,
        timeout=30
    )

    print("SUBIR MEDIA STATUS:", response.status_code)
    print("SUBIR MEDIA RESPUESTA:", response.text)

    if response.status_code not in [200, 201]:
        return None

    return response.json().get("id")


def enviar_whatsapp_pdf(numero, media_id, filename="documento.pdf", caption=""):
    access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")

    url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    data = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "document",
        "document": {
            "id": media_id,
            "filename": filename,
        }
    }

    if caption:
        data["document"]["caption"] = caption

    response = requests.post(
        url,
        headers=headers,
        json=data,
        timeout=30
    )

    print("ENVIAR PDF STATUS:", response.status_code)
    print("ENVIAR PDF RESPUESTA:", response.text)

    return response.status_code in [200, 201]


def enviar_whatsapp_texto_y_guardar(numero, mensaje):
    enviado = enviar_whatsapp_texto(numero, mensaje)

    if enviado:
        MensajeWhatsApp.objects.create(
            numero=numero,
            tipo="SALIENTE",
            mensaje=mensaje,
        )

    return enviado    


def nombre_corto_cliente(nombre_completo):
    if not nombre_completo:
        return "Cliente"

    partes = nombre_completo.strip().split()

    if len(partes) >= 3:
        primer_apellido = partes[0].capitalize()
        primer_nombre = partes[2].capitalize()
        return f"{primer_nombre} {primer_apellido}"

    return nombre_completo.title()