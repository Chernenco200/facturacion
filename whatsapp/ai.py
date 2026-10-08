from .models import MensajeWhatsApp, ConversacionWhatsApp
from .openai_client import client
from .prompts import PROMPT_OPTICA_IC


def responder_con_openai(numero, texto_actual):

    numero = normalizar_numero(numero)
    texto_actual = (texto_actual or "").strip()

    # =====================================================
    # 1. OBTENER CONVERSACIÓN
    # =====================================================

    conversacion = ConversacionWhatsApp.objects.filter(
        numero=numero
    ).first()

    contexto_modo = conversacion.modo if conversacion else "BOT"
    contexto_estado = conversacion.estado if conversacion else "INICIO"

    # =====================================================
    # 2. OBTENER HISTORIAL
    # =====================================================

    ultimos_mensajes = list(
        MensajeWhatsApp.objects.filter(
            numero=numero
        ).order_by("-creado", "-pk")[:15]
    )

    ultimos_mensajes.reverse()

    # =====================================================
    # 3. CONSTRUIR CONTEXTO
    # =====================================================

    mensajes = [
        {
            "role": "system",
            "content": PROMPT_OPTICA_IC,
        },
        {
            "role": "system",
            "content": (
                "CONTEXTO DE LA CONVERSACIÓN\n"
                f"Modo actual: {contexto_modo}\n"
                f"Estado actual: {contexto_estado}\n\n"

                "INSTRUCCIONES DE CONTEXTO:\n"

                "1. Analiza los mensajes anteriores antes de responder.\n"

                "2. Si el cliente responde a una pregunta realizada "
                "anteriormente por Óptica IC, interpreta su respuesta "
                "en relación con esa pregunta.\n"

                "3. No interpretes cada mensaje como una nueva "
                "conversación.\n"

                "4. Si el cliente responde con 👍, 👌, 😊, "
                "'todo bien', 'sí' o expresiones similares, "
                "revisa qué le preguntó previamente la óptica.\n"

                "5. Si la óptica preguntó si está disfrutando sus "
                "lentes y el cliente confirma que todo está bien, "
                "agradece brevemente la confirmación.\n"

                "6. No envíes saludos de bienvenida cuando el "
                "cliente está respondiendo un mensaje anterior.\n"

                "7. No digas 'bienvenido de nuevo' salvo que "
                "realmente corresponda iniciar una nueva conversación.\n"

                "8. No repitas información que ya fue proporcionada.\n"

                "9. Si el cliente solicita atención humana o no "
                "puedes resolver su consulta con seguridad, "
                "devuelve únicamente [ASESOR].\n"

                "10. Si detectas una intención de Django, devuelve "
                "únicamente la etiqueta correspondiente.\n"

                "11. Nunca inventes información sobre tickets, "
                "pedidos, precios ni disponibilidad.\n"
            ),
        },
    ]

    # =====================================================
    # 4. INCORPORAR MENSAJES ANTERIORES
    # =====================================================

    # Evitar duplicar el mensaje actual si ya fue guardado
    # por el webhook como último mensaje entrante.

    indice_actual = None

    if ultimos_mensajes:
        ultimo = ultimos_mensajes[-1]

        if (
            ultimo.tipo == "ENTRANTE"
            and (ultimo.mensaje or "").strip() == texto_actual
        ):
            indice_actual = len(ultimos_mensajes) - 1

    for indice, m in enumerate(ultimos_mensajes):

        if indice == indice_actual:
            continue

        if not m.mensaje:
            continue

        role = "user" if m.tipo == "ENTRANTE" else "assistant"

        mensajes.append({
            "role": role,
            "content": m.mensaje,
        })

    # =====================================================
    # 5. AGREGAR MENSAJE ACTUAL UNA SOLA VEZ
    # =====================================================

    mensajes.append({
        "role": "user",
        "content": texto_actual,
    })

    # =====================================================
    # 6. CONSULTAR OPENAI
    # =====================================================

    respuesta = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=mensajes,
        temperature=0.2,
        max_tokens=250,
    )

    respuesta_texto = (
        respuesta.choices[0].message.content or ""
    ).strip()

    print("=== OPENAI CONTEXTO ===")
    print("NUMERO:", numero)
    print("ESTADO:", contexto_estado)
    print("MENSAJES ENVIADOS:", len(mensajes))
    print("RESPUESTA:", respuesta_texto)

    return respuesta_texto