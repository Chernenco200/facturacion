from django.shortcuts import render

# Create your views here.
import os
import json

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import ConversacionWhatsApp, CitaWhatsApp
from .utils import enviar_whatsapp_texto, avisar_asesor


VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")


def enviar_menu_principal(numero):
    mensaje = (
        "Hola, somos Óptica IC 👓\n\n"
        "Elige una opción:\n\n"
        "1️⃣ Horario de atención\n"
        "2️⃣ Estado de mi ticket\n"
        "3️⃣ Ubicación\n"
        "4️⃣ Sacar una cita\n"
        "5️⃣ Hablar con un asesor\n\n"
        "0️⃣ Menú principal"
    )
    enviar_whatsapp_texto(numero, mensaje)


def responder_mensaje(numero, texto):
    texto_original = texto.strip()
    texto = texto.lower().strip()

    conversacion, created = ConversacionWhatsApp.objects.get_or_create(
        numero=numero,
        defaults={
            "modo": "BOT",
            "estado": "INICIO",
        }
    )

    # Volver al bot
    if texto in ["0", "0️⃣", "menu", "menú", "menu principal", "menú principal"]:
        conversacion.modo = "BOT"
        conversacion.estado = "INICIO"
        conversacion.save()

        enviar_menu_principal(numero)
        return

    # Si el cliente está en modo humano, el bot no responde
    if conversacion.modo == "HUMANO":
        print(f"Cliente {numero} está en modo HUMANO. Bot no responde.")
        return

    # Si el cliente estaba enviando datos de cita
    if conversacion.estado == "ESPERANDO_DATOS_CITA":
        CitaWhatsApp.objects.create(
            numero=numero,
            datos_cliente=texto_original
        )

        avisar_asesor(
            f"📅 NUEVA SOLICITUD DE CITA\n\n"
            f"Cliente WhatsApp: {numero}\n"
            f"Datos enviados:\n{texto_original}\n\n"
            f"Atender lo antes posible."
        )

        conversacion.modo = "HUMANO"
        conversacion.estado = "ASESOR"
        conversacion.save()

        enviar_whatsapp_texto(
            numero,
            "Gracias 😊 Hemos recibido tus datos para la cita.\n\n"
            "Un asesor de Óptica IC te confirmará la disponibilidad en breve.\n\n"
            "Para volver al menú principal escribe 0️⃣"
        )
        return

    # Saludo / menú
    if texto in [
        "hola",
        "buenas",
        "buenos dias",
        "buenos días",
        "buenas tardes",
        "buenas noches",
    ]:
        conversacion.estado = "INICIO"
        conversacion.save()

        enviar_menu_principal(numero)
        return

    # Horario
    if texto in ["1", "1️⃣"] or "horario" in texto:
        enviar_whatsapp_texto(
            numero,
            "Nuestro horario de atención es de lunes a sábado de 9:00 a.m. a 7:45 p.m."
            " Domingos y feriados de 10:30 a.m. a 6:30 p.m."
        )
        return

    # Estado de ticket
    if texto in ["2", "2️⃣"] or "estado" in texto or "ticket" in texto:
        enviar_whatsapp_texto(
            numero,
            "Para consultar tu ticket escribe:\n\n"
            "TICKET 000123\n\n"
            "Ejemplo: TICKET 000045"
        )
        return

    # Ubicación
    if texto in ["3", "3️⃣"] or "ubicacion" in texto or "ubicación" in texto or "direccion" in texto or "dirección" in texto:
        enviar_whatsapp_texto(
            numero,
            "Estamos ubicados en: Jr Camaná 560 - Cercado de Lima.\n\n"
            "https://www.google.com/search?q=opticas+en+centro+de+lima&sca_esv=0af47fe24a20a796&rlz=1C1GCEA_en&sxsrf=ANbL-n6UHrPkOCqkXS-qJHerJBXMnqBSKw:1781045234179&udm=1&lsack=8pcoaoLWCsGc1sQPs9K2sAM&sa=X&ved=2ahUKEwiCl4zEnvuUAxVBjpUCHTOpDTYQjGp6BAgdEAA&biw=1280&bih=585&dpr=1.5#sv=CAwS-AIKBmxjbF9wdhIbCgNwdnESFENnMHZaeTh4TVdJMmJYQjRhalo0Er4BCgNscWkStgFDaGx2Y0hScFkyRnpJR1Z1SUdObGJuUnlieUJrWlNCc2FXMWhTTnlCLWJxYXFvQ0FDRm9wRUFBWUFCZ0NHQVFpR1c5d2RHbGpZWE1nWlc0Z1kyVnVkSEp2SUdSbElHeHBiV0VxQkFnREVBQ1NBUWh2Y0hScFkybGhicG9CSTBOb1drUlRWV2hPVFVjNWJsTXdWa3BSTUVadVUxVk5lbUZ0VWpGVWJWb3pSVUZGLWdFRUNBQVFTQRJcCgN0YnMSVWxyZjohMm00ITFlMTUhNG0yITE1bTEhMXNoYXNfMXdoZWVsY2hhaXJfMWFjY2Vzc2libGVfMWVudHJhbmNlITJtMSExZTIhMm0xITFlMyEzc0lBRT0SHgoBcRIZb3B0aWNhcyBlbiBjZW50cm8gZGUgbGltYRoSbG9jYWwtcGxhY2Utdmlld2VyGAog29rHXA"
        )
        return

    # Sacar cita
    if texto in ["4", "4️⃣"] or "cita" in texto:
        conversacion.estado = "ESPERANDO_DATOS_CITA"
        conversacion.save()

        enviar_whatsapp_texto(
            numero,
            "Claro 😊 Para separar una cita, envíanos en un solo mensaje:\n\n"
            "1. Nombre completo\n"
            "2. Día deseado\n"
            "3. Hora aproximada\n"
            "4. Motivo de consulta\n\n"
            "Ejemplo:\n"
            "Juan Pérez, martes 5:00 p.m., medida de vista"
        )
        return

    # Hablar con asesor
    if texto in ["5", "5️⃣"] or "asesor" in texto or "persona" in texto:
        avisar_asesor(
            f"🚨 CLIENTE SOLICITA ASESOR\n\n"
            f"Cliente WhatsApp: {numero}\n"
            f"Mensaje recibido: {texto_original}\n\n"
            f"Responder lo antes posible."
        )

        conversacion.modo = "HUMANO"
        conversacion.estado = "ASESOR"
        conversacion.save()

        enviar_whatsapp_texto(
            numero,
            "Un asesor de Óptica IC te atenderá en breve.\n\n"
            "Para volver al menú principal escribe 0️⃣"
        )
        return

    enviar_whatsapp_texto(
        numero,
        "No entendí tu mensaje.\n\n"
        "Escribe MENÚ para ver las opciones disponibles."
    )


@csrf_exempt
def whatsapp_webhook(request):
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        if mode == "subscribe" and token == VERIFY_TOKEN:
            return HttpResponse(challenge)

        return HttpResponse("Token inválido", status=403)

    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))

            print("===================================")
            print("WHATSAPP RECIBIDO")
            print(data)
            print("===================================")

            value = data["entry"][0]["changes"][0]["value"]
            messages = value.get("messages", [])

            if messages:
                message = messages[0]
                numero = message["from"]
                tipo = message.get("type")

                if tipo == "text":
                    texto = message["text"]["body"]
                    responder_mensaje(numero, texto)

        except Exception as e:
            print("ERROR WEBHOOK:", e)

        return JsonResponse({"status": "ok"})

    return HttpResponse("Método no permitido", status=405)