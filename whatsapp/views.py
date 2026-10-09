from django.shortcuts import render, redirect, get_object_or_404 

# Create your views here.
import os
import json

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import ConversacionWhatsApp, CitaWhatsApp, MensajeWhatsApp

from .utils import enviar_whatsapp_texto, avisar_asesor, subir_media_whatsapp, enviar_whatsapp_pdf, enviar_whatsapp_texto_y_guardar, nombre_corto_cliente, normalizar_numero, enviar_whatsapp_imagen, descargar_media_whatsapp

from core.models import TicketVenta, OrdenTrabajo, Cliente

from django.contrib.auth.decorators import login_required
from django.db.models import Max

from .ai import responder_con_openai

from datetime import timedelta
from django.utils import timezone
import traceback

from django.contrib import messages
from django.core.files.base import ContentFile

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
FACEBOOK_VERIFY_TOKEN = "optica_ic_facebook_2026"


def enviar_menu_principal(numero):
    mensaje = (
        "Hola, soy el asistende virtual de Óptica IC 👓\n\n"
        "¿En qué puedo ayudarte?\n\n"
        "1️⃣ Horario de atención\n"
        "2️⃣ Estado de mi ticket\n"
        "3️⃣ Ubicación\n"
        "4️⃣ Sacar una cita\n"
        "5️⃣ Hablar con un asesor\n\n"
        "0️⃣ Menú principal"
    )
    enviar_whatsapp_texto_y_guardar(numero, mensaje)


