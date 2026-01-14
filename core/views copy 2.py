import requests  # <--- añade esto

from django.shortcuts import render, redirect
from .models import Venta, Producto, Gasto, Venta, MedidaVista, Cliente, TipoLunas, ReciboCorrelativo, TicketVenta, DetalleTicketVenta
from .forms import ClienteForm, MedidaVistaForm, TipoLunasForm, ProductoForm
from django.shortcuts import get_object_or_404

from django.http import JsonResponse
from django.db.models import Q

from django.views.decorators.csrf import csrf_exempt
import json
from datetime import datetime

from django.http import HttpResponse
from django.template.loader import render_to_string
import io
from xhtml2pdf import pisa

from django.utils import timezone


from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import mm
from io import BytesIO

import os


from reportlab.lib.units import mm
from django.conf import settings

from django.db import transaction


from decimal import Decimal

from django.db.models import Max

from django.views.decorators.http import require_http_methods

def index(request):
    return render(request, 'core/index.html')

def lista_ventas(request):
    ventas = Venta.objects.all()
    return render(request, 'core/ventas.html', {'ventas': ventas})

def registrar_cliente(request):
    """
    Vista integral:
    - POST + name="buscar_cliente": busca por DNI y prellena formularios.
    - POST + name="guardar_cliente": crea o ACTUALIZA Cliente por DNI; guarda Medida/Lunas si se llenaron.
    - GET: muestra formularios vacíos.
    """
    cliente = None
    medida = None
    ultima_luna = None

    # ---------- BUSCAR POR DNI ----------
    if request.method == 'POST' and 'buscar_cliente' in request.POST:
        dni = (request.POST.get('DNI') or '').strip()
        cliente = Cliente.objects.filter(DNI=dni).last()

        if cliente:
            cliente_form = ClienteForm(instance=cliente)
            medida = MedidaVista.objects.filter(cliente=cliente).last()
            medida_form = MedidaVistaForm(instance=medida) if medida else MedidaVistaForm()
            ultima_luna = TipoLunas.objects.filter(cliente=cliente).last()
            tipo_lunas_form = TipoLunasForm(instance=ultima_luna) if ultima_luna else TipoLunasForm()
        else:
            # Si no existe, prellenamos el DNI para que el usuario complete y guarde
            cliente_form = ClienteForm(initial={'DNI': dni})
            medida_form = MedidaVistaForm()
            tipo_lunas_form = TipoLunasForm()

    # ---------- GUARDAR (CREAR / ACTUALIZAR POR DNI) ----------
    elif request.method == 'POST' and 'guardar_cliente' in request.POST:
        dni_post = (request.POST.get('DNI') or '').strip()

        # Si el DNI existe, actualiza ese registro; si no, crea uno nuevo
        instancia_cliente = Cliente.objects.filter(DNI=dni_post).last() if dni_post else None

        cliente_form = ClienteForm(request.POST, instance=instancia_cliente)
        medida_form = MedidaVistaForm(request.POST)
        tipo_lunas_form = TipoLunasForm(request.POST)

        if cliente_form.is_valid():
            cliente = cliente_form.save()  # crea o actualiza

            # --- Guardar Medida si hay al menos un dato y el form es válido ---
            if medida_form.is_valid():
                # ¿El usuario llenó algo? (excluimos 'cliente' si no está en el form)
                campos_utiles = [f for f in medida_form.fields if f != 'cliente']
                hay_datos = any(
                    medida_form.cleaned_data.get(f) not in (None, '', 0) 
                    for f in campos_utiles
                )
                if hay_datos:
                    medida = medida_form.save(commit=False)
                    medida.cliente = cliente
                    medida.save()


            # Guarda Tipo de Lunas SOLO si el usuario llenó algo y pasa validación
            if tipo_lunas_form.has_changed() and tipo_lunas_form.is_valid():
                luna = tipo_lunas_form.save(commit=False)
                luna.cliente = cliente
                luna.save()

            # Limpia los formularios para nueva entrada
            return redirect('registrar_cliente')

        # Si Cliente tiene errores, re-render con errores (no bloqueamos por Medida/Lunas)

    # ---------- GET INICIAL ----------
    else:
        cliente_form = ClienteForm()
        medida_form = MedidaVistaForm()
        tipo_lunas_form = TipoLunasForm()

    # ---------- Listados inferiores (para tu tabla/lista) borrar cuando todo esté listo----------
    clientes = Cliente.objects.all()
    medidas = MedidaVista.objects.select_related('cliente').all()

    return render(request, 'core/registro_cliente2.html', {
        'cliente_form': cliente_form,
        'medida_form': medida_form,
        'tipo_lunas_form': tipo_lunas_form,
        'cliente': cliente,
        'medida': medida,
        'ultima_luna': ultima_luna,
        'clientes': clientes,
        'medidas': medidas,
        'producto_form': ProductoForm(),
    })

