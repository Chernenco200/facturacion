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

def enviar_whatsapp_texto(numero, mensaje, devolver_id=False):
    access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")

    numero_original = numero

    try:
        numero = normalizar_numero(numero)
    except ValueError as e:
        print("ERROR NÚMERO:", e)
        return None if devolver_id else False

    print("===================================")
    print("ENVIANDO MENSAJE WHATSAPP")
    print("Número original:", numero_original)
    print("Número normalizado:", numero)
    print("Mensaje:", mensaje)
    print("===================================")

    if not numero:
        print("ERROR: número vacío")
        return None if devolver_id else False

    if not (numero.startswith("51") and len(numero) == 11):
        print(f"ERROR: número inválido -> {numero}")
        return None if devolver_id else False

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

    print("JSON ENVIADO A META:", data)

    try:
        response = requests.post(
            url,
            headers=headers,
            json=data,
            timeout=30,
        )

        print("WHATSAPP STATUS:", response.status_code)
        print("WHATSAPP RESPUESTA:", response.text)

        if response.status_code not in [200, 201]:
            return None if devolver_id else False

        respuesta = response.json()

        wa_message_id = (
            respuesta.get("messages", [{}])[0].get("id")
        )

        print("WA_MESSAGE_ID:", wa_message_id)

        if devolver_id:
            return wa_message_id

        return True

    except Exception as e:
        print("ERROR ENVIANDO WHATSAPP:", e)
        return None if devolver_id else False