def responder_mensaje(numero, texto):

    numero = normalizar_numero(numero)
    texto_original = (texto or "").strip()
    texto = texto_original.lower()

    if not texto_original:
        print("Mensaje vacío. No se procesa.")
        return

    # ==========================================================
    # 1. OBTENER O CREAR CONVERSACIÓN
    # ==========================================================

    conversacion, created = ConversacionWhatsApp.objects.get_or_create(
        numero=numero,
        defaults={
            "modo": "BOT",
            "estado": "INICIO",
        }
    )

    # ==========================================================
    # 2. FUNCIÓN INTERNA PARA AVISAR AL ASESOR
    # ==========================================================

    def notificar_asesor(asunto, detalle=None):

        mensaje_aviso = (
            f"🔔 {asunto}\n\n"
            f"Cliente WhatsApp: {numero}\n"
            f"Mensaje recibido: {texto_original}\n"
        )

        if detalle:
            mensaje_aviso += f"\n{detalle}\n"

        mensaje_aviso += "\nRevisar la bandeja de Óptica IC."

        try:
            resultado = avisar_asesor(mensaje_aviso)

            print("=== AVISO AL ASESOR ===")
            print("CLIENTE:", numero)
            print("MOTIVO:", asunto)
            print("RESULTADO:", resultado)

            if not resultado:
                print(
                    "ADVERTENCIA: No se confirmó el envío "
                    "de la notificación al asesor."
                )

            return bool(resultado)

        except Exception as error:
            print("ERROR AVISANDO AL ASESOR:", str(error))
            return False

    # ==========================================================
    # 3. FUNCIÓN INTERNA PARA TRANSFERIR A HUMANO
    # ==========================================================

    def pasar_a_humano(asunto, detalle=None, mensaje_cliente=None):

        notificar_asesor(asunto, detalle)

        conversacion.modo = "HUMANO"
        conversacion.estado = "ASESOR"
        conversacion.save()

        if mensaje_cliente:
            enviar_whatsapp_texto_y_guardar(
                numero,
                mensaje_cliente
            )

        return

    # ==========================================================
    # 4. CONTROL DE INACTIVIDAD
    # ==========================================================

    ESTADOS_ESPERANDO = [
        "ESPERANDO_TICKET",
        "ESPERANDO_DATOS_CITA",
        "ESPERANDO_ENCUESTA",
        "ESPERANDO_CONFIRMACION_ASESOR",
    ]

    if not created:

        tiempo_inactivo = timezone.now() - conversacion.actualizado

        if (
            conversacion.modo == "BOT"
            and tiempo_inactivo > timedelta(minutes=30)
            and conversacion.estado in ESTADOS_ESPERANDO
        ):

            conversacion.estado = "INICIO"
            conversacion.save(update_fields=["estado"])

            print(
                f"Estado pendiente vencido para {numero}. "
                "Se procesará el mensaje actual normalmente."
            )

    # ==========================================================
    # 5. REINICIAR CONVERSACIÓN FINALIZADA
    # ==========================================================

    if conversacion.estado == "FINALIZADO":

        conversacion.modo = "BOT"
        conversacion.estado = "INICIO"
        conversacion.save()

    # ==========================================================
    # 6. VOLVER AL BOT / MENÚ PRINCIPAL
    # ==========================================================

    if texto in [
        "0",
        "0️⃣",
        "menu",
        "menú",
        "menu principal",
        "menú principal",
    ]:

        conversacion.modo = "BOT"
        conversacion.estado = "INICIO"
        conversacion.save()

        enviar_menu_principal(numero)
        return

    # ==========================================================
    # 7. CONVERSACIÓN EN MODO HUMANO
    # ==========================================================

    if conversacion.modo == "HUMANO":

        print(
            f"Cliente {numero} está en modo HUMANO. "
            "Se notificará al asesor."
        )

        notificar_asesor(
            "NUEVO MENSAJE EN ATENCIÓN HUMANA",
            "El cliente está siendo atendido por un asesor."
        )

        # No responder automáticamente.
        return

    # ==========================================================
    # 8. CONFIRMACIÓN DE ASESOR PENDIENTE
    # ==========================================================

    if conversacion.estado == "ESPERANDO_CONFIRMACION_ASESOR":

        if texto in [
            "1", "1️⃣", "si", "sí", "sip",
            "ok", "dale", "quiero", "asesor",
        ]:

            pasar_a_humano(
                "CLIENTE CONFIRMA ATENCIÓN HUMANA",
                mensaje_cliente=(
                    "Perfecto 😊\n\n"
                    "Tu solicitud ha sido derivada a nuestro equipo. "
                    "Un asesor de Óptica IC continuará la atención "
                    "en breve.\n\n"
                    "Para volver al menú principal escribe 0️⃣"
                )
            )
            return

        conversacion.estado = "FINALIZADO"
        conversacion.save(update_fields=["estado"])

        enviar_whatsapp_texto_y_guardar(
            numero,
            "Entendido 😊 Si más adelante necesitas ayuda, "
            "aquí estaremos."
        )
        return

    # ==========================================================
    # 9. CONFIRMACIÓN DE SEGUIMIENTO DE LENTES
    # ==========================================================

    if conversacion.estado == "ESPERANDO_CONFIRMACION_SEGUIMIENTO":

        texto_confirmacion = texto.replace("\ufe0f", "").strip()

        RESPUESTAS_POSITIVAS = [
            "👍",
            "👍🏻",
            "👍🏼",
            "👍🏽",
            "👍🏾",
            "👍🏿",
            "👌",
            "✅",
            "si",
            "sí",
            "sip",
            "todo bien",
            "todo esta bien",
            "todo está bien",
            "muy bien",
            "excelente",
            "perfecto",
            "bien",
            "ok",
            "gracias",
        ]

        if (
            texto in RESPUESTAS_POSITIVAS
            or texto_confirmacion in RESPUESTAS_POSITIVAS
        ):

            conversacion.estado = "FINALIZADO"
            conversacion.save(update_fields=["estado"])

            enviar_whatsapp_texto_y_guardar(
                numero,
                "¡Muchas gracias por confirmarnos! 😊\n\n"
                "Nos alegra saber que todo va bien con tus lentes.\n\n"
                "¡Gracias por confiar en Óptica IC!"
            )
            return

        PALABRAS_PROBLEMA = [
            "problema",
            "molestia",
            "incomodo",
            "incómodo",
            "mareo",
            "borroso",
            "no veo",
            "mal",
            "reclamo",
            "no estoy bien",
        ]

        if any(palabra in texto for palabra in PALABRAS_PROBLEMA):

            pasar_a_humano(
                "CLIENTE REPORTA PROBLEMA CON SUS LENTES",
                mensaje_cliente=(
                    "Gracias por contarnos lo ocurrido. 😊\n\n"
                    "Hemos recibido tu mensaje y un asesor "
                    "de Óptica IC continuará la atención.\n\n"
                    "Para volver al menú principal escribe 0️⃣"
                )
            )
            return

        # Respuesta distinta: continuar con el procesamiento
        # normal y permitir que OpenAI analice el historial.
        conversacion.estado = "INICIO"
        conversacion.save(update_fields=["estado"])

    # ==========================================================
    # 10. ENCUESTA DE CALIFICACIÓN DEL 1 AL 5
    # ==========================================================

    if conversacion.estado == "ESPERANDO_ENCUESTA":

        if texto in [
            "1", "1️⃣",
            "2", "2️⃣",
            "3", "3️⃣",
            "4", "4️⃣",
            "5", "5️⃣",
        ]:

            calificacion = (
                texto.replace("\ufe0f", "").replace("\u20e3", "")
            )

            conversacion.estado = "FINALIZADO"
            conversacion.save(update_fields=["estado"])

            enviar_whatsapp_texto_y_guardar(
                numero,
                "¡Gracias por calificar tu experiencia "
                "con Óptica IC! 🙌\n\n"
                f"Tu respuesta fue: {calificacion}/5\n\n"
                "Tu opinión nos ayuda a mejorar."
            )
            return

        enviar_whatsapp_texto_y_guardar(
            numero,
            "Por favor responde con un número del 1 al 5 😊"
        )
        return

    # ==========================================================
    # 11. RECEPCIÓN DE DATOS PARA CITA
    # ==========================================================

    if conversacion.estado == "ESPERANDO_DATOS_CITA":

        CitaWhatsApp.objects.create(
            numero=numero,
            datos_cliente=texto_original
        )

        pasar_a_humano(
            "NUEVA SOLICITUD DE CITA",
            mensaje_cliente=(
                "Gracias 😊 Hemos recibido tus datos para la cita.\n\n"
                "Un asesor de Óptica IC te confirmará "
                "la disponibilidad en breve.\n\n"
                "Para volver al menú principal escribe 0️⃣"
            )
        )
        return

    # ==========================================================
    # 12. CLIENTE ESTABA CONSULTANDO SU TICKET
    # ==========================================================

    if conversacion.estado == "ESPERANDO_TICKET":

        encontrado = consultar_estado_ticket(
            numero,
            texto_original
        )

        conversacion.estado = (
            "FINALIZADO" if encontrado else "ESPERANDO_TICKET"
        )
        conversacion.save(update_fields=["estado"])
        return

    # ==========================================================
    # 13. SALUDO / MENÚ
    # ==========================================================

    if texto in [
        "hola",
        "hi",
        "buenos dias",
        "buenos días",
        "buenas tardes",
        "buenas noches",
    ]:

        conversacion.estado = "INICIO"
        conversacion.save(update_fields=["estado"])

        enviar_menu_principal(numero)
        return

    # ==========================================================
    # 14. AGRADECIMIENTO
    # ==========================================================

    if texto in [
        "gracias",
        "muchas gracias",
        "ok gracias",
        "listo gracias",
        "perfecto gracias",
    ]:

        conversacion.estado = "FINALIZADO"
        conversacion.save(update_fields=["estado"])

        enviar_whatsapp_texto_y_guardar(
            numero,
            "¡Con gusto! 😊 Estamos para ayudarte."
        )
        return

    # ==========================================================
    # 15. HORARIO
    # ==========================================================

    if texto in ["1", "1️⃣"] or "horario" in texto:

        conversacion.estado = "FINALIZADO"
        conversacion.save(update_fields=["estado"])

        enviar_whatsapp_texto_y_guardar(
            numero,
            "Nuestro horario de atención es:\n\n"
            "Lunes a sábado: 9:00 a.m. a 7:45 p.m.\n"
            "Domingos: 10:30 a.m. a 6:00 p.m.\n\n"
            "Los horarios especiales por feriados "
            "se confirman por separado."
        )
        return

    # ==========================================================
    # 16. CONSULTA DIRECTA DE TICKET
    # ==========================================================

    if texto.startswith("ticket"):

        partes = texto_original.split(maxsplit=1)

        if len(partes) > 1 and partes[1].strip():

            encontrado = consultar_estado_ticket(
                numero,
                partes[1].strip()
            )

            conversacion.estado = (
                "FINALIZADO" if encontrado else "ESPERANDO_TICKET"
            )
            conversacion.save(update_fields=["estado"])
            return

        conversacion.estado = "ESPERANDO_TICKET"
        conversacion.save(update_fields=["estado"])

        enviar_whatsapp_texto_y_guardar(
            numero,
            "Por favor escribe el número de tu ticket.\n\n"
            "Ejemplo: 000123"
        )
        return

    # ==========================================================
    # 17. ESTADO DE TICKET
    # ==========================================================

    if (
        texto in ["2", "2️⃣"]
        or "estado" in texto
        or "ticket" in texto
    ):

        conversacion.estado = "ESPERANDO_TICKET"
        conversacion.save(update_fields=["estado"])

        enviar_whatsapp_texto_y_guardar(
            numero,
            "Por favor escribe el número de tu ticket.\n\n"
            "Ejemplo: 000123"
        )
        return

    # ==========================================================
    # 18. UBICACIÓN
    # ==========================================================

    if (
        texto in ["3", "3️⃣"]
        or "ubicacion" in texto
        or "ubicación" in texto
        or "direccion" in texto
        or "dirección" in texto
    ):

        conversacion.estado = "FINALIZADO"
        conversacion.save(update_fields=["estado"])

        enviar_whatsapp_texto_y_guardar(
            numero,
            "Estamos ubicados en:\n"
            "Jr. Camaná 560 - Cercado de Lima.\n\n"
            "Referencia: Entre Av. Emancipación "
            "y Jr. Huancavelica."
        )
        return

    # ==========================================================
    # 19. SACAR CITA
    # ==========================================================

    if texto in ["4", "4️⃣"] or "cita" in texto:

        conversacion.estado = "ESPERANDO_DATOS_CITA"
        conversacion.save(update_fields=["estado"])

        enviar_whatsapp_texto_y_guardar(
            numero,
            "Claro 😊 Para separar una cita, "
            "envíanos en un solo mensaje:\n\n"
            "1. Nombre completo\n"
            "2. Día deseado\n"
            "3. Hora aproximada\n"
            "4. Motivo de consulta\n\n"
            "Ejemplo:\n"
            "Juan Pérez, martes 5:00 p.m., medida de vista"
        )
        return

    # ==========================================================
    # 20. ASESOR DIRECTO DESDE EL MENÚ
    # ==========================================================

    if (
        texto in ["5", "5️⃣"]
        or "asesor" in texto
        or "persona" in texto
    ):

        pasar_a_humano(
            "CLIENTE SOLICITA ASESOR",
            mensaje_cliente=(
                "Un asesor de Óptica IC te atenderá en breve.\n\n"
                "Para volver al menú principal escribe 0️⃣"
            )
        )
        return

    # ==========================================================
    # 21. SOLICITUD DE RENOVACIÓN DE LENTES
    # ==========================================================

    PALABRAS_RENOVACION = [
        "renovar mis lentes",
        "renovación de mis lentes",
        "renovacion de mis lentes",
        "renovar lentes",
        "renovar los lentes",
        "mis mismas medidas",
        "mismas medidas",
        "medidas anteriores",
        "mis medidas anteriores",
        "hacerme otros lentes",
        "comprar otros lentes",
    ]

    if any(frase in texto for frase in PALABRAS_RENOVACION):

        pasar_a_humano(
            "CLIENTE SOLICITA RENOVACIÓN DE LENTES",
            mensaje_cliente=(
                "¡Claro! 😊 Podemos ayudarte con la "
                "renovación de tus lentes.\n\n"
                "Un asesor de Óptica IC revisará tu solicitud "
                "y continuará la atención.\n\n"
                "Para volver al menú principal escribe 0️⃣"
            )
        )
        return

    # ==========================================================
    # 22. CONSULTAR OPENAI UNA SOLA VEZ
    # ==========================================================

    print("USANDO OPENAI PARA:", texto_original)

    try:

        respuesta_ia = responder_con_openai(
            numero,
            texto_original
        )

        respuesta_ia = (respuesta_ia or "").strip()

        if not respuesta_ia:
            raise ValueError("OpenAI devolvió una respuesta vacía.")

    except Exception as error:

        print("ERROR OPENAI:", str(error))

        pasar_a_humano(
            "ERROR AL PROCESAR CONSULTA CON OPENAI",
            detalle=f"Error técnico: {str(error)}",
            mensaje_cliente=(
                "En este momento no puedo procesar "
                "correctamente tu consulta.\n\n"
                "He derivado tu solicitud a nuestro equipo "
                "para que un asesor pueda ayudarte."
            )
        )
        return

    print("RESPUESTA OPENAI:", respuesta_ia)

    respuesta_mayuscula = respuesta_ia.upper()

    # ==========================================================
    # 23. INTENCIÓN: ESTADO DE TICKET
    # ==========================================================

    if "[INTENCION:ESTADO_TICKET]" in respuesta_mayuscula:

        conversacion.estado = "ESPERANDO_TICKET"
        conversacion.save(update_fields=["estado"])

        enviar_whatsapp_texto_y_guardar(
            numero,
            "Claro 😊 Para revisar el estado de tus lentes, "
            "por favor escribe el número de tu ticket.\n\n"
            "Ejemplo: 000123"
        )
        return

    # ==========================================================
    # 24. INTENCIÓN: HORARIO
    # ==========================================================

    if "[INTENCION:HORARIO]" in respuesta_mayuscula:

        conversacion.estado = "FINALIZADO"
        conversacion.save(update_fields=["estado"])

        enviar_whatsapp_texto_y_guardar(
            numero,
            "Nuestro horario de atención es:\n\n"
            "Lunes a sábado: 9:00 a.m. a 7:45 p.m.\n"
            "Domingos: 10:30 a.m. a 6:00 p.m.\n\n"
            "Los horarios especiales por feriados "
            "se confirman por separado."
        )
        return

    # ==========================================================
    # 25. INTENCIÓN: UBICACIÓN
    # ==========================================================

    if "[INTENCION:UBICACION]" in respuesta_mayuscula:

        conversacion.estado = "FINALIZADO"
        conversacion.save(update_fields=["estado"])

        enviar_whatsapp_texto_y_guardar(
            numero,
            "Estamos ubicados en Jr. Camaná 560, "
            "Cercado de Lima.\n\n"
            "Referencia: Entre Av. Emancipación "
            "y Jr. Huancavelica."
        )
        return

    # ==========================================================
    # 26. INTENCIÓN: CITA
    # ==========================================================

    if "[INTENCION:CITA]" in respuesta_mayuscula:

        conversacion.estado = "ESPERANDO_DATOS_CITA"
        conversacion.save(update_fields=["estado"])

        enviar_whatsapp_texto_y_guardar(
            numero,
            "Claro 😊 Para separar una cita, envíanos:\n\n"
            "1. Nombre completo\n"
            "2. Día deseado\n"
            "3. Hora aproximada\n"
            "4. Motivo de consulta\n\n"
            "Ejemplo: Juan Pérez, martes 5:00 p.m., "
            "medida de vista."
        )
        return

    # ==========================================================
    # 27. OPENAI SOLICITA ATENCIÓN HUMANA
    # ==========================================================

    if (
        "[INTENCION:ASESOR]" in respuesta_mayuscula
        or "[ASESOR]" in respuesta_mayuscula
    ):

        pasar_a_humano(
            "OPENAI DERIVA CONSULTA A ASESOR",
            detalle="OpenAI no resolvió la consulta o identificó atención humana.",
            mensaje_cliente=(
                "Gracias por escribirnos 😊\n\n"
                "Tu solicitud ha sido derivada a nuestro equipo. "
                "Un asesor de Óptica IC continuará la atención "
                "en breve.\n\n"
                "Para volver al menú principal escribe 0️⃣"
            )
        )
        return

    # ==========================================================
    # 28. RESPUESTA NORMAL DE OPENAI
    # ==========================================================

    conversacion.estado = "FINALIZADO"
    conversacion.save(update_fields=["estado"])

    enviar_whatsapp_texto_y_guardar(
        numero,
        respuesta_ia
    )

    return

    