def crear_producto(request):
    if request.method == 'POST':
        producto_id = request.POST.get('producto_id')
        if producto_id:
            producto = get_object_or_404(Producto, pk=producto_id)
            form = ProductoForm(request.POST, instance=producto)
        else:
            form = ProductoForm(request.POST)

        if form.is_valid():
            form.save()
            return redirect('lista_compras')
    else:
        form = ProductoForm()
    
    compras = Producto.objects.all()
    return render(request, 'core/compras.html', {'producto_form': form, 'compras': compras})


def lista_compras(request):
    compras = Producto.objects.all()
    producto_form = ProductoForm()  # instancia vacía del formulario
    return render(request, 'core/compras.html', {
        'compras': compras,
        'producto_form': producto_form
    })


def editar_producto(request, pk):
    producto = get_object_or_404(Producto, pk=pk)
    if request.method == 'POST':
        form = ProductoForm(request.POST, instance=producto)
        if form.is_valid():
            form.save()
            return redirect('lista_compras')  # Redirige a donde muestra la lista
    else:
        form = ProductoForm(instance=producto)
    return render(request, 'core/compras.html', {'form': form})

def eliminar_producto(request, pk):
    producto = get_object_or_404(Producto, pk=pk)
    if request.method == 'POST':
        producto.delete()
        return redirect('lista_compras')
    return render(request, 'core/confirmar_eliminar.html', {'producto': producto})



def buscar_codigos(request):
    q = request.GET.get("q", "")
    productos = Producto.objects.filter(cod__icontains=q)
    data = list(productos.values("cod"))
    return JsonResponse(data, safe=False
    )


def detalle_producto_por_codigo(request):
    cod = request.GET.get("cod", "")
    try:
        producto = Producto.objects.get(cod=cod)
        data = {
            "descripcion": producto.descripcion,
            "precio_venta": producto.precio_venta,
            "precio_compra": producto.precio_compra,
            "stock": producto.stock,
            "tipo": producto.tipo,
        }
    except Producto.DoesNotExist:
        data = {}
    return JsonResponse(data)




from io import BytesIO
from django.http import HttpResponse
from django.conf import settings
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import mm
from reportlab.lib.utils import ImageReader
import os, json
from datetime import datetime
import textwrap

