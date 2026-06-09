import os
import requests


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

def avisar_asesor(mensaje):
    numero_asesor = os.environ.get("NUMERO_ASESOR_WHATSAPP")

    if not numero_asesor:
        print("No existe NUMERO_ASESOR_WHATSAPP")
        return False

    return enviar_whatsapp_texto(numero_asesor, mensaje)