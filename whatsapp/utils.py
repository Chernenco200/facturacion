import os
import requests

from django.utils import timezone
from datetime import timedelta
from .models import ConversacionWhatsApp, MensajeWhatsApp 

from django.conf import settings


import traceback
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from core.models import Cliente, ReactivacionWhatsApp, TicketVenta

from whatsapp.models import ConversacionWhatsApp, MensajeWhatsApp

import logging
logger = logging.getLogger(__name__)

from decimal import Decimal
from django.db.models import Sum

def normalizar_numero(numero):
    numero = str(numero).strip()
    numero = numero.replace("+", "").replace(" ", "").replace("-", "")

    # Si accidentalmente viene como 5151...
    while numero.startswith("5151") and len(numero) > 11:
        numero = numero[2:]

    # Si viene como 9 dígitos peruano
    if len(numero) == 9 and numero.startswith("9"):
        numero = "51" + numero

    # Validación final
    if not (numero.startswith("51") and len(numero) == 11):
        raise ValueError(f"Número WhatsApp inválido: {numero}")

    return numero

def enviar_whatsapp_texto(numero, mensaje):
    access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")

    # Guardamos el número tal como llega a la función
    numero_original = numero

    try:
        numero = normalizar_numero(numero)
    except ValueError as e:
        print("ERROR NÚMERO:", e)
        return False

    print("===================================")
    print("ENVIANDO MENSAJE WHATSAPP")
    print("Número original:", numero_original)
    print("Número normalizado:", numero)
    print("Mensaje:", mensaje)
    print("===================================")

    if not numero:
        print("ERROR: número vacío")
        return False

    # Validación adicional
    if not (numero.startswith("51") and len(numero) == 11):
        print(f"ERROR: número inválido -> {numero}")
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

    # Esto muestra exactamente el JSON que se envía a Meta
    print("JSON ENVIADO A META:", data)

    response = requests.post(url, headers=headers, json=data)

    print("WHATSAPP STATUS:", response.status_code)
    print("WHATSAPP RESPUESTA:", response.text)

    return response.status_code in [200, 201]


def enviar_whatsapp_template(numero, template_name, parametros):
    access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")

    try:
        numero = normalizar_numero(numero)
    except ValueError as e:
        print("ERROR NÚMERO TEMPLATE:", e)
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

    print("TEMPLATE:", template_name)
    print("NUMERO TEMPLATE:", numero)
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



def cliente_esta_en_ventana_servicio(numero):
    try:
        numero = normalizar_numero(numero)
    except ValueError:
        return False

    numero_sin_51 = numero[2:] if numero.startswith("51") else numero
    hace_24h = timezone.now() - timedelta(hours=24)

    return MensajeWhatsApp.objects.filter(
        numero__in=[numero, numero_sin_51],
        tipo="ENTRANTE",
        creado__gte=hace_24h
    ).exists()

def enviar_agradecimiento_ticket(ticket):
    cliente = ticket.cliente

    if not cliente or not cliente.telefono:
        print("Cliente sin teléfono. No se envía WhatsApp.")
        return False

    numero = normalizar_numero(cliente.telefono)

    mensaje = (
        f"Hola {cliente.nombre} 😊\n\n"
        f"Gracias por tu compra en Óptica IC.\n\n"
        f"Tu N° de ticket para que puedas hacer seguimiento es: {ticket.numero}\n\n"
        f"Tu pedido pasará por estas etapas:\n"
        f"1️⃣ En laboratorio\n"
        f"2️⃣ En taller de Biselado\n"
        f"3️⃣ Control de calidad\n"
        f"4️⃣ Listo para recoger ✅\n\n"
        f"Puedes consultar el estado de tu ticket escribiendo Menú a este número y seleccionando la opción 2.\n\n"
        f"Óptica IC\n"
        f"Innovación y Calidad"
    )

    if cliente_esta_en_ventana_servicio(numero):
        enviado = enviar_whatsapp_texto(numero, mensaje)
    else:
        enviado = enviar_whatsapp_template(
            numero=numero,
            template_name="agradecimiento",
            parametros=[
                cliente.nombre,
                str(ticket.numero).zfill(6),
            ],
        )

    if enviado:
        MensajeWhatsApp.objects.create(
            numero=numero,
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

    tipo_archivo = archivo.content_type or ""

    tipos_permitidos = [
        "application/pdf",
        "image/jpeg",
        "image/png",
    ]

    if tipo_archivo not in tipos_permitidos:
        print("TIPO DE ARCHIVO NO PERMITIDO:", tipo_archivo)
        return None

    archivo.seek(0)

    files = {
        "file": (
            archivo.name,
            archivo,
            tipo_archivo,
        )
    }

    data = {
        "messaging_product": "whatsapp",
        "type": tipo_archivo,
    }

    response = requests.post(
        url,
        headers=headers,
        files=files,
        data=data,
        timeout=30
    )

    print("TIPO DE ARCHIVO:", tipo_archivo)
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

def enviar_whatsapp_imagen(numero, media_id, caption=""):
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
        "type": "image",
        "image": {
            "id": media_id,
        }
    }

    if caption:
        data["image"]["caption"] = caption

    response = requests.post(
        url,
        headers=headers,
        json=data,
        timeout=30
    )

    print("ENVIAR IMAGEN STATUS:", response.status_code)
    print("ENVIAR IMAGEN RESPUESTA:", response.text)

    return response.status_code in [200, 201]