def enviar_whatsapp_template(
    numero,
    template_name,
    parametros,
    devolver_id=False
):
    access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")

    try:
        numero = normalizar_numero(numero)
    except ValueError as e:
        print("ERROR NÚMERO TEMPLATE:", e)
        return None if devolver_id else False

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
                        {
                            "type": "text",
                            "text": str(p)
                        }
                        for p in parametros
                    ]
                }
            ]
        }
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=data,
            timeout=30,
        )

        print("TEMPLATE:", template_name)
        print("NUMERO TEMPLATE:", numero)
        print("STATUS TEMPLATE:", response.status_code)
        print("RESPUESTA TEMPLATE:", response.text)

        if response.status_code not in [200, 201]:
            return None if devolver_id else False

        respuesta = response.json()

        wa_message_id = (
            respuesta.get("messages", [{}])[0].get("id")
        )

        print("WA_MESSAGE_ID TEMPLATE:", wa_message_id)

        if devolver_id:
            return wa_message_id

        return True

    except Exception as e:
        print("ERROR ENVIANDO TEMPLATE:", e)
        return None if devolver_id else False

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

    print("===================================")
    print("=== ENVIAR AGRADECIMIENTO ===")
    print("TICKET:", ticket.numero if ticket else None)

    cliente = ticket.cliente

    print("CLIENTE:", cliente.nombre if cliente else None)
    print("TELÉFONO:", cliente.telefono if cliente else None)
    print("===================================")

    # ==========================================================
    # 1. VALIDACIONES
    # ==========================================================

    if not cliente or not cliente.telefono:
        print("Cliente sin teléfono. No se envía WhatsApp.")
        return False

    numero = normalizar_numero(cliente.telefono)

    if not numero:
        print("Número de teléfono inválido.")
        return False

    # ==========================================================
    # 2. MENSAJE QUE SE MOSTRARÁ EN LA BANDEJA
    # ==========================================================

    numero_ticket = str(ticket.numero).zfill(6)

    mensaje = (
        f"Hola {cliente.nombre} 😊\n\n"
        f"Gracias por tu compra en Óptica IC.\n\n"
        f"Tu N° de ticket para que puedas hacer seguimiento es: "
        f"{numero_ticket}\n\n"
        f"Tu pedido pasará por estas etapas:\n"
        f"1️⃣ En laboratorio\n"
        f"2️⃣ En taller de Biselado\n"
        f"3️⃣ Control de calidad\n"
        f"4️⃣ Listo para recoger ✅\n\n"
        f"Puedes consultar el estado de tu ticket escribiendo Menú "
        f"a este número y seleccionando la opción 2.\n\n"
        f"Óptica IC\n"
        f"Innovación y Calidad"
    )

    # ==========================================================
    # 3. DETERMINAR SI ESTÁ DENTRO DE LA VENTANA DE 24 HORAS
    # ==========================================================

    dentro_ventana = cliente_esta_en_ventana_servicio(numero)

    print("DENTRO DE VENTANA 24H:", dentro_ventana)

    # ==========================================================
    # 4. ENVIAR MENSAJE
    # ==========================================================

    if dentro_ventana:

        print("ENVIANDO COMO TEXTO")

        wa_message_id = enviar_whatsapp_texto(
            numero,
            mensaje,
            devolver_id=True,
        )

    else:

        print("ENVIANDO PLANTILLA: agradecimiento")

        wa_message_id = enviar_whatsapp_template(
            numero=numero,
            template_name="agradecimiento",
            parametros=[
                cliente.nombre,
                numero_ticket,
            ],
            devolver_id=True,
        )

    # ==========================================================
    # 5. VERIFICAR RESPUESTA DE META
    # ==========================================================

    if not wa_message_id:

        print("===================================")
        print("NO SE PUDO ENVIAR EL AGRADECIMIENTO")
        print("TICKET:", numero_ticket)
        print("CLIENTE:", cliente.nombre)
        print("TELÉFONO:", numero)
        print("===================================")

        return False

    print("===================================")
    print("META ACEPTÓ EL AGRADECIMIENTO")
    print("WA_MESSAGE_ID:", wa_message_id)
    print("===================================")

    # ==========================================================
    # 6. GUARDAR EN LA BANDEJA
    # ==========================================================

    MensajeWhatsApp.objects.create(
        numero=numero,
        nombre=cliente.nombre,
        tipo="SALIENTE",
        mensaje=mensaje,
        wa_message_id=wa_message_id,
        estado="ENVIADO",
    )

    print(
        "AGRADECIMIENTO GUARDADO EN BANDEJA:",
        wa_message_id
    )

    # ==========================================================
    # 7. CREAR CONVERSACIÓN SI TODAVÍA NO EXISTE
    # ==========================================================

    conversacion, created = (
        ConversacionWhatsApp.objects.get_or_create(
            numero=numero,
            defaults={
                "modo": "BOT",
                "estado": "INICIO",
            },
        )
    )

    # MUY IMPORTANTE:
    # Si la conversación ya existe y está en HUMANO,
    # NO la cambiamos automáticamente a BOT.

    print(
        "MODO ACTUAL DE CONVERSACIÓN:",
        conversacion.modo
    )

    # ==========================================================
    # 8. RESULTADO
    # ==========================================================

    print("===================================")
    print("AGRADECIMIENTO ENVIADO CORRECTAMENTE")
    print("TICKET:", numero_ticket)
    print("CLIENTE:", cliente.nombre)
    print("WA_MESSAGE_ID:", wa_message_id)
    print("MODO:", conversacion.modo)
    print("===================================")

    return True

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

    # ==========================================================
    # TEXTO DEL TEMPLATE PARA MOSTRAR EN LA BANDEJA
    # Debe coincidir con el template aprobado en Meta
    # ==========================================================
    mensaje_template = (
        f"Hola {cliente.nombre} 😊\n\n"
        f"Esperamos que estés disfrutando tus nuevos lentes de Óptica IC.\n\n"
        f"Podrías confirmarnos con un like si todo va bien\n\n"
    )

    # ==========================================================
    # SIEMPRE ENVIAR TEMPLATE
    # ==========================================================
    wa_message_id = enviar_whatsapp_template(
        numero=cliente.telefono,
        template_name="encuesta_7_dias",
        parametros=[
            cliente.nombre,
        ],
        devolver_id=True,
    )

    # ==========================================================
    # META ACEPTÓ EL MENSAJE
    # ==========================================================
    if wa_message_id:

        MensajeWhatsApp.objects.create(
            numero=cliente.telefono,
            nombre=cliente.nombre,
            tipo="SALIENTE",
            mensaje=mensaje_template,
            wa_message_id=wa_message_id,
            estado="ENVIADO",
        )

        # Crear conversación si todavía no existe.
        # NO cambiamos HUMANO a BOT si ya existe.
        conversacion, created = ConversacionWhatsApp.objects.get_or_create(
            numero=normalizar_numero(cliente.telefono),
            defaults={
                "modo": "BOT",
                "estado": "ESPERANDO_ENCUESTA",
            }
        )

        if not created:
            conversacion.estado = "ESPERANDO_ENCUESTA"
            conversacion.save(update_fields=["estado"])

        print(
            "ENCUESTA GUARDADA:",
            wa_message_id
        )

        return True

    print("NO SE PUDO ENVIAR ENCUESTA")
    return False