@csrf_exempt
def whatsapp_webhook(request):

    # ==========================================================
    # 1. VERIFICACIÓN DEL WEBHOOK DE META
    # ==========================================================

    if request.method == "GET":

        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        if mode == "subscribe" and token == VERIFY_TOKEN:
            return HttpResponse(challenge)

        return HttpResponse(
            "Token inválido",
            status=403
        )

    # ==========================================================
    # 2. RECEPCIÓN DE EVENTOS DE WHATSAPP
    # ==========================================================

    if request.method == "POST":

        try:

            data = json.loads(
                request.body.decode("utf-8")
            )

            print("===================================")
            print("WHATSAPP RECIBIDO")
            print(data)
            print("===================================")

            # ==================================================
            # RECORRER TODAS LAS ENTRADAS Y CAMBIOS
            # ==================================================

            for entry in data.get("entry", []):

                for change in entry.get("changes", []):

                    value = change.get("value", {})

                    # ==========================================
                    # 3. ACTUALIZAR ESTADOS DE MENSAJES SALIENTES
                    # ==========================================

                    statuses = value.get("statuses", [])

                    mapa_estados = {
                        "sent": "ENVIADO",
                        "delivered": "ENTREGADO",
                        "read": "LEIDO",
                        "failed": "FALLIDO",
                    }

                    # Jerarquía de estados exitosos.
                    # Evita que una notificación retrasada
                    # haga retroceder el estado del mensaje.

                    prioridad_estados = {
                        "PENDIENTE": 0,
                        "ENVIADO": 1,
                        "ENTREGADO": 2,
                        "LEIDO": 3,
                    }

                    for status_data in statuses:

                        wa_message_id = status_data.get("id")
                        status_meta = status_data.get("status")

                        nuevo_estado = mapa_estados.get(
                            status_meta
                        )

                        print("-----------------------------------")
                        print("ESTADO WHATSAPP RECIBIDO")
                        print("WA_MESSAGE_ID:", wa_message_id)
                        print("STATUS META:", status_meta)
                        print("-----------------------------------")

                        if not wa_message_id or not nuevo_estado:
                            continue

                        # --------------------------------------
                        # TRATAMIENTO DE ESTADO FALLIDO
                        # --------------------------------------

                        if nuevo_estado == "FALLIDO":

                            # No sustituimos un estado de entrega
                            # o lectura ya confirmado por FALLIDO.

                            actualizados = (
                                MensajeWhatsApp.objects
                                .filter(
                                    wa_message_id=wa_message_id,
                                    tipo="SALIENTE",
                                    estado__in=[
                                        "PENDIENTE",
                                        "ENVIADO",
                                    ],
                                )
                                .update(
                                    estado="FALLIDO",
                                )
                            )

                            if actualizados:

                                print(
                                    "ESTADO ACTUALIZADO:",
                                    wa_message_id,
                                    "-> FALLIDO"
                                )

                            else:

                                print(
                                    "ESTADO FALLIDO NO APLICADO:",
                                    wa_message_id
                                )

                            errores = status_data.get(
                                "errors",
                                []
                            )

                            if errores:
                                print(
                                    "DETALLE ERROR META:",
                                    errores
                                )

                            continue

                        # --------------------------------------
                        # ACTUALIZAR SOLO SI EL ESTADO AVANZA
                        # --------------------------------------

                        prioridad_nueva = (
                            prioridad_estados[nuevo_estado]
                        )

                        estados_anteriores = [
                            estado
                            for estado, prioridad
                            in prioridad_estados.items()
                            if prioridad < prioridad_nueva
                        ]

                        actualizados = (
                            MensajeWhatsApp.objects
                            .filter(
                                wa_message_id=wa_message_id,
                                tipo="SALIENTE",
                                estado__in=estados_anteriores,
                            )
                            .update(
                                estado=nuevo_estado,
                                leido=(
                                    nuevo_estado == "LEIDO"
                                ),
                            )
                        )

                        if actualizados:

                            print(
                                "ESTADO ACTUALIZADO:",
                                wa_message_id,
                                "->",
                                nuevo_estado,
                            )

                        else:

                            mensaje_actual = (
                                MensajeWhatsApp.objects
                                .filter(
                                    wa_message_id=wa_message_id,
                                    tipo="SALIENTE",
                                )
                                .first()
                            )

                            if mensaje_actual:

                                print(
                                    "ESTADO CONSERVADO:",
                                    wa_message_id,
                                    "ACTUAL:",
                                    mensaje_actual.estado,
                                    "RECIBIDO:",
                                    nuevo_estado,
                                )

                            else:

                                print(
                                    "NO SE ENCONTRÓ MENSAJE "
                                    "SALIENTE:",
                                    wa_message_id,
                                )

                    # ==========================================
                    # 4. PROCESAR MENSAJES ENTRANTES
                    # ==========================================

                    messages = value.get("messages", [])
                    contacts = value.get("contacts", [])

                    nombres_contactos = {}

                    for contacto in contacts:

                        numero_contacto = contacto.get(
                            "wa_id"
                        )

                        nombre_contacto = (
                            contacto
                            .get("profile", {})
                            .get("name", "")
                        )

                        if numero_contacto:

                            nombres_contactos[
                                numero_contacto
                            ] = nombre_contacto

                    # ==========================================
                    # RECORRER TODOS LOS MENSAJES
                    # ==========================================

                    for message in messages:

                        numero_original = message.get(
                            "from",
                            ""
                        )

                        if not numero_original:

                            print(
                                "MENSAJE SIN NÚMERO. "
                                "SE IGNORA."
                            )

                            continue

                        numero = normalizar_numero(
                            numero_original
                        )

                        if not numero:

                            print(
                                "NÚMERO INVÁLIDO:",
                                numero_original
                            )

                            continue

                        tipo = message.get("type")

                        message_id = message.get("id")

                        nombre_contacto = (
                            nombres_contactos.get(
                                numero_original,
                                ""
                            )
                        )

                        # --------------------------------------
                        # EVITAR MENSAJES DUPLICADOS
                        # --------------------------------------

                        if message_id:

                            ya_registrado = (
                                MensajeWhatsApp.objects
                                .filter(
                                    wa_message_id=message_id,
                                    tipo="ENTRANTE",
                                )
                                .exists()
                            )

                            if ya_registrado:

                                print(
                                    "MENSAJE DUPLICADO IGNORADO:",
                                    message_id
                                )

                                continue

                        # --------------------------------------
                        # OBTENER CONVERSACIÓN
                        # --------------------------------------

                        conversacion, created = (
                            ConversacionWhatsApp.objects
                            .get_or_create(
                                numero=numero,
                                defaults={
                                    "modo": "BOT",
                                    "estado": "INICIO",
                                },
                            )
                        )

                        # ======================================
                        # 5. MENSAJE DE TEXTO
                        # ======================================

                        if tipo == "text":

                            texto = (
                                message
                                .get("text", {})
                                .get("body", "")
                            )

                            MensajeWhatsApp.objects.create(
                                numero=numero,
                                nombre=nombre_contacto,
                                tipo="ENTRANTE",
                                mensaje=texto,
                                wa_message_id=message_id,
                            )

                            print(
                                "MENSAJE ENTRANTE GUARDADO:",
                                message_id
                            )

                            # Mantener separación BOT/HUMANO

                            if conversacion.modo == "BOT":

                                responder_mensaje(
                                    numero,
                                    texto
                                )

                            else:

                                print(
                                    "Conversación en modo HUMANO. "
                                    "El bot no responde."
                                )

                        # ======================================
                        # 6. MENSAJE DE IMAGEN
                        # ======================================

                        elif tipo == "image":

                            datos_imagen = message.get(
                                "image",
                                {}
                            )

                            media_id = datos_imagen.get(
                                "id"
                            )

                            caption = datos_imagen.get(
                                "caption",
                                ""
                            )

                            mime_type = datos_imagen.get(
                                "mime_type",
                                "image/jpeg"
                            )

                            media_descargado = None

                            if media_id:

                                media_descargado = (
                                    descargar_media_whatsapp(
                                        media_id
                                    )
                                )

                            # ----------------------------------
                            # IMAGEN DESCARGADA CORRECTAMENTE
                            # ----------------------------------

                            if media_descargado:

                                if mime_type == "image/png":
                                    extension = ".png"

                                elif mime_type == "image/webp":
                                    extension = ".webp"

                                else:
                                    extension = ".jpg"

                                nombre_archivo = (
                                    f"imagen_{message_id}"
                                    f"{extension}"
                                )

                                mensaje_imagen = (
                                    MensajeWhatsApp(
                                        numero=numero,
                                        nombre=nombre_contacto,
                                        tipo="ENTRANTE",
                                        mensaje=(
                                            caption
                                            if caption
                                            else "Imagen recibida"
                                        ),
                                        wa_message_id=message_id,
                                    )
                                )

                                mensaje_imagen.archivo.save(
                                    nombre_archivo,
                                    ContentFile(
                                        media_descargado[
                                            "contenido"
                                        ]
                                    ),
                                    save=False,
                                )

                                mensaje_imagen.save()

                                print(
                                    "IMAGEN RECIBIDA Y GUARDADA:",
                                    nombre_archivo
                                )

                            # ----------------------------------
                            # ERROR DESCARGANDO IMAGEN
                            # ----------------------------------

                            else:

                                MensajeWhatsApp.objects.create(
                                    numero=numero,
                                    nombre=nombre_contacto,
                                    tipo="ENTRANTE",
                                    mensaje=(
                                        "Se recibió una imagen, "
                                        "pero no se pudo descargar."
                                    ),
                                    wa_message_id=message_id,
                                )

                                print(
                                    "NO SE PUDO DESCARGAR "
                                    "LA IMAGEN:",
                                    message_id
                                )

        except Exception as e:

            print(
                "ERROR WEBHOOK:",
                repr(e)
            )

        return JsonResponse({
            "status": "ok"
        })

    return HttpResponse(
        "Método no permitido",
        status=405
    )