from django.core.files.base import ContentFile
def descargar_media_whatsapp(media_id):
    access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN")

    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    # 1. Obtener la URL temporal del archivo
    url_info = f"https://graph.facebook.com/v20.0/{media_id}"

    response_info = requests.get(
        url_info,
        headers=headers,
        timeout=30
    )

    print("MEDIA INFO STATUS:", response_info.status_code)
    print("MEDIA INFO RESPUESTA:", response_info.text)

    if response_info.status_code != 200:
        return None

    datos_media = response_info.json()
    media_url = datos_media.get("url")
    mime_type = datos_media.get("mime_type", "")

    if not media_url:
        return None

    # 2. Descargar el archivo usando el token
    response_archivo = requests.get(
        media_url,
        headers=headers,
        timeout=60
    )

    print("DESCARGAR MEDIA STATUS:", response_archivo.status_code)

    if response_archivo.status_code != 200:
        return None

    return {
        "contenido": response_archivo.content,
        "mime_type": mime_type,
    }


def enviar_whatsapp_texto_y_guardar(numero, texto):
    try:
        numero = normalizar_numero(numero)
    except ValueError as e:
        print("ERROR NÚMERO:", e)
        return False

    enviado = enviar_whatsapp_texto(numero, texto)

    if enviado:
        MensajeWhatsApp.objects.create(
            numero=numero,
            tipo="SALIENTE",
            mensaje=texto,
        )
        return True

    print("No se guardó el mensaje porque WhatsApp no confirmó envío.")
    return False    


def nombre_corto_cliente(nombre_completo):
    if not nombre_completo:
        return "Cliente"

    partes = nombre_completo.strip().split()

    if len(partes) >= 3:
        primer_apellido = partes[0].capitalize()
        primer_nombre = partes[2].capitalize()
        return f"{primer_nombre} {primer_apellido}"

    return nombre_completo.title()


