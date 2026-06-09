from django.shortcuts import render

# Create your views here.
import os
import json

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .utils import enviar_whatsapp_texto


VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")


def responder_mensaje(numero, texto):
    texto = texto.lower().strip()

    if texto in ["hola", "buenas", "menu", "menú"]:
        mensaje = (
            "Hola, somos Óptica IC 👓\n\n"
            "Elige una opción:\n\n"
            "1. Horario de atención\n"
            "2. Estado de mi ticket\n"
            "3. Ubicación\n"
            "4. Sacar una cita\n"
            "5. Hablar con un asesor"
        )
        enviar_whatsapp_texto(numero, mensaje)
        return

    if texto == "1" or "horario" in texto:
        enviar_whatsapp_texto(
            numero,
            "Nuestro horario de atención es de lunes a sábado de 9:00 a.m. a 8:00 p.m."
        )
        return

    if texto == "3" or "ubicacion" in texto or "ubicación" in texto:
        enviar_whatsapp_texto(
            numero,
            "Estamos ubicados en: COLOCA AQUÍ TU DIRECCIÓN.\n\n"
            "Google Maps: COLOCA AQUÍ TU LINK."
        )
        return

    if texto == "4" or "cita" in texto:
        enviar_whatsapp_texto(
            numero,
            "Claro 😊 Para separar una cita, envíanos:\n\n"
            "1. Nombre completo\n"
            "2. Día deseado\n"
            "3. Hora aproximada\n"
            "4. Motivo de consulta"
        )
        return

    if texto == "5" or "asesor" in texto:
        enviar_whatsapp_texto(
            numero,
            "Un asesor de Óptica IC te atenderá en breve."
        )
        return

    if texto == "2" or "ticket" in texto or "estado" in texto:
        enviar_whatsapp_texto(
            numero,
            "Para consultar tu ticket escribe:\n\n"
            "TICKET 000123\n\n"
            "Ejemplo: TICKET 000045"
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
        data = json.loads(request.body.decode("utf-8"))

        print("===================================")
        print("WHATSAPP RECIBIDO")
        print(data)
        print("===================================")

        try:
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