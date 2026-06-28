from .models import MensajeWhatsApp, ConversacionWhatsApp
from .openai_client import client
from .prompts import PROMPT_OPTICA_IC


def responder_con_openai(numero, texto_actual):
    ultimos_mensajes = MensajeWhatsApp.objects.filter(
        numero=numero
    ).order_by("-creado")[:15]

    ultimos_mensajes = reversed(list(ultimos_mensajes))

    conversacion = ConversacionWhatsApp.objects.filter(numero=numero).first()

    contexto_modo = conversacion.modo if conversacion else "BOT"
    contexto_estado = conversacion.estado if conversacion else "INICIO"

    mensajes = [
        {
            "role": "system",
            "content": PROMPT_OPTICA_IC,
        },
        {
            "role": "system",
            "content": (
                f"Contexto actual:\n"
                f"- Número WhatsApp: {numero}\n"
                f"- Modo: {contexto_modo}\n"
                f"- Estado: {contexto_estado}\n"
            ),
        },
    ]

    for m in ultimos_mensajes:
        if not m.mensaje:
            continue

        role = "user" if m.tipo == "ENTRANTE" else "assistant"

        mensajes.append({
            "role": role,
            "content": m.mensaje,
        })

    mensajes.append({
        "role": "user",
        "content": texto_actual,
    })

    respuesta = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=mensajes,
        temperature=0.3,
    )

    return respuesta.choices[0].message.content.strip()