def enviar_reactivacion(cliente):
    print("=== ENVIAR REACTIVACIÓN ===")
    print("CLIENTE ID:", cliente.id if cliente else None)
    print("CLIENTE:", cliente.nombre if cliente else None)
    print("TELÉFONO:", cliente.telefono if cliente else None)

    # ==========================================================
    # 1. VALIDACIONES
    # ==========================================================
    if not cliente or not cliente.telefono:
        print("Cliente sin teléfono. No se envía WhatsApp.")
        return False

    if getattr(cliente, "excluir_reactivacion", False):
        print("Cliente excluido de reactivaciones.")
        return False

    # ==========================================================
    # 2. NOMBRE CORTO
    # ==========================================================
    nombre = nombre_corto_cliente(cliente.nombre)

    # ==========================================================
    # 3. CALCULAR LA MÁXIMA COMPRA DIARIA
    # ==========================================================
    compras_por_dia = (
        TicketVenta.objects
        .filter(cliente=cliente)
        .values("fecha_emision")
        .annotate(total_dia=Sum("total"))
        .order_by("-total_dia")
    )

    primera_compra = compras_por_dia.first()

    if primera_compra:
        maxima_compra_dia = (
            primera_compra.get("total_dia")
            or Decimal("0.00")
        )
    else:
        maxima_compra_dia = Decimal("0.00")

    print("MÁXIMA COMPRA DIARIA:", maxima_compra_dia)

    # ==========================================================
    # 4. DETERMINAR CATEGORÍA
    # ==========================================================
    if maxima_compra_dia >= Decimal("800"):
        categoria = "BLUE"
    elif maxima_compra_dia >= Decimal("300"):
        categoria = "BLACK"
    elif maxima_compra_dia >= Decimal("150"):
        categoria = "RED"
    elif maxima_compra_dia >= Decimal("100"):
        categoria = "WHITE"
    else:
        categoria = "BROWN"

    print("CATEGORÍA:", categoria)

    # Premium: BLUE y BLACK
    es_premium = categoria in {
        "BLUE",
        "BLACK",
    }

    print("ES PREMIUM:", es_premium)

    # ==========================================================
    # 5. ELEGIR PLANTILLA Y MENSAJE
    # ==========================================================
    if es_premium:
        template_name = "reactivar_cliente_premium"

        mensaje = (
            f"Hola {nombre} 😊\n\n"
            f"Eres uno de nuestros clientes premium de Óptica IC y "
            f"queremos seguir acompañándote en el cuidado de tu salud "
            f"visual.\n\n"
            f"Ha pasado un tiempo desde tu última compra. Queremos "
            f"invitarte a realizar una revisión de tus lentes y medida.\n\n"
            f"Puedes responder este mensaje para recibir más información "
            f"o agendar una cita.\n\n"
            f"Óptica IC\n"
            f"Innovación y Calidad"
        )

    else:
        template_name = "reactivacion_clientes"

        mensaje = (
            f"Hola {nombre} 😊\n\n"
            f"En Óptica IC queremos seguir acompañándote en el cuidado "
            f"de tu salud visual.\n\n"
            f"Ha pasado un tiempo desde tu última compra y queremos "
            f"invitarte a realizar una revisión de tus lentes y medida.\n\n"
            f"Puedes responder este mensaje para recibir más información "
            f"o agendar una cita.\n\n"
            f"Óptica IC\n"
            f"Innovación y Calidad"
        )

    print("PLANTILLA:", template_name)

    # ==========================================================
    # 6. ENVIAR TEXTO O PLANTILLA
    # ==========================================================
    if cliente_esta_en_ventana_servicio(cliente.telefono):
        print("Cliente dentro de la ventana de servicio.")

        enviado = enviar_whatsapp_texto(
            cliente.telefono,
            mensaje,
        )
    else:
        print("Cliente fuera de la ventana de servicio.")

        enviado = enviar_whatsapp_template(
            numero=cliente.telefono,
            template_name=template_name,
            parametros=[nombre],
        )

    # ==========================================================
    # 7. VERIFICAR ENVÍO
    # ==========================================================
    if not enviado:
        print("Meta no confirmó el envío de la reactivación.")
        return False

    print("Meta confirmó el envío.")

    # ==========================================================
    # 8. REGISTRAR MENSAJE EN LA BANDEJA
    # ==========================================================
    MensajeWhatsApp.objects.create(
        numero=cliente.telefono,
        tipo="BOT",
        mensaje=mensaje,
    )

    # ==========================================================
    # 9. CREAR O ACTUALIZAR CONVERSACIÓN
    # ==========================================================
    conversacion, created = (
        ConversacionWhatsApp.objects.get_or_create(
            numero=cliente.telefono,
            defaults={
                "modo": "BOT",
                "estado": "INICIO",
            },
        )
    )

    conversacion.modo = "BOT"
    conversacion.estado = "INICIO"
    conversacion.save()

    # ==========================================================
    # 10. REGISTRAR TRACKING DE REACTIVACIÓN
    # ==========================================================
    ReactivacionWhatsApp.objects.create(
        cliente=cliente,
        categoria=categoria,
        monto_maximo=maxima_compra_dia,
        
    )

    # ==========================================================
    # 11. ACTUALIZAR CLIENTE
    # ==========================================================
    cliente.fecha_ultima_reactivacion = timezone.now()

    cliente.save(
        update_fields=[
            "fecha_ultima_reactivacion",

        ]
    )

    print(
        "Reactivación enviada correctamente.",
        "Categoría:",
        categoria,
        "Plantilla:",
        template_name,
    )

    return True