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
            "Hola 👋 Bienvenido a Óptica IC.\n\n"
            "Elige una opción:\n\n"
            "1️⃣ Horario de atención\n"
            "2️⃣ Estado de mi ticket\n"
            "3️⃣ Ubicación\n"
            "4️⃣ Sacar una cita\n"
            "5️⃣ Hablar con un asesor"
        )
        enviar_whatsapp_texto(numero, mensaje)
        return

    if texto == "1" or "horario" in texto:
        enviar_whatsapp_texto(
            numero,
            "Nuestro horario de atención es de lunes a sábado de 9:00 a.m. a 7:45 p.m."
            "y domingos y feriados de 10:30 am a 6:30 pm"
        )
        return

    if texto == "3" or "ubicacion" in texto or "ubicación" in texto:
        enviar_whatsapp_texto(
            numero,
            "Estamos ubicados en: Jr. Camaná 560 - Cercado de Lima\n\n"
            "Google Maps: https://www.google.com/maps/dir//%C3%93ptica+IC,+Jr.+Caman%C3%A1+560,+Lima+15001/@-12.0478674,-77.0366906,17z/data=!4m16!1m7!3m6!1s0x9105c8c9f0be65c7:0xa08a1286e936afe0!2s%C3%93ptica+IC!8m2!3d-12.0478674!4d-77.0341157!16s%2Fg%2F11b6mpxj6x!4m7!1m0!1m5!1m1!1s0x9105c8c9f0be65c7:0xa08a1286e936afe0!2m2!1d-77.0341157!2d-12.0478674?entry=ttu&g_ep=EgoyMDI2MDYwMy4xIKXMDSoASAFQAw%3D%3D"
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
            "T000123\n\n"
            "Ejemplo: T00045"
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