def generar_ticket_pdf(request):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=(90 * mm, 270 * mm))

    # Datos recibidos
    cliente = request.GET.get('cliente', 'Cliente no definido')
    telefono = request.GET.get('telefono', '')
    vendedor = request.GET.get('vendedor', '')
    fecha_sistema = request.GET.get('fecha_sistema', datetime.now().strftime('%d/%m/%Y'))
    hora_sistema = request.GET.get('hora_sistema', datetime.now().strftime('%H:%M'))
    fecha_entrega = request.GET.get('fecha_entrega', datetime.now().strftime('%d/%m/%Y'))
    hora_entrega = request.GET.get('hora_entrega', '--:--')

    a_cuenta = request.GET.get('a_cuenta', '0.00')
    saldo = request.GET.get('saldo', '0.00')
    total = request.GET.get('total', '0.00')



    detalles_json = request.GET.get('detalles', '[]')
    detalles = json.loads(detalles_json)

    fecha_actual = datetime.now().strftime('%d/%m/%Y')
    total = 0
 
    y = 250  # margen superior

    # Cargar y centrar logo
    ruta_logo = os.path.join(settings.MEDIA_ROOT, 'img', 'logo.png')
    if os.path.exists(ruta_logo):
        logo = ImageReader(ruta_logo)
        ancho_logo = 90  # en puntos
        alto_logo = 35
        x_centro = (90 * mm - ancho_logo) / 2
        p.drawImage(logo, x_centro, y * mm, width=ancho_logo, height=alto_logo, preserveAspectRatio=True)
        y -= 12  # espacio tras el logo
    else:
        p.setFont("Helvetica-Bold", 11)
        p.drawCentredString(45 * mm, y * mm, "OPTICA IC")
        y -= 8

    # --- Número de Ticket (añadido mínimo) ---
    # Opción A: te llega por querystring ?numero=123  (recomendado)
    numero = request.GET.get('numero')

    # Opción B (fallback): si no llegó, usa el último id guardado en DB solo para mostrar
    if not numero:
        try:
            from .models import TicketVenta  # ← si ya lo importaste arriba, puedes quitar esta línea
            ultimo_id = TicketVenta.objects.order_by('-id').values_list('id', flat=True).first()
            numero = ultimo_id or 1
        except Exception:
            numero = 1  # si algo falla, muestra 000001

    # Formato 6 dígitos: 000123
    try:
        numero_formateado = f"{int(numero):06d}"
    except (TypeError, ValueError):
        numero_formateado = "000001"

    p.setFont("Helvetica-Bold", 11)
    p.drawCentredString(45 * mm, y * mm, f"Recibo N\u00B0 {numero_formateado}")
    y -= 8
    # --- fin añadido ---


    # Datos del cliente
    p.setFont("Helvetica", 10)
    p.drawString(10 * mm, y * mm, f"Cliente: {cliente}")
    y -= 5
    p.drawString(10 * mm, y * mm, f"Teléfono: {telefono}")
    y -= 5

    p.drawString(10 * mm, y * mm, f"Vendedor: {vendedor}")
    y -= 5

    p.drawString(10 * mm, y * mm, f"Emisión: {fecha_sistema} {hora_sistema}")
    y -= 5
    p.drawString(10 * mm, y * mm, f"Entrega: {fecha_entrega} {hora_entrega}")
    y -= 7

    # Línea divisoria
    p.drawString(10 * mm, y * mm, "-" * 60)
    y -= 5

    # Encabezado de productos
    p.setFont("Helvetica-Bold", 10)
    p.drawString(10 * mm, y * mm, "Cant.")
    p.drawString(22 * mm, y * mm, "Producto")
    p.drawRightString(80 * mm, y * mm, "Subtotal")
    y -= 5

    p.setFont("Helvetica", 10)

    for item in detalles:
        cantidad = str(item.get("cantidad", "1"))
        descripcion = item.get("descripcion", "")
        precio = float(item.get("precio", 0))
        subtotal = precio # Ajustar subtotal = float(cantidad) * precio
        total += subtotal

        # Ajustar descripción en líneas
        max_chars = 26  # puedes ajustar según ancho
        lineas_desc = textwrap.wrap(descripcion, max_chars)

        # Mostrar cantidad y subtotal solo en la primera línea
        p.drawString(10 * mm, y * mm, cantidad)
        p.drawRightString(80 * mm, y * mm, f"{subtotal:.2f}")
        p.drawString(22 * mm, y * mm, lineas_desc[0])
        y -= 5

        for desc_line in lineas_desc[1:]:
            p.drawString(22 * mm, y * mm, desc_line)
            y -= 5

    # Línea final
    p.drawString(10 * mm, y * mm, "-" * 60)
    y -= 5

 
    # Totales alineados a la derecha
    p.setFont("Helvetica-Bold", 10)
    p.drawRightString(80 * mm, y * mm, f"Total: S/ {total:.2f}")
    y -= 5
    p.drawRightString(80 * mm, y * mm, f"A cuenta: S/ {a_cuenta}")
    y -= 5
    p.drawRightString(80 * mm, y * mm, f"Saldo: S/ {saldo}")
    y -= 7

    # Gracias
    p.drawString(10 * mm, y * mm, "-" * 60)
    y -= 5
    p.drawCentredString(45 * mm, y * mm, "¡GRACIAS POR SU PREFERENCIA!")
    y -= 17
    # Mostrar puntos IC
    puntos_ic = int(request.GET.get('puntos_ic', 0))
    if puntos_ic > 0:
        mensaje = f"¡Felicitaciones, Ud ganó {puntos_ic} punto{'s' if puntos_ic > 1 else ''} IC que podrá canjear en su próxima compra!"
        lineas = textwrap.wrap(mensaje, width=40)  # Ajusta el ancho según el tamaño de fuente

        p.setFont("Helvetica", 11)
        for linea in lineas:
            p.drawString(10 * mm, y * mm, linea)
            y -= 5
        

    # === Al final del ticket, arma la segunda hoja ===
    # ...tras terminar la primera hoja (ticket) y llamar a dibujar_orden_trabajo(...)

    # === preparar datos de RECETA desde query ===
    # Opción JSON compacta (preferida)
    receta_json = request.GET.get('receta')
    if receta_json:
        try:
            receta_data = json.loads(receta_json)
        except Exception:
            receta_data = {}
    else:
        # Opción por campos sueltos (si aún no mandas JSON):
        def G(key): return request.GET.get(key, "")
        receta_data = {
            "esf_lejos_OD": G("esf_lejos_OD"),
            "cil_lejos_OD": G("cil_lejos_OD"),
            "eje_lejos_OD": G("eje_lejos_OD"),
            "DIP_lejos_OD": G("DIP_lejos_OD"),
            "Add_lejos_OD": G("Add_lejos_OD"),
            "AV_lejos_OD":  G("AV_lejos_OD"),

            "esf_lejos_OI": G("esf_lejos_OI"),
            "cil_lejos_OI": G("cil_lejos_OI"),
            "eje_lejos_OI": G("eje_lejos_OI"),
            "DIP_lejos_OI": G("DIP_lejos_OI"),
            "Add_lejos_OI": G("Add_lejos_OI"),
            "AV_lejos_OI":  G("AV_lejos_OI"),

            "esf_cerca_OD": G("esf_cerca_OD"),
            "cil_cerca_OD": G("cil_cerca_OD"),
            "eje_cerca_OD": G("eje_cerca_OD"),
            "DIP_cerca_OD": G("DIP_cerca_OD"),
            "AV_cerca_OD":  G("AV_cerca_OD"),

            "esf_cerca_OI": G("esf_cerca_OI"),
            "cil_cerca_OI": G("cil_cerca_OI"),
            "eje_cerca_OI": G("eje_cerca_OI"),
            "DIP_cerca_OI": G("DIP_cerca_OI"),
            "AV_cerca_OI":  G("AV_cerca_OI"),
        }






    # Productos (nombres) desde detalles
    nombres_productos = []
    for item in detalles:
        desc = str(item.get("descripcion", "")).strip()
        if desc:
            nombres_productos.append(desc)

    # Construye fecha de emisión legible
    fecha_emision_legible = f"{fecha_sistema}"  # ya viene 'dd/mm/yyyy' desde tu query
    hora_emision_legible = f"{hora_sistema}" 
    # Fecha de entrega legible
    fecha_entrega_legible = f"{fecha_entrega}"
    hora_entrega_legible = f"{hora_entrega}"

    # Dibuja la Orden de Trabajo (2da hoja)
    dibujar_orden_trabajo(
        p,
        ancho_mm=90,
        alto_mm=270,
        numero=numero,                     # si no llegó, mostrará PREVIEW
        productos=nombres_productos,
        fecha_emision=fecha_emision_legible,
        hora_emision=hora_emision_legible,
        fecha_entrega=fecha_entrega_legible,
        hora_entrega=hora_entrega_legible,
        telefono=telefono,
        cliente=cliente,
        vendedor=vendedor,
        receta=receta_data,
    )




    # Hoja 3: RECETA
    dibujar_receta(
        p,
        ancho_mm=90,
        alto_mm=270,
        cliente=cliente,
        telefono=telefono,
        fecha_emision=fecha_sistema,
        vendedor=vendedor,
        receta=receta_data
    )


    # === Finalizar PDF y devolver respuesta ===
    p.save()
    pdf_value = buffer.getvalue()
    buffer.close()

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="ticket.pdf"'
    response.write(pdf_value)
    return response
    

