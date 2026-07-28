import os
import requests

from django.utils import timezone
from datetime import timedelta
from .models import ConversacionWhatsApp, MensajeWhatsApp

from django.conf import settings

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

def enviar_whatsapp_texto(numero, mensaje):
    access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")

    # Guardamos el número tal como llega a la función
    numero_original = numero

    try:
        numero = normalizar_numero(numero)
    except ValueError as e:
        print("ERROR NÚMERO:", e)
        return False

    print("===================================")
    print("ENVIANDO MENSAJE WHATSAPP")
    print("Número original:", numero_original)
    print("Número normalizado:", numero)
    print("Mensaje:", mensaje)
    print("===================================")

    if not numero:
        print("ERROR: número vacío")
        return False

    # Validación adicional
    if not (numero.startswith("51") and len(numero) == 11):
        print(f"ERROR: número inválido -> {numero}")
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

    # Esto muestra exactamente el JSON que se envía a Meta
    print("JSON ENVIADO A META:", data)

    response = requests.post(url, headers=headers, json=data)

    print("WHATSAPP STATUS:", response.status_code)
    print("WHATSAPP RESPUESTA:", response.text)

    return response.status_code in [200, 201]


def enviar_whatsapp_template(numero, template_name, parametros):
    access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")

    try:
        numero = normalizar_numero(numero)
    except ValueError as e:
        print("ERROR NÚMERO TEMPLATE:", e)
        return False

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
                        {"type": "text", "text": str(p)}
                        for p in parametros
                    ]
                }
            ]
        }
    }

    response = requests.post(url, headers=headers, json=data)

    print("TEMPLATE:", template_name)
    print("NUMERO TEMPLATE:", numero)
    print("STATUS TEMPLATE:", response.status_code)
    print("RESPUESTA TEMPLATE:", response.text)

    return response.status_code in [200, 201]

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
    cliente = ticket.cliente

    if not cliente or not cliente.telefono:
        print("Cliente sin teléfono. No se envía WhatsApp.")
        return False

    numero = normalizar_numero(cliente.telefono)

    mensaje = (
        f"Hola {cliente.nombre} 😊\n\n"
        f"Gracias por tu compra en Óptica IC.\n\n"
        f"Tu N° de ticket para que puedas hacer seguimiento es: {ticket.numero}\n\n"
        f"Tu pedido pasará por estas etapas:\n"
        f"1️⃣ En laboratorio\n"
        f"2️⃣ En taller de Biselado\n"
        f"3️⃣ Control de calidad\n"
        f"4️⃣ Listo para recoger ✅\n\n"
        f"Puedes consultar el estado de tu ticket escribiendo Menú a este número y seleccionando la opción 2.\n\n"
        f"Óptica IC\n"
        f"Innovación y Calidad"
    )

    if cliente_esta_en_ventana_servicio(numero):
        enviado = enviar_whatsapp_texto(numero, mensaje)
    else:
        enviado = enviar_whatsapp_template(
            numero=numero,
            template_name="agradecimiento",
            parametros=[
                cliente.nombre,
                str(ticket.numero).zfill(6),
            ],
        )

    if enviado:
        MensajeWhatsApp.objects.create(
            numero=numero,
            tipo="BOT",
            mensaje=mensaje,
        )

    return enviado

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

    mensaje = (
        f"Hola {cliente.nombre} 😊\n\n"
        f"Esperamos que estés disfrutando tus nuevos lentes de Óptica IC.\n\n"
        f"Podrías confirmarnos con un like si todo va bien\n\n"
    )

    if cliente_esta_en_ventana_servicio(cliente.telefono):
        enviado = enviar_whatsapp_texto(cliente.telefono, mensaje)
    else:
        enviado = enviar_whatsapp_template(
            numero=cliente.telefono,
            template_name="encuesta_7_dias",
            parametros=[cliente.nombre],
        )

    if enviado:
        MensajeWhatsApp.objects.create(
            numero=cliente.telefono,
            tipo="BOT",
            mensaje=mensaje,
        )

        conversacion, created = ConversacionWhatsApp.objects.get_or_create(
            numero=cliente.telefono,
            defaults={
                "modo": "BOT",
                "estado": "ESPERANDO_ENCUESTA",
            }
        )

        conversacion.modo = "BOT"
        conversacion.estado = "ESPERANDO_ENCUESTA"
        conversacion.save()

    return enviado

def enviar_control_menor_6_meses(orden):
    ticket = orden.ticket
    cliente = ticket.cliente

    if not cliente or not cliente.telefono:
        return False

    mensaje = (
        f"Hola {cliente.nombre} 😊\n\n"
        f"Te recordamos que hoy se cumplen 6 meses desde que adquiriste lentes con nosotros.\n\n"
        f"Puedes escribir 'Cita' para separar una cita de control. "
        f"Recuerda que en menores es recomendable realizar evaluaciones semestrales.\n\n"
        f"Óptica IC\n"
        f"Innovación y Calidad"
    )

    if cliente_esta_en_ventana_servicio(cliente.telefono):
        enviado = enviar_whatsapp_texto(cliente.telefono, mensaje)
    else:
        enviado = enviar_whatsapp_template(
            numero=cliente.telefono,
            template_name="control_6_meses",
            parametros=[cliente.nombre],
        )

    if enviado:
        MensajeWhatsApp.objects.create(
            numero=cliente.telefono,
            tipo="BOT",
            mensaje=mensaje,
        )

    return enviado

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

    files = {
        "file": (
            archivo.name,
            archivo,
            "application/pdf"
        )
    }

    data = {
        "messaging_product": "whatsapp",
        "type": "application/pdf",
    }

    response = requests.post(
        url,
        headers=headers,
        files=files,
        data=data,
        timeout=30
    )

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

    return response.status_code in [200, 201]


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


