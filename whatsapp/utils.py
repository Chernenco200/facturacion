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

    return enviar_whatsapp_texto(cliente.telefono, mensaje)


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

    return enviar_whatsapp_texto(cliente.telefono, mensaje)