# views.py (añadir al final o donde prefieras)
from django.views.decorators.http import require_POST
from django.http import HttpResponseBadRequest

@require_POST
def guardar_ticket(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest("Formato no válido")

    vendedor      = data.get("vendedor", "")
    cliente_name  = data.get("cliente", "")
    telefono      = data.get("telefono", "")
    fecha_entrega = data.get("fecha_entrega", "")
    hora_entrega  = data.get("hora_entrega", "")
    a_cuenta      = Decimal(str(data.get("a_cuenta", "0")))
    saldo         = Decimal(str(data.get("saldo", "0")))
    total         = Decimal(str(data.get("total", "0")))
    puntos_ic     = int(data.get("puntos_ic", 0))
    items_in      = data.get("detalles", [])

    if not items_in:
        return HttpResponseBadRequest("No hay ítems para guardar.")

    # Intentar encontrar cliente
    cliente_obj = None
    if cliente_name:
        cliente_obj = Cliente.objects.filter(nombre__iexact=cliente_name).last()

    with transaction.atomic():
        rc = ReciboCorrelativo.objects.select_for_update().first()
        if not rc:
            rc = ReciboCorrelativo.objects.create(numero_actual=0)
        rc.numero_actual += 1
        numero = rc.numero_actual
        rc.save()

        ticket = TicketVenta.objects.create(
            numero=numero,
            cliente=cliente_obj,
            vendedor=vendedor,
            fecha_entrega=fecha_entrega,
            hora_entrega=hora_entrega,
            total=total,
            a_cuenta=a_cuenta,
            saldo=saldo,
            puntos_ic=puntos_ic,
        )

        detalles_objs = []
        for it in items_in:
            desc   = it.get("descripcion", "")
            cant   = int(it.get("cantidad", 1))
            precio = Decimal(str(it.get("precio", "0")))
            detalles_objs.append(
                DetalleTicketVenta(
                    ticket_numero=ticket,
                    descripcion=desc,
                    cantidad=cant,
                    precio=precio
                )
            )
        DetalleTicketVenta.objects.bulk_create(detalles_objs)

    return JsonResponse({"ok": True, "numero": numero})


def dibujar_orden_trabajo(p, ancho_mm=90, alto_mm=270, *, numero=None, productos=None,
                          fecha_emision=None, hora_emision=None, fecha_entrega=None, hora_entrega=None, telefono=None, cliente=None, vendedor=None, receta=None):
    """
    Dibuja la 2da hoja (Orden de trabajo) en el canvas 'p'.
    Usa el mismo tamaño de página térmica (90mm x 270mm).
    """
    # Nueva página
    p.showPage()
    if receta is None:
        receta = {}

    # Medidas bases
    y = 260    # “línea base” en mm desde arriba
    x_izq = 10 # margen izquierdo
    x_centro = (ancho_mm / 2) * mm

    # Encabezado
    p.setFont("Helvetica-Bold", 12)
    p.drawCentredString(x_centro, y * mm, f"OT #000{numero}")
    y -= 10

    # 👇 Cambiar a normal antes de imprimir fechas
    p.setFont("Helvetica", 10)
    
    # Fechas
    p.drawString(10 * mm, y * mm, f"Emisión: {fecha_emision} {hora_emision}")
    y -= 7
    p.drawString(10 * mm, y * mm, f"Entrega: {fecha_entrega} {hora_entrega}")
    y -= 7

    # Vendedor (útil para taller)
    if vendedor:
        p.drawString(x_izq * mm, y * mm, f"Vendedor: {vendedor}")
        y -= 7

    # Línea
    p.drawString(x_izq * mm, y * mm, "-" * 60)
    y -= 6

    # Productos
    p.setFont("Helvetica-Bold", 11)
    p.drawString(x_izq * mm, y * mm, "Productos / Trabajo:")
    y -= 6
    p.setFont("Helvetica", 10)

    if not productos:
        productos = []

    max_chars = 40  # ancho de línea aprox. para el rollo térmico
    idx = 1
    for prod in productos:
        for i, linea in enumerate(textwrap.wrap(prod, max_chars)):
            bullet = f"{idx}. " if i == 0 else "    "
            p.drawString(x_izq * mm, y * mm, bullet + linea)
            y -= 5
        idx += 1

   # Línea
    p.drawString(x_izq * mm, y * mm, "-" * 60)
    y -= 6


    # Tabla (LEJOS)
    p.setFont("Helvetica-Bold", 10)
    p.drawString(x_izq * mm, y * mm, "Visión de Lejos")
    y -= 6
    p.setFont("Helvetica", 9)

    # Cabeceras
    headers = ["", "Esf", "Cil", "Eje","DIP", "Add"]
    col_x = [x_izq, x_izq+14, x_izq+27, x_izq+40, x_izq+53, x_izq+66, x_izq+78]  # mm aprox en rollo 80/90mm
    for i, h in enumerate(headers):
        p.drawString(col_x[i] * mm, y * mm, h)
    y -= 5

    # Fila OD lejos
    fila_OD = [
        "OD",
        receta.get("esf_lejos_OD", ""),
        receta.get("cil_lejos_OD", ""),
        receta.get("eje_lejos_OD", ""),
        receta.get("DIP_lejos_OD", ""),
        receta.get("Add_lejos_OD", ""),
        #receta.get("AV_lejos_OD", ""),
    ]
    for i, val in enumerate(fila_OD):
        p.drawString(col_x[i] * mm, y * mm, str(val))
    y -= 5

    # Fila OI lejos
    fila_OI = [
        "OI",
        receta.get("esf_lejos_OI", ""),
        receta.get("cil_lejos_OI", ""),
        receta.get("eje_lejos_OI", ""),
        receta.get("DIP_lejos_OI", ""),
        receta.get("Add_lejos_OI", ""),
        #receta.get("AV_lejos_OI", ""),
    ]
    for i, val in enumerate(fila_OI):
        p.drawString(col_x[i] * mm, y * mm, str(val))
    y -= 6

    # Si hay CERCA, dibuja tabla de cerca
    tiene_cerca = any(receta.get(k) for k in [
        "esf_cerca_OD","cil_cerca_OD","eje_cerca_OD","DIP_cerca_OD","AV_cerca_OD",
        "esf_cerca_OI","cil_cerca_OI","eje_cerca_OI","DIP_cerca_OI","AV_cerca_OI",
    ])
    if tiene_cerca:
        p.setFont("Helvetica-Bold", 10)
        p.drawString(x_izq * mm, y * mm, "Visión de Cerca")
        y -= 6
        p.setFont("Helvetica", 9)
        headers_c = ["", "Esf", "Cil", "Eje", "DIP"]
        colc_x = [x_izq, x_izq+16, x_izq+30, x_izq+43, x_izq+56, x_izq+70]
        for i, h in enumerate(headers_c):
            p.drawString(colc_x[i] * mm, y * mm, h)
        y -= 5

        fila_ODc = [
            "OD",
            receta.get("esf_cerca_OD", ""),
            receta.get("cil_cerca_OD", ""),
            receta.get("eje_cerca_OD", ""),
            receta.get("DIP_cerca_OD", ""),
            #receta.get("AV_cerca_OD", ""),
        ]
        for i, val in enumerate(fila_ODc):
            p.drawString(colc_x[i] * mm, y * mm, str(val))
        y -= 5

        fila_OIc = [
            "OI",
            receta.get("esf_cerca_OI", ""),
            receta.get("cil_cerca_OI", ""),
            receta.get("eje_cerca_OI", ""),
            receta.get("DIP_cerca_OI", ""),
            #receta.get("AV_cerca_OI", ""),
        ]
        for i, val in enumerate(fila_OIc):
            p.drawString(colc_x[i] * mm, y * mm, str(val))
        y -= 6

   # Línea
    p.drawString(x_izq * mm, y * mm, "-" * 80)

    # Espacio para observaciones/taller
    y -= 6
    p.setFont("Helvetica-Bold", 10)
    p.drawString(x_izq * mm, y * mm, "Observaciones:")
    y -= 30
    p.setFont("Helvetica", 10)
    p.drawString(x_izq * mm, (y+22) * mm, "____________________________")
    p.drawString(x_izq * mm, (y+14) * mm, "____________________________")
    p.drawString(x_izq * mm, (y+6)  * mm, "____________________________")
    y -= 10


    # Línea de corte
    p.drawString(x_izq * mm, y * mm, "-" * 60)
    y -= 6
    p.setFont("Helvetica-Oblique", 9)
    p.drawCentredString(x_centro, y * mm, "— Separa aquí —")


# --- 3ra hoja: RECETA ---
def dibujar_receta(p, *, ancho_mm=90, alto_mm=270, cliente=None, telefono=None,
                   fecha_emision=None, vendedor=None, receta=None):
    """
    Dibuja la hoja de RECETA. 'receta' es un dict con campos:
    - esf_lejos_OD, cil_lejos_OD, eje_lejos_OD, DIP_lejos_OD, Add_lejos_OD, AV_lejos_OD
    - esf_lejos_OI, cil_lejos_OI, eje_lejos_OI, DIP_lejos_OI, Add_lejos_OI, AV_lejos_OI
    - esf_cerca_OD, cil_cerca_OD, eje_cerca_OD, DIP_cerca_OD, AV_cerca_OD
    - esf_cerca_OI, cil_cerca_OI, eje_cerca_OI, DIP_cerca_OI, AV_cerca_OI
    (puedes enviar solo “lejos” si no hay “cerca”)
    """
    p.showPage()  # nueva página
    if receta is None:
        receta = {}

    x_izq = 6
    x_centro = (ancho_mm / 2) * mm
    y = 264

    # Título
    p.setFont("Helvetica-Bold", 12)
    p.drawCentredString(x_centro, y * mm, "RECETA ")
    y -= 8

    p.setFont("Helvetica", 9)
    if cliente:
        p.drawString(x_izq * mm, y * mm, f"Cliente: {cliente}")
        y -= 5
    if telefono:
        #p.drawString(x_izq * mm, y * mm, f"Teléfono: {telefono}")
        y -= 5
    if fecha_emision:
        p.drawString(x_izq * mm, y * mm, f"Fecha de emisión: {fecha_emision}")
        y -= 5
    if vendedor:
        #p.drawString(x_izq * mm, y * mm, f"Optometrista / Vendedor: {vendedor}")
        y -= 6

    # Línea
    p.drawString(x_izq * mm, y * mm, "-" * 60)
    y -= 6

    # Tabla (LEJOS)
    p.setFont("Helvetica-Bold", 10)
    p.drawString(x_izq * mm, y * mm, "Visión de Lejos")
    y -= 6
    p.setFont("Helvetica", 9)

    # Cabeceras
    headers = ["", "Esf", "Cil", "Eje", "DIP", "Add", "AV"]
    col_x = [x_izq, x_izq+10, x_izq+23, x_izq+36, x_izq+49, x_izq+60, x_izq+70]  # mm aprox en rollo 80/90mm
    for i, h in enumerate(headers):
        p.drawString(col_x[i] * mm, y * mm, h)
    y -= 5

    # Fila OD lejos
    fila_OD = [
        "OD",
        receta.get("esf_lejos_OD", ""),
        receta.get("cil_lejos_OD", ""),
        receta.get("eje_lejos_OD", ""),
        receta.get("DIP_lejos_OD", ""),
        receta.get("Add_lejos_OD", ""),
        receta.get("AV_lejos_OD", ""),
    ]
    for i, val in enumerate(fila_OD):
        p.drawString(col_x[i] * mm, y * mm, str(val))
    y -= 5

    # Fila OI lejos
    fila_OI = [
        "OI",
        receta.get("esf_lejos_OI", ""),
        receta.get("cil_lejos_OI", ""),
        receta.get("eje_lejos_OI", ""),
        receta.get("DIP_lejos_OI", ""),
        receta.get("Add_lejos_OI", ""),
        receta.get("AV_lejos_OI", ""),
    ]
    for i, val in enumerate(fila_OI):
        p.drawString(col_x[i] * mm, y * mm, str(val))
    y -= 6

    # Si hay CERCA, dibuja tabla de cerca
    tiene_cerca = any(receta.get(k) for k in [
        "esf_cerca_OD","cil_cerca_OD","eje_cerca_OD","DIP_cerca_OD","AV_cerca_OD",
        "esf_cerca_OI","cil_cerca_OI","eje_cerca_OI","DIP_cerca_OI","AV_cerca_OI",
    ])
    if tiene_cerca:
        p.setFont("Helvetica-Bold", 10)
        p.drawString(x_izq * mm, y * mm, "Visión de Cerca")
        y -= 6
        p.setFont("Helvetica", 9)
        headers_c = ["","Esf", "Cil", "Eje", "DIP", "AV"]
        colc_x = [x_izq, x_izq+10, x_izq+23, x_izq+36, x_izq+49, x_izq+70]
        for i, h in enumerate(headers_c):
            p.drawString(colc_x[i] * mm, y * mm, h)
        y -= 5

        fila_ODc = [
            "OD",
            receta.get("esf_cerca_OD", ""),
            receta.get("cil_cerca_OD", ""),
            receta.get("eje_cerca_OD", ""),
            receta.get("DIP_cerca_OD", ""),
            receta.get("AV_cerca_OD", ""),
        ]
        for i, val in enumerate(fila_ODc):
            p.drawString(colc_x[i] * mm, y * mm, str(val))
        y -= 5

        fila_OIc = [
            "OI",
            receta.get("esf_cerca_OI", ""),
            receta.get("cil_cerca_OI", ""),
            receta.get("eje_cerca_OI", ""),
            receta.get("DIP_cerca_OI", ""),
            receta.get("AV_cerca_OI", ""),
        ]
        for i, val in enumerate(fila_OIc):
            p.drawString(colc_x[i] * mm, y * mm, str(val))
        y -= 6

    # Observaciones y firma
    p.drawString(x_izq * mm, y * mm, "-" * 60); y -= 6
    p.setFont("Helvetica-Bold", 9); p.drawString(x_izq * mm, y * mm, "Observaciones:"); y -= 20
    p.setFont("Helvetica", 9)
    p.drawString((x_izq+2) * mm, (y+14) * mm, "____________________________")
    p.drawString((x_izq+2) * mm, (y+6)  * mm,  "____________________________")
    y -= 14

    # Línea de corte al final de la hoja RECETA
    p.drawString(x_izq * mm, y * mm, "-" * 60); y -= 6
    p.setFont("Helvetica-Oblique", 9)
    p.drawCentredString(x_centro, y * mm, "— Separa aquí —")
    p.showPage()  # corta justo aquí


@require_http_methods(["GET","POST"])
def consulta_dni(request):
    # GET: devuelve nombre por DNI
    if request.method == "GET":
        codigo = (request.GET.get("codigo") or "").strip()
        if not codigo:
            return JsonResponse({"ok": False, "error": "DNI vacío"}, status=400)

        try:
            url = f"https://api.apis.net.pe/v1/dni?numero={codigo}"
            headers = {
                "Authorization": f"Bearer {getattr(settings, 'APIS_DNI_TOKEN', '')}"
            }
            r = requests.get(url, headers=headers, timeout=8)
            if r.status_code == 200:
                d = r.json() or {}
                # API suele devolver: nombres, apellidoPaterno, apellidoMaterno
                nombres = (d.get("nombres") or "").strip()
                ap = (d.get("apellidoPaterno") or "").strip()
                am = (d.get("apellidoMaterno") or "").strip()
                nombre_completo = " ".join(x for x in [nombres, ap, am] if x).strip()
                return JsonResponse({"ok": True, "nombre": nombre_completo})
            return JsonResponse({"ok": False, "error": f"API {r.status_code}"}, status=502)
        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=500)

    # POST: crea un cliente (opcional, por si la quieres usar aquí)
    form = ClienteForm(request.POST)
    if form.is_valid():
        form.save()
        return redirect("registrar_cliente")
    return render(request, "core/registro_cliente2.html", {
        "cliente_form": form,
        "medida_form": MedidaVistaForm(),
        "tipo_lunas_form": TipoLunasForm(),
    })