@csrf_exempt
def webhook_facebook(request):

    # ==========================================
    # VERIFICACIÓN DEL WEBHOOK POR META
    # ==========================================
    if request.method == "GET":

        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        if mode == "subscribe" and token == FACEBOOK_VERIFY_TOKEN:
            print("FACEBOOK WEBHOOK VERIFICADO")
            return HttpResponse(challenge, status=200)

        print("ERROR VERIFICANDO FACEBOOK WEBHOOK")
        return HttpResponse("Token de verificación incorrecto", status=403)

    # ==========================================
    # MENSAJES ENTRANTES
    # Lo programaremos en el siguiente paso
    # ==========================================
    if request.method == "POST":
        print("WEBHOOK FACEBOOK RECIBIDO")
        print(request.body)

        return HttpResponse("EVENT_RECEIVED", status=200)

    return HttpResponse(status=405)



def consultar_estado_ticket(numero, texto_ticket):
    numero_ticket = texto_ticket.strip().upper()
    numero_ticket = numero_ticket.replace("TICKET", "").strip()
    numero_ticket = numero_ticket.lstrip("0")

    if not numero_ticket:
        enviar_whatsapp_texto_y_guardar(
            numero,
            "Por favor escribe el número de ticket.\n\n"
            "Ejemplo: 000123"
        )
        return

    try:
        ticket = TicketVenta.objects.get(numero=numero_ticket)
    except TicketVenta.DoesNotExist:
        enviar_whatsapp_texto_y_guardar(
            numero,
            "No encontramos ese número de ticket.\n\n"
            "Verifica el número e intenta nuevamente.\n\n"
            "Ejemplo: 000123"
        )
        return False

    orden = OrdenTrabajo.objects.filter(ticket=ticket).last()

    if not orden:
        enviar_whatsapp_texto_y_guardar(
            numero,
            f"Encontramos tu ticket N° {ticket.numero}, pero aún no tiene orden de trabajo registrada."
        )
        return

    estados = {
        "LAB_PEDIDO": "🏭 Pedido enviado a laboratorio",
        "LAB_EN_PROCESO": "🔬 En proceso de fabricación",
        "BISELADO": "🔧 En taller de biselado",
        "UV": "🔍 En control de calidad",
        "LISTO": "✅ Listo para recoger",
        "ENTREGADO": "📦 Entregado",
    }

    estado_codigo = orden.estado
    estado_texto = estados.get(estado_codigo, f"📌 {orden.get_estado_display()}")

    mensaje = (
        f"Ticket N° {ticket.numero}\n\n"
        f"Estado actual:\n"
        f"{estado_texto}\n\n"
    )

    if estado_codigo == "LISTO":
        mensaje += (
            "Tus lentes ya están listos. Puedes acercarte a recogerlos 😊\n\n"
        )

    elif estado_codigo == "ENTREGADO":
        mensaje += (
            "Este pedido ya fue entregado. Gracias por confiar en Óptica IC 😊\n\n"
        )

    else:
        mensaje += (
            "Seguimos trabajando en tu pedido. Te avisaremos cuando esté listo.\n\n"
        )

    mensaje += (
        "Óptica IC\n"
        "Innovación y Calidad"
    )

    enviar_whatsapp_texto_y_guardar(numero, mensaje)
    
    return True


