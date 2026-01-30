import requests  # <--- añade esto
from django.views.decorators.http import require_GET

from django.shortcuts import render, redirect
from .models import Venta, Producto, Gasto, Venta, MedidaVista, Cliente, TipoLunas, ReciboCorrelativo, TicketVenta, DetalleTicketVenta, Compra, DetalleCompra, Proveedor
from .forms import ClienteForm, MedidaVistaForm, TipoLunasForm, ProductoForm, CompraForm, ProveedorForm, DetalleCompraForm
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

from django.contrib import messages


def index(request):
    return render(request, 'core/index.html')

def lista_ventas(request):
    ventas = Venta.objects.all()
    return render(request, 'core/ventas.html', {'ventas': ventas})

def registrar_venta(request):
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

    return render(request, 'core/registro_ventas.html', {
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

@transaction.atomic
def registrar_cliente(request):
    cliente = None

    if request.method == 'POST':
        # viene del formulario
        dni = request.POST.get('DNI', '').strip()
        cliente_id = request.POST.get('cliente_id')  # hidden

        # 1. Identificar si el cliente ya existe
        if cliente_id:
            cliente = get_object_or_404(Cliente, id=cliente_id)
            cliente_form = ClienteForm(request.POST, instance=cliente)
        else:
            # si no hay cliente_id, buscamos por DNI
            if dni:
                try:
                    cliente = Cliente.objects.get(DNI=dni)
                    # si lo encontramos, usamos ese objeto
                    cliente_form = ClienteForm(request.POST, instance=cliente)
                except Cliente.DoesNotExist:
                    cliente = None
                    cliente_form = ClienteForm(request.POST)
            else:
                cliente_form = ClienteForm(request.POST)

        medida_form = MedidaVistaForm(request.POST)

        if cliente_form.is_valid() and medida_form.is_valid():
            # 2. Guardar/actualizar cliente (sin duplicar)
            cliente = cliente_form.save()

            # 3. Crear nueva medida vinculada al cliente
            medida = medida_form.save(commit=False)
            medida.cliente = cliente
            # Si luego agregas un campo fecha_registro en MedidaVista, aquí se llenaría automáticamente con auto_now_add
            medida.save()

            if cliente_id or (cliente and Cliente.objects.filter(DNI=dni).exists()):
                messages.success(request, 'Medida registrada correctamente para el cliente.')
            else:
                messages.success(request, 'Cliente y medida registrados correctamente.')

            return redirect('lista_clientes')
    else:
        cliente_form = ClienteForm()
        medida_form = MedidaVistaForm()

    return render(request, 'core/registro_cliente.html', {
        'cliente_form': cliente_form,
        'medida_form': medida_form,
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
            return redirect('crear_producto')
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
    return render(request, "core/registro_ventas.html", {
        "cliente_form": form,
        "medida_form": MedidaVistaForm(),
        "tipo_lunas_form": TipoLunasForm(),
    })




@transaction.atomic
def registrar_compra(request):
    if request.method == 'POST':
        compra_form = CompraForm(request.POST)
        if compra_form.is_valid():
            compra = compra_form.save(commit=False)
            compra.total = 0  # lo calculamos
            compra.save()

            cods            = request.POST.getlist('cod[]')
            descripciones   = request.POST.getlist('descripcion[]')
            tipos           = request.POST.getlist('tipo[]')
            precios_compra  = request.POST.getlist('precio_compra[]')
            precios_venta   = request.POST.getlist('precio_venta[]')
            cantidades      = request.POST.getlist('cantidad[]')
            subtotales      = request.POST.getlist('subtotal[]')

            total_compra = 0

            for i in range(len(cods)):
                cod = cods[i].strip()
                if not cod:
                    continue  # fila vacía

                descripcion = descripciones[i].strip()
                tipo = tipos[i].strip()
                pc = float(precios_compra[i] or 0)
                pv = float(precios_venta[i] or 0)
                cant = float(cantidades[i] or 0)
                sub = float(subtotales[i] or 0)

                # 🔹 1. Buscar o crear producto por código
                producto, creado = Producto.objects.get_or_create(
                    cod=cod,
                    defaults={
                        'descripcion': descripcion,
                        'precio_compra': pc,
                        'precio_venta': pv,
                        'stock': cant,
                        'tipo': tipo,
                    }
                )

                # 🔹 2. Si ya existía, ACTUALIZAR datos y aumentar stock
                if not creado:
                    producto.descripcion = descripcion or producto.descripcion
                    producto.precio_compra = pc
                    producto.precio_venta = pv
                    producto.tipo = tipo or producto.tipo
                    producto.stock = (producto.stock or 0) + cant
                    producto.save()
                else:
                    # si es nuevo, ya se guardó con el stock inicial
                    producto.save()

                # 🔹 3. Crear el detalle de compra
                DetalleCompra.objects.create(
                    compra=compra,
                    producto=producto,
                    cantidad=cant,
                    precio_compra=pc,
                    precio_venta=pv,
                    subtotal=sub
                )

                total_compra += sub

            # 🔹 4. Actualizar total de la compra
            compra.total = total_compra
            compra.save()

            return redirect('lista_compras')  # o donde quieras

    else:
        compra_form = CompraForm()

    return render(request, 'core/registro_compra.html', {
        'compra_form': compra_form,
    })


def crear_proveedor(request):
    if request.method == 'POST':
        form = ProveedorForm(request.POST)
        if form.is_valid():
            form.save()
            # después de crear el proveedor, regresas a la compra
            return redirect('registrar_compra')
    else:
        form = ProveedorForm()

    return render(request, 'core/crear_proveedor.html', {
        'form': form
    })

def lista_compras(request):
    compras = Compra.objects.select_related('proveedor').order_by('-fecha', '-id')
    return render(request, 'core/lista_compras.html', {
        'compras': compras
    })
def editar_compra(request, compra_id):
    compra = get_object_or_404(Compra, id=compra_id)

    if request.method == 'POST':
        form = CompraForm(request.POST, instance=compra)
        if form.is_valid():
            form.save()
            messages.success(request, 'Compra actualizada correctamente.')
            return redirect('lista_compras')
    else:
        form = CompraForm(instance=compra)

    return render(request, 'core/editar_compra.html', {
        'form': form,
        'compra': compra,
    })

@transaction.atomic
def eliminar_compra(request, compra_id):
    compra = get_object_or_404(Compra, id=compra_id)

    if request.method == 'POST':
        # 1. Ajustar stock de productos
        for det in compra.detalles.all():  # gracias al related_name='detalles'
            producto = det.producto
            # restamos la cantidad de la compra al stock
            if producto.stock is not None:
                producto.stock = (producto.stock or 0) - (det.cantidad or 0)
                if producto.stock < 0:
                    producto.stock = 0  # por si acaso
                producto.save()

        # 2. Eliminar la compra (y sus DetalleCompra por CASCADE)
        compra.delete()
        messages.success(request, 'Compra eliminada correctamente.')
        return redirect('lista_compras')

    return render(request, 'core/confirmar_eliminar_compra.html', {
        'compra': compra
    })


def lista_detalles_compra(request):
    detalles = DetalleCompra.objects.select_related('compra', 'producto', 'compra__proveedor').order_by('-compra__fecha', '-id')
    return render(request, 'core/lista_detalles_compra.html', {
        'detalles': detalles
    })


@transaction.atomic
def editar_detalle_compra(request, detalle_id):
    detalle = get_object_or_404(DetalleCompra, id=detalle_id)
    compra = detalle.compra

    # guardamos valores anteriores
    producto_anterior = detalle.producto
    cantidad_anterior = float(detalle.cantidad or 0)

    if request.method == 'POST':
        form = DetalleCompraForm(request.POST, instance=detalle)
        if form.is_valid():
            detalle_modificado = form.save(commit=False)

            producto_nuevo = detalle_modificado.producto
            cantidad_nueva = float(detalle_modificado.cantidad or 0)
            precio_compra = float(detalle_modificado.precio_compra or 0)

            # 1. Ajustar stock según cambios
            if producto_nuevo == producto_anterior:
                # mismo producto: ajustamos solo la diferencia de cantidad
                diferencia = cantidad_nueva - cantidad_anterior
                producto_nuevo.stock = (producto_nuevo.stock or 0) + diferencia
                if producto_nuevo.stock < 0:
                    producto_nuevo.stock = 0
                producto_nuevo.save()
            else:
                # producto cambiado:
                #   - devolvemos cantidad al producto anterior
                producto_anterior.stock = (producto_anterior.stock or 0) - cantidad_anterior
                if producto_anterior.stock < 0:
                    producto_anterior.stock = 0
                producto_anterior.save()

                #   - sumamos cantidad al nuevo producto
                producto_nuevo.stock = (producto_nuevo.stock or 0) + cantidad_nueva
                if producto_nuevo.stock < 0:
                    producto_nuevo.stock = 0
                producto_nuevo.save()

            # 2. Recalcular subtotal
            detalle_modificado.subtotal = precio_compra * cantidad_nueva

            # 3. Guardar detalle
            detalle_modificado.save()

            # 4. Recalcular total de la compra
            total_compra = 0
            for d in compra.detalles.all():
                total_compra += float(d.subtotal or 0)
            compra.total = total_compra
            compra.save()

            messages.success(request, 'Detalle de compra actualizado correctamente.')
            return redirect('lista_detalles_compra')
    else:
        form = DetalleCompraForm(instance=detalle)

    return render(request, 'core/editar_detalle_compra.html', {
        'form': form,
        'detalle': detalle,
        'compra': compra,
    })

@transaction.atomic
def eliminar_detalle_compra(request, detalle_id):
    detalle = get_object_or_404(DetalleCompra, id=detalle_id)
    compra = detalle.compra
    producto = detalle.producto
    cantidad = float(detalle.cantidad or 0)

    if request.method == 'POST':
        # 1. Ajustar stock
        producto.stock = (producto.stock or 0) - cantidad
        if producto.stock < 0:
            producto.stock = 0
        producto.save()

        # 2. Eliminar detalle
        detalle.delete()

        # 3. Recalcular total de la compra
        total_compra = 0
        for d in compra.detalles.all():
            total_compra += float(d.subtotal or 0)
        compra.total = total_compra
        compra.save()

        messages.success(request, 'Detalle de compra eliminado correctamente.')
        return redirect('lista_detalles_compra')

    return render(request, 'core/confirmar_eliminar_detalle_compra.html', {
        'detalle': detalle,
        'compra': compra,
    })


@require_GET
def buscar_cliente_por_dni(request):
    dni = request.GET.get('dni', '').strip()
    data = {'existe': False}

    if dni:
        try:
            cliente = Cliente.objects.get(DNI=dni)
            data.update({
                'existe': True,
                'id': cliente.id,
                'nombre': cliente.nombre or '',
                'telefono': cliente.telefono or '',
                'edad': cliente.Edad or '',
            })
        except Cliente.DoesNotExist:
            pass

    return JsonResponse(data)


def lista_clientes(request):
    clientes = Cliente.objects.all().order_by('-id')

    dni = request.GET.get('dni')
    nombre = request.GET.get('nombre')
    fecha = request.GET.get('fecha')   # fecha_registro

    # FILTRO POR DNI
    if dni:
        clientes = clientes.filter(DNI__icontains=dni)

    # FILTRO POR NOMBRE
    if nombre:
        clientes = clientes.filter(nombre__icontains=nombre)

    # FILTRO POR FECHA (formato YYYY-MM-DD)
    if fecha:
        clientes = clientes.filter(fecha_registro=fecha)

    return render(request, 'core/lista_clientes.html', {
        'clientes': clientes
    })


def crear_cliente(request):
    if request.method == 'POST':
        form = ClienteForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Cliente registrado correctamente.')
            return redirect('lista_clientes')
    else:
        form = ClienteForm()
    return render(request, 'core/editar_cliente.html', {
        'form': form,
        'titulo': 'Nuevo Clientes',
    })


def editar_cliente(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    if request.method == 'POST':
        form = ClienteForm(request.POST, instance=cliente)
        if form.is_valid():
            form.save()
            messages.success(request, 'Cliente actualizado correctamente.')
            return redirect('lista_clientes')
    else:
        form = ClienteForm(instance=cliente)
    return render(request, 'core/editar_cliente.html', {
        'form': form,
        'titulo': f'Editar Cliente: {cliente.nombre}',
    })

@transaction.atomic
def eliminar_cliente(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)

    if request.method == 'POST':
        nombre = cliente.nombre
        cliente.delete()
        messages.success(request, f'Cliente "{nombre}" eliminado correctamente.')
        return redirect('lista_clientes')

    return render(request, 'core/confirmar_eliminar_cliente.html', {
        'cliente': cliente
    })
def cliente_historial(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)

    medidas = MedidaVista.objects.filter(cliente=cliente).order_by('-id')
    ticket_ventas = TicketVenta.objects.filter(cliente=cliente).order_by('-fecha_emision', '-id')
    ventas = Venta.objects.filter(cliente=cliente).order_by('-fecha', '-id')

    return render(request, 'core/cliente_historial.html', {
        'cliente': cliente,
        'medidas': medidas,
        'ticket_ventas': ticket_ventas,
        'ventas': ventas,
    })


def consulta_dni(request):
    dni = request.GET.get('dni')
    if not dni:
        return JsonResponse({'nombre': '', 'error': 'DNI requerido'}, status=400)

    url = f"https://api.apis.net.pe/v1/dni?numero={dni}"
    headers = {
        # mejor guarda el token en settings.APIS_NET_PE_TOKEN
        'Authorization': 'Bearer tu_token_de_seguridad'
        # 'Authorization': f'Bearer {settings.APIS_NET_PE_TOKEN}'
    }

    try:
        response = requests.get(url, headers=headers, timeout=5)
    except requests.RequestException:
        return JsonResponse({'nombre': '', 'error': 'Error de conexión'}, status=500)

    if response.status_code == 200:
        data = response.json()
        # adapta según el JSON real de la API (ejemplo típico):
        # nombres, apellidoPaterno, apellidoMaterno
        nombre = data.get('nombre') or data.get('nombres')  # por si cambia la clave
        apellido_p = data.get('apellidoPaterno', '')
        apellido_m = data.get('apellidoMaterno', '')
        nombre_completo = " ".join(
            x for x in [nombre] if x
        )

        return JsonResponse({'nombre': nombre_completo})
    else:
        return JsonResponse({'nombre': '', 'error': 'DNI no encontrado'}, status=404)


def buscar_clientes(request):
    term = request.GET.get('term', '')  # jQuery UI envía 'term'
    clientes = Cliente.objects.filter(DNI__icontains=term)[:10]

    resultados = []
    for c in clientes:
        resultados.append({
            "label": f"{c.DNI} - {c.nombre}",  # lo que se muestra en la lista
            "value": c.DNI,                    # lo que se pone en el input
            "nombre": c.nombre,
            "telefono": c.telefono,
            "id": c.id,
        })

    return JsonResponse(resultados, safe=False)



def ultima_medida_cliente(request):
    cliente_id = request.GET.get('cliente_id')

    if not cliente_id:
        return JsonResponse({'existe': False, 'error': 'cliente_id requerido'})

    medida = (
        MedidaVista.objects
            .filter(cliente_id=cliente_id)
            .order_by('-fecha_registro')   # tu campo real
            .first()
    )

    if not medida:
        return JsonResponse({'existe': False})

    data = {
        'existe': True,

        # CAMPO 1: LEJOS OD
        'esf_lejos_OD': medida.esf_lejos_OD,
        'cil_lejos_OD': medida.cil_lejos_OD,
        'eje_lejos_OD': medida.eje_lejos_OD,

        # CAMPO 2: LEJOS OI
        'esf_lejos_OI': medida.esf_lejos_OI,
        'cil_lejos_OI': medida.cil_lejos_OI,
        'eje_lejos_OI': medida.eje_lejos_OI,

        # CAMPO 3: ADD (OD)
        'Add_lejos_OD': medida.Add_lejos_OD,

        # CAMPO 4: DESCRIPCIÓN / OBSERVACIONES
        'descripcion': medida.descripcion or "",
    }

    return JsonResponse(data)


def buscar_medidas(request):
    """
    Endpoint para jQuery UI Autocomplete.
    Busca en MedidaVista por DNI o nombre del cliente
    y devuelve una lista de recetas recientes.
    """
    term = request.GET.get("term", "").strip()
    resultados = []

    if term:
        qs = (
            MedidaVista.objects
            .select_related("cliente")
            .filter(
                Q(cliente__DNI__icontains=term) |
                Q(cliente__nombre__icontains=term)
            )
            .order_by("-fecha_registro")[:20]
        )

        for medida in qs:
            c = medida.cliente
            label = f"{c.DNI or ''} - {c.nombre} · {medida.fecha_registro:%d/%m/%Y}"
            resultados.append({
                "label": label,
                "value": label,
                "medida_id": medida.id,
                "cliente_id": c.id,
                "dni": c.DNI,
                "nombre": c.nombre,
                "telefono": c.telefono,
                "edad": c.Edad,
            })

    return JsonResponse(resultados, safe=False)


def medida_detalle(request, medida_id):
    """
    Devuelve todos los campos de la medida para
    rellenar la receta en la venta.
    """
    medida = get_object_or_404(MedidaVista, pk=medida_id)
    c = medida.cliente

    def to_number(x):
        return float(x) if x is not None else None

    data = {
        "medida_id": medida.id,
        "cliente_id": c.id,
        "dni": c.DNI,
        "nombre": c.nombre,
        "telefono": c.telefono,
        "edad": c.Edad,
        "descripcion": medida.descripcion,

        "esf_lejos_OD": to_number(medida.esf_lejos_OD),
        "cil_lejos_OD": to_number(medida.cil_lejos_OD),
        "eje_lejos_OD": to_number(medida.eje_lejos_OD),
        "DIP_lejos_OD": to_number(medida.DIP_lejos_OD),
        "Add_lejos_OD": to_number(medida.Add_lejos_OD),
        "AV_lejos_OD": medida.AV_lejos_OD,

        "esf_lejos_OI": to_number(medida.esf_lejos_OI),
        "cil_lejos_OI": to_number(medida.cil_lejos_OI),
        "eje_lejos_OI": to_number(medida.eje_lejos_OI),
        "DIP_lejos_OI": to_number(medida.DIP_lejos_OI),
        "Add_lejos_OI": to_number(medida.Add_lejos_OI),
        "AV_lejos_OI": medida.AV_lejos_OI,

        "esf_cerca_OD": to_number(medida.esf_cerca_OD),
        "cil_cerca_OD": to_number(medida.cil_cerca_OD),
        "eje_cerca_OD": to_number(medida.eje_cerca_OD),
        "DIP_cerca_OD": to_number(medida.DIP_cerca_OD),
        "AV_cerca_OD": medida.AV_cerca_OD,

        "esf_cerca_OI": to_number(medida.esf_cerca_OI),
        "cil_cerca_OI": to_number(medida.cil_cerca_OI),
        "eje_cerca_OI": to_number(medida.eje_cerca_OI),
        "DIP_cerca_OI": to_number(medida.DIP_cerca_OI),
        "AV_cerca_OI": medida.AV_cerca_OI,
    }
    return JsonResponse(data)

def ultimas_medidas(request):
    """
    Devuelve las 10 MedidaVista más recientes
    para llenar la lista desplegable.
    """
    qs = (
        MedidaVista.objects
        .select_related("cliente")
        .order_by("-fecha_registro")[:5]
    )

    resultados = []
    for medida in qs:
        c = medida.cliente
        label = f"{c.DNI or ''} - {c.nombre} · {medida.fecha_registro:%d/%m/%Y}"

        resultados.append({
            "medida_id": medida.id,
            "cliente_id": c.id,
            "label": label,
            "dni": c.DNI,
            "nombre": c.nombre,
            "telefono": c.telefono,
            "edad": c.Edad,
          })

    return JsonResponse(resultados, safe=False)