def enviar_control_menor_6_meses(orden):
    ticket = orden.ticket
    cliente = ticket.cliente

    # ==========================================================
    # VALIDAR CLIENTE Y TELÉFONO
    # ==========================================================
    if not cliente or not cliente.telefono:
        print("Cliente sin teléfono. No se envía control de 6 meses.")
        return False

    # ==========================================================
    # TEXTO QUE MOSTRAREMOS EN NUESTRA BANDEJA
    # ==========================================================
    mensaje = (
        f"Hola {cliente.nombre} 😊\n\n"
        f"Te recordamos que hoy se cumplen 6 meses desde que adquiriste lentes con nosotros.\n\n"
        f"Puedes escribir 'Cita' para separar una cita de control. "
        f"Recuerda que en menores es recomendable realizar evaluaciones semestrales.\n\n"
        f"Óptica IC\n"
        f"Innovación y Calidad"
    )

    # ==========================================================
    # SIEMPRE ENVIAR TEMPLATE
    # ==========================================================
    wa_message_id = enviar_whatsapp_template(
        numero=cliente.telefono,
        template_name="control_6_meses",
        parametros=[
            cliente.nombre,
        ],
        devolver_id=True,
    )

    # ==========================================================
    # META ACEPTÓ EL MENSAJE
    # ==========================================================
    if wa_message_id:

        MensajeWhatsApp.objects.create(
            numero=cliente.telefono,
            nombre=cliente.nombre,
            tipo="SALIENTE",
            mensaje=mensaje,
            wa_message_id=wa_message_id,
            estado="ENVIADO",
        )

        print("===================================")
        print("CONTROL 6 MESES ENVIADO")
        print("CLIENTE:", cliente.nombre)
        print("TELEFONO:", cliente.telefono)
        print("WA_MESSAGE_ID:", wa_message_id)
        print("===================================")

        return True

    # ==========================================================
    # ERROR
    # ==========================================================
    print("===================================")
    print("NO SE PUDO ENVIAR CONTROL 6 MESES")
    print("CLIENTE:", cliente.nombre)
    print("TELEFONO:", cliente.telefono)
    print("===================================")

    return False

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

    if response.status_code not in [200, 201]:
        return None

    respuesta = response.json()
    mensajes = respuesta.get("messages", [])

    if not mensajes:
        return None

    wa_message_id = mensajes[0].get("id")

    print("PDF WA_MESSAGE_ID:", wa_message_id)

    return wa_message_id

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
    if response.status_code not in [200, 201]:
        return None

    respuesta = response.json()
    mensajes = respuesta.get("messages", [])

    if not mensajes:
        return None

    wa_message_id = mensajes[0].get("id")

    print("IMAGEN WA_MESSAGE_ID:", wa_message_id)

    return wa_message_id

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

    print("===================================")
    print("=== ENVIAR REACTIVACIÓN ===")
    print("CLIENTE ID:", cliente.id if cliente else None)
    print("CLIENTE:", cliente.nombre if cliente else None)
    print("TELÉFONO:", cliente.telefono if cliente else None)
    print("===================================")

    # ==========================================================
    # 1. VALIDACIONES
    # ==========================================================

    if not cliente or not cliente.telefono:
        print("Cliente sin teléfono. No se envía WhatsApp.")
        return False

    if getattr(cliente, "excluir_reactivacion", False):
        print("Cliente excluido de reactivaciones.")
        return False

    # Normalizar teléfono para que coincida con la bandeja
    try:
        numero = normalizar_numero(cliente.telefono)

    except ValueError as e:
        print("ERROR NORMALIZANDO TELÉFONO:", e)
        return False

    # ==========================================================
    # 2. NOMBRE CORTO DEL CLIENTE
    # ==========================================================

    nombre = nombre_corto_cliente(cliente.nombre)

    # ==========================================================
    # 3. CALCULAR MÁXIMA COMPRA EN UN MISMO DÍA
    # ==========================================================

    compras_por_dia = (
        TicketVenta.objects
        .filter(cliente=cliente)
        .values("fecha_emision")
        .annotate(
            total_dia=Sum("total")
        )
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

    es_premium = categoria in ["BLUE", "BLACK"]

    print("CATEGORÍA:", categoria)
    print("ES PREMIUM:", es_premium)

    # ==========================================================
    # 5. SELECCIONAR TEMPLATE
    # ==========================================================

    if es_premium:

        template_name = "reactivar_cliente_premium"

        # IMPORTANTE:
        # Este texto debe coincidir con el template aprobado en Meta.

        mensaje_template = (
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

        # IMPORTANTE:
        # Este texto debe coincidir con el template aprobado en Meta.

        mensaje_template = (
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

    print("PLANTILLA SELECCIONADA:", template_name)

    # ==========================================================
    # 6. SIEMPRE ENVIAR TEMPLATE
    # ==========================================================

    wa_message_id = enviar_whatsapp_template(
        numero=numero,
        template_name=template_name,
        parametros=[
            nombre,
        ],
        devolver_id=True,
    )

    # ==========================================================
    # 7. VERIFICAR RESPUESTA DE META
    # ==========================================================

    if not wa_message_id:

        print("===================================")
        print("ERROR ENVIANDO REACTIVACIÓN")
        print("CLIENTE:", cliente.nombre)
        print("TELÉFONO:", numero)
        print("PLANTILLA:", template_name)
        print("===================================")

        return False

    print("===================================")
    print("META ACEPTÓ LA REACTIVACIÓN")
    print("WA_MESSAGE_ID:", wa_message_id)
    print("===================================")

    # ==========================================================
    # 8. REGISTRAR MENSAJE EN LA BANDEJA
    # ==========================================================

    MensajeWhatsApp.objects.create(
        numero=numero,
        nombre=cliente.nombre,
        tipo="SALIENTE",
        mensaje=mensaje_template,
        wa_message_id=wa_message_id,
        estado="ENVIADO",
    )

    print(
        "MENSAJE GUARDADO EN BANDEJA:",
        wa_message_id
    )

    # ==========================================================
    # 9. CREAR CONVERSACIÓN SIN ALTERAR BOT/HUMANO
    # ==========================================================

    conversacion, created = (
        ConversacionWhatsApp.objects.get_or_create(
            numero=numero,
            defaults={
                "modo": "BOT",
                "estado": "INICIO",
            },
        )
    )

    # IMPORTANTE:
    # Si la conversación ya existe y está en HUMANO,
    # permanece en HUMANO.
    #
    # No ejecutamos:
    # conversacion.modo = "BOT"

    print(
        "MODO ACTUAL DE CONVERSACIÓN:",
        conversacion.modo
    )

    # ==========================================================
    # 10. REGISTRAR HISTORIAL DE REACTIVACIÓN
    # ==========================================================

    ReactivacionWhatsApp.objects.create(
        cliente=cliente,
        categoria=categoria,
        monto_maximo=maxima_compra_dia,
    )

    # ==========================================================
    # 11. ACTUALIZAR FECHA DE ÚLTIMA REACTIVACIÓN
    # ==========================================================

    cliente.fecha_ultima_reactivacion = timezone.localdate()

    cliente.save(
        update_fields=[
            "fecha_ultima_reactivacion",
        ]
    )

    # ==========================================================
    # 12. RESULTADO FINAL
    # ==========================================================

    print("===================================")
    print("REACTIVACIÓN REGISTRADA CORRECTAMENTE")
    print("CLIENTE:", cliente.nombre)
    print("CATEGORÍA:", categoria)
    print("PLANTILLA:", template_name)
    print("WA_MESSAGE_ID:", wa_message_id)
    print("MODO:", conversacion.modo)
    print("===================================")

    return True