@login_required
def bandeja_whatsapp(request):
    try:
        mensajes = MensajeWhatsApp.objects.all().order_by("-creado")

        grupos = {}

        for msg in mensajes:
            try:
                numero_normalizado = normalizar_numero(msg.numero)
            except ValueError:
                print("Número inválido ignorado en bandeja:", msg.numero)
                continue

            if numero_normalizado not in grupos:
                grupos[numero_normalizado] = msg

        lista = []

        for numero, ultimo_msg in grupos.items():
            numero_sin_51 = numero[2:] if numero.startswith("51") else numero

            cliente = Cliente.objects.filter(
                telefono=numero_sin_51
            ).first()

            conversacion, created = ConversacionWhatsApp.objects.get_or_create(
                numero=numero,
                defaults={
                    "modo": "BOT",
                    "estado": "INICIO",
                }
            )

            no_leidos = MensajeWhatsApp.objects.filter(
                numero__in=[numero, numero_sin_51],
                tipo="ENTRANTE",
                leido=False
            ).count()

            nombre_mostrar = (
                nombre_corto_cliente(cliente.nombre)
                if cliente
                else ultimo_msg.nombre if ultimo_msg and ultimo_msg.nombre
                else "Cliente"
            )

            lista.append({
                "numero": numero,
                "nombre": nombre_mostrar,
                "ultimo_mensaje": ultimo_msg.mensaje if ultimo_msg else "",
                "ultimo": ultimo_msg.creado if ultimo_msg else None,
                "modo": conversacion.modo,
                "no_leidos": no_leidos,
            })

        return render(request, "whatsapp/bandeja.html", {
            "conversaciones": lista
        })

    except Exception as e:
        print("ERROR EN BANDEJA WHATSAPP:")
        print(e)
        traceback.print_exc()
        raise