def enviar_reactivacion_whatsapp(request, cliente_id):
    cliente = get_object_or_404(
        Cliente,
        id=cliente_id,
    )

    if request.method != "POST":
        return redirect("seguimiento_whatsapp")

    if not cliente.telefono:
        messages.error(
            request,
            f"El cliente {cliente.nombre or 'seleccionado'} "
            f"no tiene teléfono registrado."
        )
        return redirect("seguimiento_whatsapp")

    nombre = (cliente.nombre or "Cliente").strip()
    numero = str(cliente.telefono).strip()

    # Obtener el monto enviado desde la lista.
    monto_recibido = (
        request.POST.get("monto_maximo", "0")
        .strip()
        .replace(",", ".")
    )

    try:
        monto_maximo = Decimal(monto_recibido)
    except (InvalidOperation, TypeError, ValueError):
        monto_maximo = Decimal("0.00")

    # Calcular la categoría en el servidor.
    categoria = obtener_categoria_reactivacion(
        monto_maximo
    )

    # Elegir la plantilla y el texto que se verá
    # dentro de la bandeja interna de Django.
    if categoria in ["BLUE", "BLACK"]:
        template_name = "reactivacion_clientes_premium"

        mensaje_bandeja = (
            f"Hola {nombre} 👋\n\n"
            f"En Óptica IC queremos agradecerte por haber confiado "
            f"en nosotros. Gracias a clientes como tú seguimos "
            f"creciendo cada día.\n\n"
            f"Nos encantaría volver a atenderte y acompañarte en el "
            f"cuidado de tu salud visual. Si ya es momento de renovar "
            f"tus lentes o realizar un nuevo examen visual, estaremos "
            f"felices de recibirte nuevamente.\n\n"
            f"Como uno de nuestros clientes preferentes, queremos "
            f"brindarte una atención personalizada para ayudarte a "
            f"encontrar la mejor solución para tu visión.\n\n"
            f"📍 Jr. Camaná 560, Cercado de Lima.\n\n"
            f"Botones:\n"
            f"• Reservar cita\n"
            f"• Hablar con un asesor\n"
            f"• Ver promociones\n\n"
            f"Óptica IC\n"
            f"Innovación y Calidad"
        )

    else:
        template_name = "reactivacion_clientes"

        mensaje_bandeja = (
            f"Hola {nombre} 👋\n\n"
            f"Ha pasado un tiempo desde tu última visita a "
            f"Óptica IC.\n\n"
            f"Queremos invitarte a realizar un nuevo control visual "
            f"y evaluar si ya es momento de renovar tus lentes.\n\n"
            f"Será un gusto volver a atenderte.\n\n"
            f"📍 Jr. Camaná 560, Cercado de Lima.\n\n"
            f"Botones:\n"
            f"• Reservar cita\n"
            f"• Hablar con un asesor\n"
            f"• Ver promociones\n\n"
            f"Óptica IC\n"
            f"Innovación y Calidad"
        )

    try:
        # En reactivación siempre se usa plantilla,
        # porque son clientes sin conversación reciente.
        enviado = enviar_whatsapp_template(
            numero=numero,
            template_name=template_name,
            parametros=[
                nombre,
            ],
        )

        if not enviado:
            messages.error(
                request,
                f"Meta no aceptó el mensaje para {nombre}. "
                f"Revisa el teléfono y la plantilla "
                f"'{template_name}'."
            )
            return redirect("seguimiento_whatsapp")

        # Meta aceptó el envío. Ahora registramos
        # todos los cambios locales en una transacción.
        with transaction.atomic():

            # Registrar el mensaje para mostrarlo
            # dentro de /whatsapp/bandeja/
            MensajeWhatsApp.objects.create(
                numero=numero,
                nombre=nombre,
                tipo="SALIENTE",
                mensaje=mensaje_bandeja,
                leido=True,
            )

            # Crear o actualizar la conversación.
            # BOT/HUMANO corresponde a ConversacionWhatsApp.modo,
            # no a MensajeWhatsApp.tipo.
            conversacion, creada = (
                ConversacionWhatsApp.objects.get_or_create(
                    numero=numero,
                    defaults={
                        "modo": "BOT",
                        "estado": "INICIO",
                    },
                )
            )

            conversacion.modo = "BOT"
            conversacion.estado = "INICIO"
            conversacion.save(
                update_fields=[
                    "modo",
                    "estado",
                    "actualizado",
                ]
            )

            # Registrar el historial de reactivación.
            ReactivacionWhatsApp.objects.create(
                cliente=cliente,
                categoria=categoria,
                monto_maximo=monto_maximo,
            )

            # Esta fecha permitirá retirar al cliente
            # de la lista de reactivación.
            cliente.fecha_ultima_reactivacion = (
                timezone.localdate()
            )
            cliente.save(
                update_fields=[
                    "fecha_ultima_reactivacion",
                ]
            )

        messages.success(
            request,
            f"Mensaje de reactivación enviado a {nombre} "
            f"con la plantilla '{template_name}'."
        )

    except Exception as e:
        print("ERROR ENVIANDO REACTIVACIÓN:", repr(e))

        messages.error(
            request,
            f"Error enviando la reactivación: {e}"
        )

    return redirect("seguimiento_whatsapp")