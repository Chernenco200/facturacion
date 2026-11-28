from datetime import timedelta

from django.utils import timezone

from .models import ConversacionWhatsApp, MensajeWhatsApp, numero_normalizado
from .openai_client import client
from .prompts import PROMPT_OPTICA_IC

MAX_MENSAJES_HISTORIAL = 20
DIAS_HISTORIAL = 60
PAUSA_RELEVANTE = timedelta(hours=6)


def _variantes(numero):
    """El mismo celular guardado con o sin 51 (mensajes antiguos)."""
    n = numero_normalizado(numero)
    variantes = {numero, n}
    if n.startswith("51") and len(n) == 11:
        variantes.add(n[2:])
    return list(variantes)


def _ahora_lima():
    from zoneinfo import ZoneInfo

    return timezone.now().astimezone(ZoneInfo("America/Lima"))


def _describir_pausa(delta):
    horas = delta.total_seconds() / 3600
    if horas < 24:
        return f"{int(horas)} horas"
    return f"{int(horas // 24)} días"


def contexto_cliente(numero):
    """
    Datos del propio cliente que escribe (identificado por su celular):
    nombre y pedidos en curso. Solo se usan para responderle a él.
    """
    try:
        from core.models import Cliente, OrdenTrabajo

        n = numero_normalizado(numero)
        nueve = n[2:] if n.startswith("51") else n
        clientes = list(Cliente.objects.filter(telefono__in=[nueve, n, "+" + n])[:3])
        if not clientes:
            return "No se encontró un cliente registrado con este número."

        lineas = [f"Nombre registrado: {clientes[0].nombre}"]
        ordenes = (
            OrdenTrabajo.objects.select_related("ticket")
            .filter(ticket__cliente__in=clientes)
            .exclude(estado="ENTREGADO")
            .order_by("-ticket__fecha_emision")[:3]
        )
        if ordenes:
            lineas.append("Pedidos en curso (del sistema, confiables):")
            for o in ordenes:
                t = o.ticket
                entrega = " ".join(filter(None, [t.fecha_entrega, t.hora_entrega])) or "sin fecha registrada"
                lineas.append(
                    f"- Ticket {t.numero}: {o.estado_publico()} · entrega prometida: {entrega}"
                )
        else:
            lineas.append("No tiene pedidos pendientes de entrega.")
        return "\n".join(lineas)
    except Exception as error:  # el bot sigue funcionando sin este contexto
        print("CONTEXTO CLIENTE NO DISPONIBLE:", error)
        return "Datos del cliente no disponibles en este momento."


def contexto_horario():
    ahora = _ahora_lima()
    texto = f"Fecha y hora actual en Lima: {ahora:%A %d/%m/%Y %H:%M}."
    try:
        from incentivos.horario import es_feriado, tienda_abierta

        abierta, proxima = tienda_abierta()
        texto += " La tienda está ABIERTA ahora." if abierta else f" La tienda está CERRADA ahora; abre {proxima}."
        if es_feriado(ahora.date()):
            texto += " Hoy es feriado (horario 10:30 a. m. a 6:00 p. m.)."
    except Exception:
        pass
    return texto


def responder_con_openai(numero, texto_actual):

    numero = str(numero).strip()
    texto_actual = (texto_actual or "").strip()

    # =====================================================
    # 1. OBTENER CONVERSACIÓN
    # =====================================================

    conversacion = ConversacionWhatsApp.objects.filter(
        numero__in=_variantes(numero)
    ).first()

    contexto_modo = conversacion.modo if conversacion else "BOT"
    contexto_estado = conversacion.estado if conversacion else "INICIO"

    # =====================================================
    # 2. OBTENER HISTORIAL
    # =====================================================
    # Se busca con y sin 51: antes los avisos de "lentes listos" y algunas
    # plantillas se guardaban sin 51 y el bot no los veía.

    ultimos_mensajes = list(
        MensajeWhatsApp.objects.filter(
            numero__in=_variantes(numero),
            creado__gte=timezone.now() - timedelta(days=DIAS_HISTORIAL),
        ).order_by("-creado", "-pk")[:MAX_MENSAJES_HISTORIAL]
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
                f"Estado actual: {contexto_estado}\n"
                f"{contexto_horario()}\n\n"

                "DATOS DEL CLIENTE QUE ESCRIBE (por su número de celular):\n"
                f"{contexto_cliente(numero)}\n\n"

                "INSTRUCCIONES DE CONTEXTO:\n"

                "1. Analiza los mensajes anteriores antes de responder.\n"

                "2. Si el cliente responde a una pregunta realizada "
                "anteriormente por Óptica IC, interpreta su respuesta "
                "en relación con esa pregunta.\n"

                "3. No interpretes cada mensaje como una nueva "
                "conversación. Las notas del sistema indican cuánto "
                "tiempo pasó entre mensajes: si pasaron días, el cliente "
                "puede estar iniciando un tema nuevo.\n"

                "4. Si el cliente responde con 👍, 👌, 😊, "
                "'todo bien', 'sí' o expresiones similares, "
                "revisa qué le preguntó previamente la óptica.\n"

                "5. Si la óptica preguntó si está disfrutando sus "
                "lentes y el cliente confirma que todo está bien, "
                "agradece brevemente la confirmación.\n"

                "6. No envíes saludos de bienvenida cuando el "
                "cliente está respondiendo un mensaje anterior.\n"

                "7. Si el cliente pregunta por sus lentes o su pedido y "
                "en DATOS DEL CLIENTE hay pedidos en curso, respóndele "
                "directamente con ese estado y la fecha prometida. Si no "
                "hay pedidos o no se encontró al cliente, devuelve "
                "[INTENCION:ESTADO_TICKET].\n"

                "8. No repitas información que ya fue proporcionada.\n"

                "9. Si el cliente solicita atención humana o no "
                "puedes resolver su consulta con seguridad, "
                "devuelve únicamente [ASESOR].\n"

                "10. Si detectas una intención de Django, devuelve "
                "únicamente la etiqueta correspondiente.\n"

                "11. Nunca inventes información sobre tickets, "
                "pedidos, precios ni disponibilidad.\n"

                "12. Puedes llamar al cliente por su primer nombre "
                "registrado, sin abusar.\n"
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

    anterior = None
    for indice, m in enumerate(ultimos_mensajes):

        if indice == indice_actual:
            continue

        if not m.mensaje:
            continue

        if anterior is not None and m.creado - anterior > PAUSA_RELEVANTE:
            mensajes.append({
                "role": "system",
                "content": f"(Pasaron {_describir_pausa(m.creado - anterior)} sin mensajes.)",
            })
        anterior = m.creado

        role = "user" if m.tipo == "ENTRANTE" else "assistant"

        mensajes.append({
            "role": role,
            "content": m.mensaje,
        })

    if anterior is not None and timezone.now() - anterior > PAUSA_RELEVANTE:
        mensajes.append({
            "role": "system",
            "content": f"(El cliente vuelve a escribir después de {_describir_pausa(timezone.now() - anterior)}.)",
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
    print("ESTADO:", contexto_estado)
    print("MENSAJES ENVIADOS:", len(mensajes))
    print("RESPUESTA:", respuesta_texto)

    return respuesta_texto