# ============================================================
# CHAT WHATSAPP
# ============================================================

def chat_whatsapp(request, numero):

    # ========================================================
    # 1. NORMALIZAR NÚMERO
    # ========================================================

    numero = normalizar_numero(numero)

    if not numero:
        print("Número inválido en chat WhatsApp.")
        return redirect("whatsapp_bandeja")

    numero_sin_51 = (
        numero[2:]
        if numero.startswith("51")
        else numero
    )

    posibles_numeros = [
        numero,
        numero_sin_51,
    ]

    # ========================================================
    # 2. OBTENER O CREAR CONVERSACIÓN
    # ========================================================

    conversacion, created = (
        ConversacionWhatsApp.objects.get_or_create(
            numero=numero,
            defaults={
                "modo": "BOT",
                "estado": "INICIO",
            }
        )
    )

    # IMPORTANTE:
    # Si ya existe y está en HUMANO,
    # NO modificamos conversacion.modo.

    # ========================================================
    # 3. ENVÍO MANUAL
    # ========================================================

    if request.method == "POST":

        texto = request.POST.get(
            "mensaje",
            ""
        ).strip()

        archivo = request.FILES.get(
            "archivo"
        )

        print("===================================")
        print("=== ENVÍO MANUAL DESDE CHAT ===")
        print("NÚMERO:", numero)
        print("MODO:", conversacion.modo)
        print("TEXTO:", texto)

        if archivo:
            print("ARCHIVO:", archivo.name)
            print("TIPO:", archivo.content_type)
        else:
            print("ARCHIVO: Ninguno")

        print("===================================")

        # ====================================================
        # 4. SI HAY ARCHIVO
        # ====================================================
        #
        # Si existe archivo + texto:
        #
        # el texto será el caption del archivo.
        #
        # NO enviamos además un mensaje de texto separado.
        # Así evitamos mensajes duplicados.
        # ====================================================

        if archivo:

            media_id = subir_media_whatsapp(
                archivo
            )

            if not media_id:

                print(
                    "ERROR: No se pudo subir "
                    "el archivo a WhatsApp."
                )

            else:

                tipo_archivo = (
                    archivo.content_type or ""
                )

                wa_message_id = None
                mensaje_registro = ""

                # ============================================
                # PDF
                # ============================================

                if tipo_archivo == "application/pdf":

                    print("ENVIANDO PDF...")

                    wa_message_id = (
                        enviar_whatsapp_pdf(
                            numero=numero,
                            media_id=media_id,
                            filename=archivo.name,
                            caption=texto if texto else "",
                        )
                    )

                    mensaje_registro = (
                        texto
                        if texto
                        else f"PDF enviado: {archivo.name}"
                    )

                # ============================================
                # IMAGEN
                # ============================================

                elif tipo_archivo in [
                    "image/jpeg",
                    "image/png",
                    "image/webp",
                ]:

                    print("ENVIANDO IMAGEN...")

                    wa_message_id = (
                        enviar_whatsapp_imagen(
                            numero=numero,
                            media_id=media_id,
                            caption=texto if texto else "",
                        )
                    )

                    mensaje_registro = (
                        texto
                        if texto
                        else f"Imagen enviada: {archivo.name}"
                    )

                # ============================================
                # TIPO NO PERMITIDO
                # ============================================

                else:

                    print(
                        "TIPO DE ARCHIVO NO PERMITIDO:",
                        tipo_archivo
                    )

                # ============================================
                # GUARDAR ARCHIVO EN LA BANDEJA
                # ============================================

                if wa_message_id:

                    # subir_media_whatsapp() pudo haber
                    # avanzado el puntero del archivo.
                    archivo.seek(0)

                    MensajeWhatsApp.objects.create(
                        numero=numero,
                        tipo="SALIENTE",
                        mensaje=mensaje_registro,
                        archivo=archivo,
                        wa_message_id=wa_message_id,
                        estado="ENVIADO",
                    )

                    print(
                        "ARCHIVO GUARDADO EN BANDEJA"
                    )

                    print(
                        "WA_MESSAGE_ID:",
                        wa_message_id
                    )

                else:

                    print(
                        "NO SE GUARDÓ EL ARCHIVO "
                        "COMO ENVIADO PORQUE META "
                        "NO DEVOLVIÓ WA_MESSAGE_ID."
                    )

        # ====================================================
        # 5. SI NO HAY ARCHIVO, PERO HAY TEXTO
        # ====================================================

        elif texto:

            print(
                "ENVIANDO MENSAJE DE TEXTO MANUAL..."
            )

            wa_message_id = enviar_whatsapp_texto(
                numero,
                texto,
                devolver_id=True,
            )

            if wa_message_id:

                MensajeWhatsApp.objects.create(
                    numero=numero,
                    tipo="SALIENTE",
                    mensaje=texto,
                    wa_message_id=wa_message_id,
                    estado="ENVIADO",
                )

                print(
                    "MENSAJE MANUAL GUARDADO"
                )

                print(
                    "WA_MESSAGE_ID:",
                    wa_message_id
                )

            else:

                print(
                    "NO SE PUDO ENVIAR "
                    "EL MENSAJE DE TEXTO."
                )

        # ====================================================
        # 6. POST VACÍO
        # ====================================================

        else:

            print(
                "No hay texto ni archivo para enviar."
            )

        # ====================================================
        # 7. REDIRECCIONAR AL CHAT
        # ====================================================

        return redirect(
            "chat_whatsapp",
            numero=numero
        )

    # ========================================================
    # 8. MARCAR MENSAJES ENTRANTES COMO LEÍDOS EN DJANGO
    # ========================================================

    MensajeWhatsApp.objects.filter(
        numero__in=posibles_numeros,
        tipo="ENTRANTE",
        leido=False
    ).update(
        leido=True
    )

    # ========================================================
    # 9. CARGAR HISTORIAL
    # ========================================================

    mensajes = (
        MensajeWhatsApp.objects
        .filter(
            numero__in=posibles_numeros
        )
        .order_by("creado")
    )

    # ========================================================
    # 10. MOSTRAR CHAT
    # ========================================================

    return render(
        request,
        "whatsapp/chat.html",
        {
            "numero": numero,
            "mensajes": mensajes,
            "conversacion": conversacion,
        }
    )

@login_required
def cambiar_modo_whatsapp(request, numero):
    conversacion, created = ConversacionWhatsApp.objects.get_or_create(
        numero=numero,
        defaults={
            "modo": "BOT",
            "estado": "INICIO",
        }
    )

    if conversacion.modo == "BOT":
        conversacion.modo = "HUMANO"
    else:
        conversacion.modo = "BOT"
        conversacion.estado = "INICIO"

    conversacion.save()

    return redirect("chat_whatsapp", numero=numero)
    

def transferir_a_asesor(numero, texto_original):

    numero = normalizar_numero(numero)

    conversacion, created = ConversacionWhatsApp.objects.get_or_create(
        numero=numero,
        defaults={
            "modo": "BOT",
            "estado": "INICIO",
        }
    )

    # Evitar avisos duplicados si ya está con un asesor
    if conversacion.modo == "HUMANO":
        print("El cliente ya está en modo HUMANO:", numero)
        return

    # Activar atención humana
    conversacion.modo = "HUMANO"
    conversacion.estado = "ASESOR"
    conversacion.save()

    # Avisar al asesor
    try:
        resultado_aviso = avisar_asesor(
            f"🚨 CLIENTE REQUIERE ATENCIÓN HUMANA\n\n"
            f"Cliente WhatsApp: {numero}\n"
            f"Mensaje recibido: {texto_original}\n\n"
            f"Responder lo antes posible."
        )

        print("RESULTADO AVISO ASESOR:", resultado_aviso)

    except Exception as e:
        print("ERROR AVISANDO AL ASESOR:", str(e))

    # Informar al cliente
    enviar_whatsapp_texto_y_guardar(
        numero,
        "Gracias por escribirnos 😊\n\n"
        "Tu solicitud ha sido derivada a nuestro equipo.\n"
        "Un asesor de Óptica IC continuará la atención en breve.\n\n"
        "Para volver al menú principal escribe 0️⃣"
    )


    