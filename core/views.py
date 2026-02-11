from django.contrib.staticfiles import finders
from django.urls import reverse


from .models import OrdenTrabajo
from .utils_pdf import render_to_pdf
from django.contrib.auth.decorators import login_required, user_passes_test

from accounts.decorators import role_required


import requests  # <--- añade esto
from django.views.decorators.http import require_GET

from reportlab.platypus import Paragraph, Frame
from reportlab.lib.styles import ParagraphStyle

from django.shortcuts import render, redirect
from .models import Venta, Producto, Gasto, Venta, MedidaVista, Cliente, TipoLunas, ReciboCorrelativo, TicketVenta, DetalleTicketVenta, Compra, DetalleCompra, Proveedor, KardexMovimiento, PagoTicket, MovimientoCaja, OrdenTrabajo
from .forms import ClienteForm, MedidaVistaForm, TipoLunasForm, ProductoForm, CompraForm, ProveedorForm, DetalleCompraForm
from django.shortcuts import get_object_or_404

from django.http import JsonResponse
from django.db.models import Count, Q

from django.views.decorators.csrf import csrf_exempt
import json
from datetime import datetime
from datetime import date

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

from django.db.models import Max, Sum

from django.views.decorators.http import require_http_methods

from django.contrib import messages

from core.kardex import recalcular_kardex_producto


from accounts.forms import LoginForm
from django.contrib.auth import login
def index(request):
    # Si ya inició sesión, manda al dashboard (o a donde quieras)
    if request.user.is_authenticated:
        return redirect("dashboard")  # o "index" si no tienes dashboard separado

    form = LoginForm(request, data=request.POST or None)

    if request.method == "POST":
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect("dashboard")  # o a donde quieras entrar

    return render(request, "core/index.html", {"form": form})

@role_required("ADMIN", "SUPERVISOR", "VENDEDOR", "CAJA")
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
@role_required("ADMIN", "SUPERVISOR", "VENDEDOR", "CAJA")
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

            # OJO: si fecha_registro es auto_now_add en MedidaVista, NO la asignes.
            # Solo deja esto si tu modelo MedidaVista tiene fecha_registro editable.
            try:
                medida.fecha_registro = cliente.fecha_registro
            except Exception:
                pass

            # OJO: ajusta el nombre exacto del campo (Optometra vs optometra)
            try:
                medida.Optometra = cliente.Optometra
            except Exception:
                pass

            medida.save()

            if cliente_id or (dni and Cliente.objects.filter(DNI=dni).exists()):
                messages.success(request, 'Medida registrada correctamente para el cliente.')
            else:
                messages.success(request, 'Cliente y medida registrados correctamente.')

            # ✅ SI PRESIONÓ "Guardar cliente y receta" -> abrir PDF receta
            if "guardar_cliente_receta" in request.POST:
                return redirect(reverse("receta_pdf", args=[medida.id]))

            # Si no, tu flujo normal
            return redirect('lista_clientes')
    else:
        cliente_form = ClienteForm()
        medida_form = MedidaVistaForm()

    return render(request, 'core/registro_cliente.html', {
        'cliente_form': cliente_form,
        'medida_form': medida_form,
    })

@role_required("ADMIN", "SUPERVISOR")
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

@role_required("ADMIN", "SUPERVISOR")
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

# Este es el que imprime el ticket
def generar_ticket_pdf(request):
    buffer = BytesIO()

    # ========= AJUSTE REAL PARA TIQUETERA =========
    WIDTH_MM = 80
    HEIGHT_MM = 270
    MARGIN_MM = 3

    PAGE_W = WIDTH_MM * mm
    PAGE_H = HEIGHT_MM * mm

    LEFT_X   = MARGIN_MM * mm
    RIGHT_X  = (WIDTH_MM - MARGIN_MM) * mm
    CENTER_X = (WIDTH_MM / 2) * mm

    COL_QTY_X      = LEFT_X
    COL_DESC_X     = (MARGIN_MM + 12) * mm
    COL_SUBTOTAL_X = (WIDTH_MM - MARGIN_MM) * mm

    p = canvas.Canvas(buffer, pagesize=(PAGE_W, PAGE_H))

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
    puntos_ic = request.GET.get('puntos_ic', '0.00')

    detalles_json = request.GET.get('detalles', '[]')
    try:
        detalles = json.loads(detalles_json)
    except Exception:
        detalles = []

    # Datos empresa
    RUC_EMPRESA = "RUC: 10429550101"
    DIR_EMPRESA = "Dirección: Jr. Camaná N° 560, Cercado de Lima"
    TELS_EMPRESA = "Cel: 952305913 / 914300701"

    try:
        puntos_int = int(float(puntos_ic))
    except Exception:
        puntos_int = 0

    def wrap_text(text, max_chars=32):
        return textwrap.wrap(str(text or ""), max_chars) or [""]

    def hr(y_mm):
        y = y_mm * mm
        p.line(LEFT_X, y, RIGHT_X, y)

    # ====== Número de Ticket ======
    numero = request.GET.get('numero')
    if not numero:
        try:
            ultimo_id = TicketVenta.objects.order_by('-id').values_list('id', flat=True).first()
            numero = ultimo_id or 1
        except Exception:
            numero = 1

    try:
        numero_formateado = f"{int(numero):06d}"
    except Exception:
        numero_formateado = "000001"

    # ===== receta_data (lo mantengo igual como ya lo tienes) =====
    receta_json = request.GET.get('receta')
    if receta_json:
        try:
            receta_data = json.loads(receta_json)
        except Exception:
            receta_data = {}
    else:
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

    nombres_productos = []
    for item in detalles:
        desc = str(item.get("descripcion", "")).strip()
        if desc:
            nombres_productos.append(desc)

    # =========================================================
    # ✅ FUNCIÓN QUE DIBUJA 1 RECIBO EN LA HOJA ACTUAL
    # =========================================================
    def dibujar_recibo(copia_n: int):
        total = 0.0
        y = 257  # en mm

        # ====== LOGO ======
        ruta_logo = finders.find("core/img/logo.png")
        if ruta_logo and os.path.exists(ruta_logo):
            logo = ImageReader(ruta_logo)
            ancho_logo_pt = 90
            alto_logo_pt = 35
            x_centro_logo = (PAGE_W - ancho_logo_pt) / 2
            p.drawImage(logo, x_centro_logo, y * mm, width=ancho_logo_pt, height=alto_logo_pt,
                        preserveAspectRatio=True, mask='auto')
            y -= 6
        else:
            p.setFont("Helvetica-Bold", 11)
            p.drawCentredString(CENTER_X, y * mm, "OPTICA IC")
            y -= 8

        # ====== RUC / Dirección / Celulares ======
        p.setFont("Helvetica", 9.5)
        p.drawCentredString(CENTER_X, y * mm, RUC_EMPRESA); y -= 4
        for ln in wrap_text(DIR_EMPRESA, 32):
            p.drawCentredString(CENTER_X, y * mm, ln); y -= 4
        for ln in wrap_text(TELS_EMPRESA, 32):
            p.drawCentredString(CENTER_X, y * mm, ln); y -= 8

        # ====== Número + COPIA ======
        p.setFont("Helvetica-Bold", 11)
        p.drawCentredString(CENTER_X, y * mm, f"Recibo N\u00B0 {numero_formateado}")
        y -= 5
        p.setFont("Helvetica-Bold", 9.5)
        #p.drawCentredString(CENTER_X, y * mm, f"COPIA {copia_n}/3")
        y -= 7

        # ====== Datos del cliente ======
        p.setFont("Helvetica", 9.5)
        p.drawString(LEFT_X, y * mm, f"Cliente: {cliente}"); y -= 5
        p.drawString(LEFT_X, y * mm, f"Teléfono: {telefono}"); y -= 5
        p.drawString(LEFT_X, y * mm, f"Vendedor: {vendedor}"); y -= 5
        p.drawString(LEFT_X, y * mm, f"Emisión: {fecha_sistema} {hora_sistema}"); y -= 5
        p.drawString(LEFT_X, y * mm, f"Entrega: {fecha_entrega} {hora_entrega}"); y -= 6

        hr(y); y -= 6

        # Encabezado productos
        p.setFont("Helvetica-Bold", 9.5)
        p.drawString(COL_QTY_X, y * mm, "Cant.")
        p.drawString(COL_DESC_X, y * mm, "Producto")
        p.drawRightString(COL_SUBTOTAL_X, y * mm, "Subtotal")
        y -= 5
        p.setFont("Helvetica", 9.5)

        # Productos
        for item in detalles:
            cantidad = str(item.get("cantidad", "1"))
            descripcion = item.get("descripcion", "")
            precio = float(item.get("precio", 0) or 0)

            subtotal = precio
            total += subtotal

            lineas_desc = textwrap.wrap(descripcion, 24) or [""]

            p.drawString(COL_QTY_X, y * mm, cantidad)
            p.drawRightString(COL_SUBTOTAL_X, y * mm, f"{subtotal:.2f}")
            p.drawString(COL_DESC_X, y * mm, lineas_desc[0])
            y -= 5

            for desc_line in lineas_desc[1:]:
                p.drawString(COL_DESC_X, y * mm, desc_line)
                y -= 5

            # Si llega al final, mejor: cortar ahí (para tiquetera)
            if y < 25:
                hr(y); y -= 6
                p.setFont("Helvetica-Oblique", 9)
                #p.drawCentredString(CENTER_X, y * mm, "— Separa aquí —")
                return  # termina este recibo aquí

        # Totales
        hr(y); y -= 6
        p.setFont("Helvetica-Bold", 10)
        p.drawRightString(COL_SUBTOTAL_X, y * mm, f"Total: S/ {total:.2f}"); y -= 5
        p.drawRightString(COL_SUBTOTAL_X, y * mm, f"A cuenta: S/ {a_cuenta}"); y -= 5
        p.drawRightString(COL_SUBTOTAL_X, y * mm, f"Saldo: S/ {saldo}"); y -= 8

        # Despedida + puntos
        p.setFont("Helvetica-Bold", 10)
        p.drawCentredString(CENTER_X, y * mm, "¡Gracias por su preferencia!")
        y -= 6

        msg = f"Ud ha ganado {puntos_int} puntos IC que podrá canjear en su próxima compra"
        p.setFont("Helvetica", 9.5)
        for ln in wrap_text(msg, 34):
            p.drawCentredString(CENTER_X, y * mm, ln)
            y -= 5

        # Corte del recibo
        y -= 2
        hr(y); y -= 6
        p.setFont("Helvetica-Oblique", 9)
        #p.drawCentredString(CENTER_X, y * mm, "— Separa aquí —")

    # =========================================================
    # ✅ 1) IMPRIMIR RECIBO 3 VECES (3 hojas)
    # =========================================================
    for copia in (1, 2, 3):
        dibujar_recibo(copia)
        p.showPage()  # siguiente hoja (corte)

    # =========================================================
    # ✅ 2) IMPRIMIR OT 1 VEZ (1 hoja)
    #    (OJO: tu OT ya NO debe hacer p.showPage() al inicio)
    # =========================================================
    dibujar_orden_trabajo(
        p,
        ancho_mm=WIDTH_MM,
        alto_mm=HEIGHT_MM,
        numero=numero_formateado,
        productos=nombres_productos,
        fecha_emision=fecha_sistema,
        hora_emision=hora_sistema,
        fecha_entrega=fecha_entrega,
        hora_entrega=hora_entrega,
        telefono=telefono,
        cliente=cliente,
        vendedor=vendedor,
        receta=receta_data,
    )
    p.showPage()

    p.save()
    pdf_value = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf_value, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="ticket.pdf"'
    return response


from io import BytesIO
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from datetime import datetime

from .models import MedidaVista  # ajusta si tu modelo se llama distinto

def receta_pdf(request, medida_id):
    medida = get_object_or_404(MedidaVista, id=medida_id)
    cliente = medida.cliente  # ajusta si tu FK se llama diferente

    buffer = BytesIO()

    WIDTH_MM = 80
    HEIGHT_MM = 270
    PAGE_W = WIDTH_MM * mm
    PAGE_H = HEIGHT_MM * mm

    p = canvas.Canvas(buffer, pagesize=(PAGE_W, PAGE_H))

    receta_data = {
        "esf_lejos_OD": medida.esf_lejos_OD,
        "cil_lejos_OD": medida.cil_lejos_OD,
        "eje_lejos_OD": medida.eje_lejos_OD,
        "DIP_lejos_OD": medida.DIP_lejos_OD,
        "Add_lejos_OD": getattr(medida, "Add_lejos_OD", ""),
        "AV_lejos_OD": getattr(medida, "AV_lejos_OD", ""),

        "esf_lejos_OI": medida.esf_lejos_OI,
        "cil_lejos_OI": medida.cil_lejos_OI,
        "eje_lejos_OI": medida.eje_lejos_OI,
        "DIP_lejos_OI": medida.DIP_lejos_OI,
        "Add_lejos_OI": getattr(medida, "Add_lejos_OI", ""),
        "AV_lejos_OI": getattr(medida, "AV_lejos_OI", ""),

        "esf_cerca_OD": getattr(medida, "esf_cerca_OD", ""),
        "cil_cerca_OD": getattr(medida, "cil_cerca_OD", ""),
        "eje_cerca_OD": getattr(medida, "eje_cerca_OD", ""),
        "DIP_cerca_OD": getattr(medida, "DIP_cerca_OD", ""),
        "AV_cerca_OD": getattr(medida, "AV_cerca_OD", ""),

        "esf_cerca_OI": getattr(medida, "esf_cerca_OI", ""),
        "cil_cerca_OI": getattr(medida, "cil_cerca_OI", ""),
        "eje_cerca_OI": getattr(medida, "eje_cerca_OI", ""),
        "DIP_cerca_OI": getattr(medida, "DIP_cerca_OI", ""),
        "AV_cerca_OI": getattr(medida, "AV_cerca_OI", ""),
    }

    # Datos básicos
    fecha_emision = datetime.now().strftime("%d/%m/%Y")
    vendedor = request.user.get_full_name() or request.user.username

    # >>> REUSA tu helper tal cual lo tienes <<<
    dibujar_receta(
        p,
        ancho_mm=WIDTH_MM,
        alto_mm=HEIGHT_MM,
        cliente=getattr(cliente, "nombre", str(cliente)),
        telefono=getattr(cliente, "telefono", ""),
        fecha_emision=fecha_emision,
        vendedor=vendedor,
        receta=receta_data,
    )

    p.save()
    pdf_value = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf_value, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="receta.pdf"'
    return response



# views.py (añadir al final o donde prefieras)
from django.views.decorators.http import require_POST
from django.http import HttpResponseBadRequest

import json
from decimal import Decimal

from django.db import transaction
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt

from .models import (
    TicketVenta,
    DetalleTicketVenta,
    ReciboCorrelativo,
    Cliente,
    Producto,
)

@login_required
@role_required("ADMIN", "SUPERVISOR", "CAJA", "VENDEDOR")
@require_POST
def guardar_ticket(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Método no permitido")

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponseBadRequest("JSON inválido")

    with transaction.atomic():
        # 1) Obtener/actualizar correlativo
        correlativo, _ = ReciboCorrelativo.objects.select_for_update().get_or_create(pk=1)
        correlativo.numero_actual += 1
        numero = correlativo.numero_actual
        correlativo.save()

        # 2) Buscar cliente por nombre (opcional; ajusta según tu lógica)
        nombre_cliente = data.get("cliente") or ""
        cliente = None
        if nombre_cliente:
            cliente = Cliente.objects.filter(nombre=nombre_cliente).first()

        # ====== Montos y medio de pago (vienen del JSON) ======
        total = Decimal(str(data.get("total", "0") or "0"))
        a_cuenta = Decimal(str(data.get("a_cuenta", "0") or "0"))
        medio_pago = (data.get("medio_pago") or "").strip().upper()  # EFECTIVO/YAPE/TARJETA/TRANSFERENCIA

        # saldo: mejor calcularlo aquí
        saldo = total - a_cuenta
        if saldo < 0:
            saldo = Decimal("0")

        # 3) Crear TicketVenta
        ticket = TicketVenta.objects.create(
            numero=numero,
            cliente=cliente,
            vendedor=data.get("vendedor", ""),
            fecha_entrega=data.get("fecha_entrega", ""),
            hora_entrega=data.get("hora_entrega", ""),
            total=total,
            a_cuenta=a_cuenta,
            saldo=saldo,
            puntos_ic=int(data.get("puntos_ic", 0) or 0),
        )
        OrdenTrabajo.objects.create(
            ticket=ticket,
            estado="LAB_PEDIDO",
            ts_lab_pedido=timezone.now()
        )


        # 3.1) Registrar PagoTicket (abono)
        # Validar medio_pago contra los choices (por si mandan algo raro)
        medios_validos = {"EFECTIVO", "YAPE", "TARJETA", "TRANSFERENCIA"}
        if a_cuenta > 0 and medio_pago in medios_validos:
            PagoTicket.objects.create(
                ticket=ticket,
                medio_pago=medio_pago,
                monto=a_cuenta
            )
        productos_afectados = set()
        # 4) Crear detalles y DESCONTAR STOCK
        for det in data.get("detalles", []):
            descripcion = det.get("descripcion", "")
            cantidad = int(det.get("cantidad", 0) or 0)
            precio = Decimal(str(det.get("precio", "0") or "0"))
            cod = det.get("cod") or ""

            producto = None
            if cod:
                producto = Producto.objects.select_for_update().filter(cod=cod).first()
            if not producto and descripcion:
                producto = Producto.objects.select_for_update().filter(descripcion=descripcion).first()

            DetalleTicketVenta.objects.create(
                ticket_numero=ticket,
                producto=producto,
                descripcion=descripcion,
                cantidad=cantidad,
                precio=precio,
            )

            if producto:
                if producto.stock < cantidad:
                    raise ValueError(f"Stock insuficiente para {producto.descripcion}")
                producto.stock -= cantidad
                producto.save(update_fields=["stock"])

                # ✅ AQUI: marca el producto para recalcular kardex al final
                productos_afectados.add(producto.id)

        # ✅ AQUI: después del for, recalcula el kardex de todos los productos vendidos
        for pid in productos_afectados:
            recalcular_kardex_producto(Producto.objects.get(id=pid))


    return JsonResponse({"ok": True, "numero": numero})


def dibujar_orden_trabajo(p, ancho_mm=80, alto_mm=270, *, numero=None, productos=None,
                          fecha_emision=None, hora_emision=None, fecha_entrega=None, hora_entrega=None, telefono=None, cliente=None, vendedor=None, receta=None):
    """
    Dibuja la 2da hoja (Orden de trabajo) en el canvas 'p'.
    Usa el mismo tamaño de página térmica (90mm x 270mm).
    """
    # Nueva página
    #p.showPage()
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
    p.setFont("Helvetica", 9)

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
    col_x = [x_izq, x_izq+10, x_izq+20, x_izq+30, x_izq+40, x_izq+50, x_izq+60]  # mm aprox en rollo 80/90mm
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
        colc_x = [x_izq, x_izq+10, x_izq+20, x_izq+30, x_izq+40, x_izq+50]
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
    #p.drawCentredString(x_centro, y * mm, "— Separa aquí —")


# --- 3ra hoja: RECETA ---
def dibujar_receta(p, *, ancho_mm=80, alto_mm=270, cliente=None, telefono=None,
                   fecha_emision=None, vendedor=None, receta=None):
    """
    Dibuja la hoja de RECETA. 'receta' es un dict con campos:
    - esf_lejos_OD, cil_lejos_OD, eje_lejos_OD, DIP_lejos_OD, Add_lejos_OD, AV_lejos_OD
    - esf_lejos_OI, cil_lejos_OI, eje_lejos_OI, DIP_lejos_OI, Add_lejos_OI, AV_lejos_OI
    - esf_cerca_OD, cil_cerca_OD, eje_cerca_OD, DIP_cerca_OD, AV_cerca_OD
    - esf_cerca_OI, cil_cerca_OI, eje_cerca_OI, DIP_cerca_OI, AV_cerca_OI
    (puedes enviar solo “lejos” si no hay “cerca”)
    """
#    p.showPage()  # nueva página
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
    col_x = [x_izq, x_izq+10, x_izq+20, x_izq+30, x_izq+40, x_izq+50, x_izq+60]  # mm aprox en rollo 80/90mm
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
        p.setFont("Helvetica-Bold", 9)
        p.drawString(x_izq * mm, y * mm, "Visión de Cerca")
        y -= 6
        p.setFont("Helvetica", 9)
        headers_c = ["","Esf", "Cil", "Eje", "DIP", "AV"]
        colc_x = [x_izq, x_izq+10, x_izq+20, x_izq+30, x_izq+40, x_izq+50]
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
    #p.drawCentredString(x_centro, y * mm, "— Separa aquí —")
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
@role_required("ADMIN", "SUPERVISOR")
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

            productos_afectados = set()

            for i in range(len(cods)):
                cod = cods[i].strip()
                if not cod:
                    continue  # fila vacía

                descripcion = descripciones[i].strip()
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
                    }
                )

                # 🔹 2. Si ya existía, ACTUALIZAR datos y aumentar stock
                if not creado:
                    producto.descripcion = descripcion or producto.descripcion
                    producto.precio_compra = pc
                    producto.precio_venta = pv
                    producto.stock = (producto.stock or 0) + cant
                    producto.save()
                else:
                    # si es nuevo, ya se guardó con el stock inicial
                    producto.save()
                
                productos_afectados.add(producto.id)

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

            for pid in productos_afectados:
                producto = Producto.objects.get(id=pid)
                recalcular_kardex_producto(producto)

            return redirect('lista_compras')  # o donde quieras

    else:
        compra_form = CompraForm()

    return render(request, 'core/registro_compra.html', {
        'compra_form': compra_form,
    })

@role_required("ADMIN", "SUPERVISOR")
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

@role_required("ADMIN", "SUPERVISOR")
def lista_compras(request):
    compras = Compra.objects.select_related('proveedor').order_by('-fecha', '-id')
    return render(request, 'core/lista_compras.html', {
        'compras': compras
    })

@role_required("ADMIN", "SUPERVISOR")
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
@role_required("ADMIN", "SUPERVISOR")
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

@role_required("ADMIN", "SUPERVISOR")
def lista_detalles_compra(request):
    detalles = DetalleCompra.objects.select_related('compra', 'producto', 'compra__proveedor').order_by('-compra__fecha', '-id')
    return render(request, 'core/lista_detalles_compra.html', {
        'detalles': detalles
    })


@transaction.atomic
@role_required("ADMIN", "SUPERVISOR")
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
@role_required("ADMIN", "SUPERVISOR")
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
@role_required("ADMIN", "SUPERVISOR", "TALLER", "CAJA","VENDEDOR")
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
@role_required("ADMIN", "SUPERVISOR", "CAJA","VENDEDOR")
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
        clientes = clientes.filter(fecha_registro__date=fecha)

    return render(request, 'core/lista_clientes.html', {
        'clientes': clientes
    })

@role_required("ADMIN", "SUPERVISOR", "CAJA","VENDEDOR")
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

@role_required("ADMIN", "SUPERVISOR", "CAJA","VENDEDOR")
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
@role_required("ADMIN", "SUPERVISOR", "CAJA","VENDEDOR")
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
@role_required("ADMIN", "SUPERVISOR", "CAJA","VENDEDOR")
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

@role_required("ADMIN", "SUPERVISOR", "CAJA","VENDEDOR")
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

@role_required("ADMIN", "SUPERVISOR", "CAJA","VENDEDOR")
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


@role_required("ADMIN", "SUPERVISOR", "CAJA","VENDEDOR")
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

@role_required("ADMIN", "SUPERVISOR", "CAJA","VENDEDOR")
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

@role_required("ADMIN", "SUPERVISOR", "CAJA","VENDEDOR")
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

@role_required("ADMIN", "SUPERVISOR", "CAJA","VENDEDOR")
def ultimas_medidas(request):
    """
    Devuelve las 10 MedidaVista más recientes
    para llenar la lista desplegable.
    """
    qs = (
        MedidaVista.objects
        .select_related("cliente")
        .order_by("-fecha_registro", "-id")[:9]
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

@role_required("ADMIN", "SUPERVISOR", "CAJA","VENDEDOR")
def ticket_detalle(request, numero):
    ticket = get_object_or_404(TicketVenta, numero=numero)
    detalles = DetalleTicketVenta.objects.filter(ticket_numero=ticket)

    return render(request, "core/ticket_detalle.html", {
        "ticket": ticket,
        "detalles": detalles,
    })

def _wrap_text(pdf, text, max_width_pt, font_name="Helvetica", font_size=10):
    """
    Envuelve texto a varias líneas para que no exceda max_width_pt (puntos).
    Incluye fallback para cortar palabras largas sin espacios.
    """
    if text is None:
        text = ""
    text = str(text)

    pdf.setFont(font_name, font_size)

    words = text.split()
    lines = []
    current = ""

    for w in words:
        test = (current + " " + w).strip()
        if pdf.stringWidth(test, font_name, font_size) <= max_width_pt:
            current = test
        else:
            if current:
                lines.append(current)
            current = w

    if current:
        lines.append(current)

    # Fallback: cortar por caracteres si una palabra/línea queda muy larga
    fixed = []
    for line in (lines or [""]):
        if pdf.stringWidth(line, font_name, font_size) <= max_width_pt:
            fixed.append(line)
        else:
            chunk = ""
            for ch in line:
                test = chunk + ch
                if pdf.stringWidth(test, font_name, font_size) <= max_width_pt:
                    chunk = test
                else:
                    if chunk:
                        fixed.append(chunk)
                    chunk = ch
            if chunk:
                fixed.append(chunk)

    return fixed or [""]

from io import BytesIO
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from django.contrib.staticfiles import finders
import os, json, textwrap

# from core.models import TicketVenta  # <-- ajusta import
# Si tienes un modelo detalle:
# from core.models import TicketVentaDetalle

from io import BytesIO
import os, json, textwrap
from datetime import datetime, date

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.contrib.staticfiles import finders

from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader

from core.models import TicketVenta  # <-- ajusta si tu app/modelo cambia


def imprimir_ticket_pdf(request):
    buffer = BytesIO()

    # ========= AJUSTE REAL PARA TIQUETERA =========
    WIDTH_MM = 80
    HEIGHT_MM = 270
    MARGIN_MM = 3

    PAGE_W = WIDTH_MM * mm
    PAGE_H = HEIGHT_MM * mm

    LEFT_X   = MARGIN_MM * mm
    RIGHT_X  = (WIDTH_MM - MARGIN_MM) * mm
    CENTER_X = (WIDTH_MM / 2) * mm

    COL_QTY_X      = LEFT_X
    COL_DESC_X     = (MARGIN_MM + 12) * mm
    COL_SUBTOTAL_X = (WIDTH_MM - MARGIN_MM) * mm

    p = canvas.Canvas(buffer, pagesize=(PAGE_W, PAGE_H))

    # =========================
    # DATOS EMPRESA
    # =========================
    RUC_EMPRESA = "RUC: 10429550101"
    DIR_EMPRESA = "Dirección: Jr. Camaná N° 560, Cercado de Lima"
    TELS_EMPRESA = "Cel: 952305913 / 914300701"

    def wrap_text(text, max_chars=32):
        return textwrap.wrap(str(text or ""), max_chars) or [""]

    def hr(y_mm):
        y = y_mm * mm
        p.line(LEFT_X, y, RIGHT_X, y)

    # =========================
    # 1) TRAER TICKET DESDE BD
    # =========================
    ticket_id = request.GET.get("ticket_id")
    numero = request.GET.get("numero")  # en tu URL: ?numero=5 (parece ser ID)

    ticket = None
    if ticket_id:
        ticket = get_object_or_404(TicketVenta, pk=ticket_id)
    elif numero:
        try:
            ticket = get_object_or_404(TicketVenta, pk=int(numero))
        except Exception:
            ticket = None

    # =========================
    # 2) ARMAR VARIABLES (BD primero; GET fallback)
    # =========================
    detalles = []
    receta_data = {}
    nombres_productos = []

    if ticket:
        # ---- Cliente ----
        cli = getattr(ticket, "cliente", None)
        cliente_nombre = (
            getattr(cli, "nombre", None)
            or getattr(cli, "nombres", None)
            or getattr(cli, "razon_social", None)
            or (str(cli) if cli else "")
        )
        cliente_telefono = getattr(cli, "telefono", "") if cli else ""

        # ---- Vendedor ----
        vend_obj = getattr(ticket, "vendedor", None) or getattr(ticket, "usuario", None)
        if vend_obj:
            vendedor = (
                getattr(vend_obj, "get_full_name", lambda: "")()  # si es User
                or getattr(vend_obj, "username", "")
                or str(vend_obj)
            )
        else:
            vendedor = ""

        # ---- Fecha de emisión ----
        fecha_dt = (
            getattr(ticket, "fecha_emision", None)
            or getattr(ticket, "fecha_registro", None)
            or getattr(ticket, "created_at", None)
        )
        if isinstance(fecha_dt, datetime):
            fecha_sistema = fecha_dt.strftime("%d/%m/%Y")
        elif isinstance(fecha_dt, date):
            fecha_sistema = fecha_dt.strftime("%d/%m/%Y")
        else:
            fecha_sistema = timezone.now().strftime("%d/%m/%Y")

        # ✅ Hora de emisión (TimeField auto_now_add)
        he = getattr(ticket, "hora_emision", None)
        if he:
            hora_sistema = he.strftime("%H:%M")
        else:
            hora_sistema = timezone.now().strftime("%H:%M")

        # ---- Fecha de entrega ----
        fe = getattr(ticket, "fecha_entrega", None)
        if isinstance(fe, datetime):
            fecha_entrega = fe.strftime("%d/%m/%Y")
        elif isinstance(fe, date):
            fecha_entrega = fe.strftime("%d/%m/%Y")
        elif isinstance(fe, str) and fe.strip():
            fecha_entrega = fe.strip()
        else:
            fecha_entrega = timezone.now().strftime("%d/%m/%Y")

        # ✅ Hora de entrega (CharField)
        hora_entrega = (getattr(ticket, "hora_entrega", "") or "").strip()
        if not hora_entrega:
            hora_entrega = "--:--"

        # ---- Totales/pagos (ajusta si tus campos se llaman distinto) ----
        a_cuenta = f"{float(getattr(ticket, 'a_cuenta', 0) or 0):.2f}"
        saldo    = f"{float(getattr(ticket, 'saldo', 0) or 0):.2f}"
        puntos_ic_val = getattr(ticket, "puntos_ic", None)

        # ---- Número ticket ----
        numero_formateado = f"{ticket.id:06d}"

        # ---- Detalles (RELACIÓN) ----
        rel = getattr(ticket, "detalles", None) or getattr(ticket, "items", None)
        if rel is not None and hasattr(rel, "all"):
            for d in rel.all():
                # ajusta nombres según tu detalle real
                desc = (
                    getattr(d, "descripcion", None)
                    or getattr(getattr(d, "producto", None), "descripcion", "")
                    or str(getattr(d, "producto", "") or "")
                )
                qty = getattr(d, "cantidad", 1) or 1
                pu  = getattr(d, "precio", None) or getattr(d, "precio_unitario", None) or 0
                detalles.append({"descripcion": desc, "cantidad": qty, "precio": float(pu or 0)})

        # ---- Detalles (JSON fallback) ----
        if not detalles:
            dj = getattr(ticket, "detalles_json", None) or getattr(ticket, "detalles", None)
            if isinstance(dj, str) and dj.strip():
                try:
                    detalles = json.loads(dj)
                except Exception:
                    detalles = []

        # ---- Receta (JSON si existe) ----
        rj = getattr(ticket, "receta_json", None) or getattr(ticket, "receta", None)
        if isinstance(rj, str) and rj.strip():
            try:
                receta_data = json.loads(rj)
            except Exception:
                receta_data = {}
        else:
            receta_data = {}

        # ---- Puntos ----
        try:
            puntos_int = int(float(puntos_ic_val)) if puntos_ic_val is not None else 0
        except Exception:
            puntos_int = 0

    else:
        # ===== FALLBACK GET (por si llamas sin BD) =====
        cliente_nombre = request.GET.get("cliente", "Cliente no definido")
        cliente_telefono = request.GET.get("telefono", "")
        vendedor = request.GET.get("vendedor", "")

        fecha_sistema = request.GET.get("fecha_sistema", timezone.now().strftime("%d/%m/%Y"))
        hora_sistema  = request.GET.get("hora_sistema", timezone.now().strftime("%H:%M"))

        fecha_entrega = request.GET.get("fecha_entrega", timezone.now().strftime("%d/%m/%Y"))
        hora_entrega  = request.GET.get("hora_entrega", "--:--")

        a_cuenta = request.GET.get("a_cuenta", "0.00")
        saldo    = request.GET.get("saldo", "0.00")

        puntos_ic = request.GET.get("puntos_ic", "0.00")
        try:
            puntos_int = int(float(puntos_ic))
        except Exception:
            puntos_int = 0

        detalles_json = request.GET.get("detalles", "[]")
        try:
            detalles = json.loads(detalles_json)
        except Exception:
            detalles = []

        numero = request.GET.get("numero")
        if not numero:
            ultimo_id = TicketVenta.objects.order_by("-id").values_list("id", flat=True).first()
            numero = ultimo_id or 1
        try:
            numero_formateado = f"{int(numero):06d}"
        except Exception:
            numero_formateado = "000001"

        receta_data = {}
        rj = request.GET.get("receta")
        if rj:
            try:
                receta_data = json.loads(rj)
            except Exception:
                receta_data = {}

    # Nombres de productos para OT
    nombres_productos = []
    for item in detalles:
        desc = str(item.get("descripcion", "")).strip()
        if desc:
            nombres_productos.append(desc)

    # =========================================================
    # ✅ DIBUJAR 1 RECIBO EN LA HOJA ACTUAL
    # =========================================================
    def dibujar_recibo(copia_n: int):
        total = 0.0
        y = 257  # mm

        # ====== LOGO ======
        ruta_logo = finders.find("core/img/logo.png")
        if ruta_logo and os.path.exists(ruta_logo):
            logo = ImageReader(ruta_logo)
            ancho_logo_pt = 90
            alto_logo_pt = 35
            x_centro_logo = (PAGE_W - ancho_logo_pt) / 2
            p.drawImage(
                logo, x_centro_logo, y * mm,
                width=ancho_logo_pt, height=alto_logo_pt,
                preserveAspectRatio=True, mask="auto"
            )
            y -= 6
        else:
            p.setFont("Helvetica-Bold", 11)
            p.drawCentredString(CENTER_X, y * mm, "OPTICA IC")
            y -= 8

        # Empresa
        p.setFont("Helvetica", 9.5)
        p.drawCentredString(CENTER_X, y * mm, RUC_EMPRESA); y -= 4
        for ln in wrap_text(DIR_EMPRESA, 32):
            p.drawCentredString(CENTER_X, y * mm, ln); y -= 4
        for ln in wrap_text(TELS_EMPRESA, 32):
            p.drawCentredString(CENTER_X, y * mm, ln); y -= 8

        # Ticket
        p.setFont("Helvetica-Bold", 11)
        p.drawCentredString(CENTER_X, y * mm, f"Recibo N\u00B0 {numero_formateado}")
        y -= 12

        # Datos cliente
        p.setFont("Helvetica", 9.5)
        p.drawString(LEFT_X, y * mm, f"Cliente: {cliente_nombre}"); y -= 5
        p.drawString(LEFT_X, y * mm, f"Teléfono: {cliente_telefono}"); y -= 5
        p.drawString(LEFT_X, y * mm, f"Vendedor: {vendedor}"); y -= 5
        p.drawString(LEFT_X, y * mm, f"Emisión: {fecha_sistema} {hora_sistema}"); y -= 5
        p.drawString(LEFT_X, y * mm, f"Entrega: {fecha_entrega} {hora_entrega}"); y -= 6

        hr(y); y -= 6

        # Encabezado productos
        p.setFont("Helvetica-Bold", 9.5)
        p.drawString(COL_QTY_X, y * mm, "Cant.")
        p.drawString(COL_DESC_X, y * mm, "Producto")
        p.drawRightString(COL_SUBTOTAL_X, y * mm, "Subtotal")
        y -= 5
        p.setFont("Helvetica", 9.5)

        # Productos
        for item in detalles:
            qty = float(item.get("cantidad", 1) or 1)
            descripcion = str(item.get("descripcion", "") or "")
            precio_unit = float(item.get("precio", 0) or 0)

            subtotal = qty * precio_unit
            total += subtotal

            lineas_desc = textwrap.wrap(descripcion, 24) or [""]

            p.drawString(COL_QTY_X, y * mm, str(int(qty)) if qty.is_integer() else str(qty))
            p.drawRightString(COL_SUBTOTAL_X, y * mm, f"{subtotal:.2f}")
            p.drawString(COL_DESC_X, y * mm, lineas_desc[0])
            y -= 5

            for desc_line in lineas_desc[1:]:
                p.drawString(COL_DESC_X, y * mm, desc_line)
                y -= 5

            if y < 25:
                hr(y); y -= 6
                return

        # Totales
        hr(y); y -= 6
        p.setFont("Helvetica-Bold", 10)
        p.drawRightString(COL_SUBTOTAL_X, y * mm, f"Total: S/ {total:.2f}"); y -= 5
        p.drawRightString(COL_SUBTOTAL_X, y * mm, f"A cuenta: S/ {a_cuenta}"); y -= 5
        p.drawRightString(COL_SUBTOTAL_X, y * mm, f"Saldo: S/ {saldo}"); y -= 8

        # Despedida
        p.setFont("Helvetica-Bold", 10)
        p.drawCentredString(CENTER_X, y * mm, "¡Gracias por su preferencia!")
        y -= 6

        msg = f"Ud ha ganado {puntos_int} puntos IC que podrá canjear en su próxima compra"
        p.setFont("Helvetica", 9.5)
        for ln in wrap_text(msg, 34):
            p.drawCentredString(CENTER_X, y * mm, ln)
            y -= 5

        y -= 2
        hr(y); y -= 6

    # =========================================================
    # ✅ 1) IMPRIMIR RECIBO 3 VECES (3 hojas)
    # =========================================================
    for copia in (1, 2, 3):
        dibujar_recibo(copia)
        p.showPage()

    # =========================================================
    # ✅ 2) IMPRIMIR OT 1 VEZ
    #    (tu función debe existir y NO hacer showPage() al inicio)
    # =========================================================
    dibujar_orden_trabajo(
        p,
        ancho_mm=WIDTH_MM,
        alto_mm=HEIGHT_MM,
        numero=numero_formateado,
        productos=nombres_productos,
        fecha_emision=fecha_sistema,
        hora_emision=hora_sistema,
        fecha_entrega=fecha_entrega,
        hora_entrega=hora_entrega,
        telefono=cliente_telefono,
        cliente=cliente_nombre,
        vendedor=vendedor,
        receta=receta_data,
    )
    p.showPage()

    p.save()
    pdf_value = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf_value, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="ticket.pdf"'
    return response


@role_required("ADMIN", "SUPERVISOR")
@role_required("ADMIN", "SUPERVISOR", "CAJA","VENDEDOR")
def kardex_resumen(request):
    productos = Producto.objects.filter(activo=True).order_by("descripcion")

    data = []
    for p in productos:
        stock = p.stock or 0

        # ✅ toma el último costo_promedio del kardex; si no existe, usa precio_compra del producto
        ultimo = (KardexMovimiento.objects
                  .filter(producto=p)
                  .order_by("-fecha", "-id")
                  .first())

        if ultimo:
            costo_prom = ultimo.costo_promedio
        else:
            costo_prom = p.precio_compra or Decimal("0")

        valor = Decimal(stock) * Decimal(costo_prom)

        data.append({
            "producto": p,
            "stock": stock,
            "costo_prom": costo_prom,
            "valor": valor,
        })

    total_valor = sum((x["valor"] for x in data), Decimal("0"))

    return render(request, "core/kardex_resumen.html", {
        "data": data,
        "total_valor": total_valor,
    })

@role_required("ADMIN", "SUPERVISOR", "CAJA","VENDEDOR")
def kardex_detalle(request, producto_id):
    """
    GET /kardex/<producto_id>/
    Movimientos del producto en Kardex
    """
    producto = get_object_or_404(Producto, pk=producto_id)

    # Ajusta si tu modelo tiene otro nombre o app
    movimientos = KardexMovimiento.objects.filter(producto=producto).order_by("fecha", "id")

    return render(request, "core/kardex_detalle.html", {
        "producto": producto,
        "movimientos": movimientos,
    })

@transaction.atomic
def recalcular_kardex_producto2(producto: Producto):
    KardexMovimiento.objects.filter(producto=producto).delete()

    stock = Decimal("0")
    costo_prom = Decimal("0")

    eventos = []

    # ENTRADAS (compras)
    for dc in DetalleCompra.objects.filter(producto=producto).select_related("compra"):
        # Compra.fecha es DateField -> lo convertimos a datetime
        fecha_dt = datetime.combine(dc.compra.fecha, time(0, 0))
        eventos.append(("IN", fecha_dt, Decimal(dc.cantidad), Decimal(dc.precio_compra), dc.compra, None))

    # SALIDAS (ventas)
    for dv in DetalleTicketVenta.objects.filter(producto=producto).select_related("ticket_numero"):
        t = dv.ticket_numero
        fecha_dt = datetime.combine(t.fecha_emision, t.hora_emision)
        eventos.append(("OUT", fecha_dt, Decimal(dv.cantidad), None, None, t))

    eventos.sort(key=lambda x: x[1])

    for tipo, fecha_dt, cantidad, costo_in, compra_ref, ticket_ref in eventos:
        if tipo == "IN":
            nuevo_stock = stock + cantidad
            nuevo_costo_prom = ((stock * costo_prom) + (cantidad * costo_in)) / nuevo_stock if nuevo_stock > 0 else Decimal("0")

            KardexMovimiento.objects.create(
                producto=producto,
                fecha=fecha_dt,
                tipo="IN",
                cantidad=cantidad,
                costo_unitario=costo_in,
                costo_total=cantidad * costo_in,
                stock_anterior=stock,
                stock_actual=nuevo_stock,
                costo_promedio=nuevo_costo_prom,
                compra=compra_ref
            )

            stock = nuevo_stock
            costo_prom = nuevo_costo_prom

        else:
            nuevo_stock = stock - cantidad

            KardexMovimiento.objects.create(
                producto=producto,
                fecha=fecha_dt,
                tipo="OUT",
                cantidad=cantidad,
                costo_unitario=costo_prom,
                costo_total=cantidad * costo_prom,
                stock_anterior=stock,
                stock_actual=nuevo_stock,
                costo_promedio=costo_prom,
                ticket=ticket_ref
            )

            stock = nuevo_stock

    # opcional: sincronizar stock real al producto
    producto.stock = int(stock)
    producto.save()

from .caja import get_or_create_caja

@role_required("ADMIN", "SUPERVISOR", "CAJA", "VENDEDOR")
def caja_cobrar_saldo(request, fecha, ticket_id):
    fecha_dt = datetime.strptime(fecha, "%Y-%m-%d").date()
    caja = get_or_create_caja(fecha_dt)
    ticket = get_object_or_404(TicketVenta, pk=ticket_id)

    if request.method == "POST":
        if caja.cerrada:
            messages.error(request, "La caja está cerrada.")
            return redirect("caja_detalle", fecha=fecha)

        monto = Decimal(request.POST.get("monto") or "0")
        medio = request.POST.get("medio_pago") or "EFECTIVO"

        if monto <= 0:
            messages.error(request, "Monto inválido.")
            return redirect("caja_detalle", fecha=fecha)

        MovimientoCaja.objects.create(
            caja=caja,
            tipo="IN",
            medio_pago=medio,
            categoria="VENTA" if ticket.fecha_emision == fecha_dt else "COBRANZA",
            descripcion=f"Cobro saldo ticket #{ticket.numero}",
            monto=monto,
            ticket=ticket,
            fuente="MANUAL",
        )

        return redirect("caja_detalle", fecha=fecha)

    return redirect("caja_detalle", fecha=fecha)

from .caja import importar_cobros_a_caja

@role_required("ADMIN", "SUPERVISOR", "CAJA", "VENDEDOR")
def caja_importar_ventas(request, fecha):
    fecha_dt = datetime.strptime(fecha, "%Y-%m-%d").date()
    importar_cobros_a_caja(fecha_dt)
    return redirect("caja_detalle", fecha=fecha)

@role_required("ADMIN", "CAJA", "VENDEDOR")
@role_required("ADMIN", "SUPERVISOR", "CAJA")
def caja_hoy(request):
    """
    Redirige a la caja del día actual
    """
    hoy = timezone.localdate()
    return redirect("caja_detalle", fecha=hoy.strftime("%Y-%m-%d"))

@role_required("ADMIN", "SUPERVISOR", "CAJA", "VENDEDOR")
def caja_detalle(request, fecha):
    """
    Muestra la caja de una fecha específica
    """
    fecha_dt = datetime.strptime(fecha, "%Y-%m-%d").date()

    # obtiene o crea la caja del día
    caja = get_or_create_caja(fecha_dt)

    # movimientos del día
    movimientos = caja.movimientos.all().order_by("-fecha_hora")

    def neto_por_medio(medio):
        ing = caja.movimientos.filter(tipo="IN", medio_pago=medio).aggregate(s=Sum("monto"))["s"] or Decimal("0.00")
        eg  = caja.movimientos.filter(tipo="OUT", medio_pago=medio).aggregate(s=Sum("monto"))["s"] or Decimal("0.00")
        return ing - eg

    esperado_efectivo = neto_por_medio("EFECTIVO") + Decimal(caja.saldo_inicial or 0)  # saldo inicial se asume efectivo
    esperado_yape = neto_por_medio("YAPE")
    esperado_tarjeta = neto_por_medio("TARJETA")
    esperado_transferencia = neto_por_medio("TRANSFERENCIA")




    return render(request, "core/caja_detalle.html", {
        "caja": caja,
        "movs": movimientos,
        "esperado_efectivo": esperado_efectivo,
        "esperado_yape": esperado_yape,
        "esperado_tarjeta": esperado_tarjeta,
        "esperado_transferencia": esperado_transferencia,
    })


@role_required("ADMIN", "SUPERVISOR", "CAJA", "VENDEDOR")
def caja_agregar_movimiento(request, fecha):
    """
    Movimiento manual (ingreso / egreso)
    """
    fecha_dt = datetime.strptime(fecha, "%Y-%m-%d").date()
    caja = get_or_create_caja(fecha_dt)

    if request.method == "POST":
        if caja.cerrada:
            return redirect("caja_detalle", fecha=fecha)

        tipo = request.POST.get("tipo")
        medio = request.POST.get("medio_pago")
        categoria = request.POST.get("categoria")
        descripcion = request.POST.get("descripcion", "")
        monto = Decimal(request.POST.get("monto") or "0")

        if monto > 0:
            MovimientoCaja.objects.create(
                caja=caja,
                tipo=tipo,
                medio_pago=medio,
                categoria=categoria,
                descripcion=descripcion,
                monto=monto,
                fuente="MANUAL",
            )

    return redirect("caja_detalle", fecha=fecha)

@role_required("ADMIN", "SUPERVISOR", "CAJA", "VENDEDOR")
def registrar_pago_ticket(request, ticket_id):
    ticket = get_object_or_404(TicketVenta, pk=ticket_id)

    if request.method != "POST":
        return redirect("saldos_pendientes")

    medio_pago = (request.POST.get("medio_pago") or "").strip().upper()
    monto = Decimal(request.POST.get("monto") or "0")

    medios_validos = {"EFECTIVO", "YAPE", "TARJETA", "TRANSFERENCIA"}
    if medio_pago not in medios_validos:
        messages.error(request, "Medio de pago inválido.")
        return redirect("saldos_pendientes")

    if monto <= 0:
        messages.error(request, "El monto debe ser mayor a 0.")
        return redirect("saldos_pendientes")

    saldo_actual = Decimal(ticket.saldo or 0)
    if monto > saldo_actual:
        messages.error(request, f"El monto no puede ser mayor al saldo (S/ {saldo_actual}).")
        return redirect("saldos_pendientes")

    # 1) Crear pago
    PagoTicket.objects.create(ticket=ticket, medio_pago=medio_pago, monto=monto)

    # 2) Recalcular a_cuenta y saldo (sin depender de signals)
    total_pagado = ticket.pagos.aggregate(s=Sum("monto"))["s"] or Decimal("0.00")
    ticket.a_cuenta = total_pagado
    ticket.saldo = Decimal(ticket.total or 0) - total_pagado
    if ticket.saldo < 0:
        ticket.saldo = Decimal("0.00")
    ticket.save(update_fields=["a_cuenta", "saldo"])

    messages.success(request, f"Pago registrado para Ticket #{ticket.numero}.")
    return redirect("saldos_pendientes")

@role_required("ADMIN", "SUPERVISOR", "CAJA" ,"VENDEDOR")
def saldos_pendientes(request):
    q = (request.GET.get("q") or "").strip()

    tickets = TicketVenta.objects.filter(saldo__gt=0).select_related("cliente").order_by("-fecha_emision", "-numero")

    if q:
        # Busca por número de ticket o nombre de cliente
        tickets = tickets.filter(
            Q(numero__icontains=q) |
            Q(cliente__nombre__icontains=q)
        )

    return render(request, "core/saldos_pendientes.html", {
        "tickets": tickets,
        "q": q
    })

@role_required("ADMIN", "SUPERVISOR", "CAJA", "VENDEDOR")
def caja_cerrar(request, fecha):
    fecha_dt = datetime.strptime(fecha, "%Y-%m-%d").date()
    caja = get_or_create_caja(fecha_dt)

    if request.method != "POST":
        return redirect("caja_detalle", fecha=fecha)

    if caja.cerrada:
        return redirect("caja_detalle", fecha=fecha)

    def neto_por_medio(medio):
        ing = caja.movimientos.filter(tipo="IN", medio_pago=medio).aggregate(s=Sum("monto"))["s"] or Decimal("0.00")
        eg = caja.movimientos.filter(tipo="OUT", medio_pago=medio).aggregate(s=Sum("monto"))["s"] or Decimal("0.00")
        return ing - eg

    esperado_ef = neto_por_medio("EFECTIVO") + Decimal(caja.saldo_inicial or 0)
    esperado_ya = neto_por_medio("YAPE")
    esperado_ta = neto_por_medio("TARJETA")
    esperado_tr = neto_por_medio("TRANSFERENCIA")

    arqueo_ef = Decimal(request.POST.get("arqueo_efectivo") or "0")
    arqueo_ya = Decimal(request.POST.get("arqueo_yape") or "0")
    arqueo_ta = Decimal(request.POST.get("arqueo_tarjeta") or "0")
    arqueo_tr = Decimal(request.POST.get("arqueo_transferencia") or "0")

    caja.arqueo_efectivo = arqueo_ef
    caja.arqueo_yape = arqueo_ya
    caja.arqueo_tarjeta = arqueo_ta
    caja.arqueo_transferencia = arqueo_tr

    caja.dif_efectivo = arqueo_ef - esperado_ef
    caja.dif_yape = arqueo_ya - esperado_ya
    caja.dif_tarjeta = arqueo_ta - esperado_ta
    caja.dif_transferencia = arqueo_tr - esperado_tr

    caja.observacion = request.POST.get("observacion", "")

    caja.cerrada = True
    caja.fecha_cierre = timezone.now()
    caja.save()

    messages.success(request, "Caja cerrada con arqueo.")
    return redirect("caja_detalle", fecha=fecha)


def _es_admin(user):
    return user.is_authenticated and (user.is_superuser or user.is_staff)


# reabrir caja
@role_required("ADMIN")
@user_passes_test(_es_admin)
def caja_reabrir(request, fecha):
    fecha_dt = datetime.strptime(fecha, "%Y-%m-%d").date()
    caja = get_or_create_caja(fecha_dt)

    if request.method != "POST":
        return redirect("caja_detalle", fecha=fecha)

    # Reabrir
    caja.cerrada = False
    caja.fecha_cierre = None

    # Opcional: limpiar arqueo/diferencias al reabrir (recomendado)
    caja.arqueo_efectivo = None
    caja.arqueo_yape = None
    caja.arqueo_tarjeta = None
    caja.arqueo_transferencia = None

    caja.dif_efectivo = None
    caja.dif_yape = None
    caja.dif_tarjeta = None
    caja.dif_transferencia = None

    caja.save()
    messages.success(request, "Caja reabierta (solo admin).")
    return redirect("caja_detalle", fecha=fecha)

@login_required
def caja_reporte_pdf(request, fecha):
    fecha_dt = datetime.strptime(fecha, "%Y-%m-%d").date()
    caja = get_or_create_caja(fecha_dt)

    movs = caja.movimientos.all().order_by("fecha_hora")

    # Totales esperados por medio (los mismos que usas en caja_detalle)
    def neto_por_medio(medio):
        ing = caja.movimientos.filter(tipo="IN", medio_pago=medio).aggregate(s=Sum("monto"))["s"] or Decimal("0.00")
        eg  = caja.movimientos.filter(tipo="OUT", medio_pago=medio).aggregate(s=Sum("monto"))["s"] or Decimal("0.00")
        return ing - eg

    esperado_efectivo = neto_por_medio("EFECTIVO") + Decimal(caja.saldo_inicial or 0)  # saldo inicial efectivo
    esperado_yape = neto_por_medio("YAPE")
    esperado_tarjeta = neto_por_medio("TARJETA")
    esperado_transferencia = neto_por_medio("TRANSFERENCIA")

    context = {
        "caja": caja,
        "movs": movs,
        "esperado_efectivo": esperado_efectivo,
        "esperado_yape": esperado_yape,
        "esperado_tarjeta": esperado_tarjeta,
        "esperado_transferencia": esperado_transferencia,
    }

    pdf_bytes = render_to_pdf("core/caja_cierre_ticket80.html", context)
    if not pdf_bytes:
        return HttpResponse("Error generando PDF", status=500)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="cierre_caja_{fecha}.pdf"'
    return response


# Pantalla TV
@role_required("ADMIN", "SUPERVISOR", "CAJA","VENDEDOR","TALLER")
def tv_ordenes(request):
    return render(request, "core/tv_ordenes.html")

@role_required("ADMIN", "SUPERVISOR", "CAJA","VENDEDOR","TALLER")
def tv_ordenes_data(request):
    hoy = timezone.localdate()

    qs = (
        OrdenTrabajo.objects
        .select_related("ticket", "ticket__cliente")
        .order_by("-ticket__numero")
        .filter(
            Q(estado__in=["LAB_PEDIDO","LAB_EN_PROCESO","BISELADO","UV","LISTO"]) |
            Q(estado="ENTREGADO", ts_entregado__date=hoy)
        )
    )

    data = []

    for ot in qs:
        t = ot.ticket

        # Cliente público: Inicial + Apellido
        inicial = ""
        apellido = ""
        if t.cliente_id and getattr(t.cliente, "nombre", None):
            parts = t.cliente.nombre.strip().split()
            if len(parts) >= 1:
                inicial = parts[0][0].upper()
            if len(parts) >= 2:
                apellido = parts[-1].upper()

        cliente_publico = f"{inicial}. {apellido}".strip() if (inicial or apellido) else "CLIENTE"

        due_dt = ot.due_datetime()
        now = timezone.now()

        # ✅ Vencido respecto al tiempo actual (solo para estado no ENTREGADO)
        vencido = bool(due_dt and now > due_dt and ot.estado != "ENTREGADO")

        # ✅ Minutos de atraso: usa el método que congela en LISTO
        min_atraso = ot.minutos_retraso()


        if ot.estado == "ENTREGADO":
            semaforo = "green" if ot.a_tiempo() else "red"
        else:
            if due_dt:
                mins_para_entrega = int((due_dt - now).total_seconds() // 60)
                if mins_para_entrega <= 0:
                    semaforo = "red"
                elif mins_para_entrega <= 30:
                    semaforo = "yellow"
                else:
                    semaforo = "green"
            else:
                semaforo = "green"

        data.append({
            "ticket": t.numero,
            "cliente": cliente_publico,
            "estado": ot.estado_publico(),
            "estado_code": ot.estado,
            "due_str": due_dt.strftime("%d/%m %H:%M") if due_dt else "",
            "vencido": vencido and ot.estado != "ENTREGADO",
            "min_atraso": min_atraso,
            "a_tiempo": (min_atraso == 0),
            "semaforo": semaforo,
        })

    entregados_hoy = OrdenTrabajo.objects.filter(
        estado="ENTREGADO",
        ts_entregado__date=hoy
    )

    total_hoy = entregados_hoy.count()
    ontime_hoy = sum(1 for ot in entregados_hoy if ot.a_tiempo())

    return JsonResponse({
        "items": data,
        "kpi": {
            "entregados_hoy": total_hoy,
            "a_tiempo_hoy": ontime_hoy,
        }
    })



from django.contrib.auth.decorators import login_required

@login_required
@role_required("ADMIN", "SUPERVISOR", "CAJA","VENDEDOR","TALLER")
def actualizar_estado_orden(request, ticket_id):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST requerido"}, status=400)

    ot = OrdenTrabajo.objects.select_related("ticket").get(ticket__id=ticket_id)
    nuevo = (request.POST.get("estado") or "").strip()

    validos = {k for k, _ in OrdenTrabajo.ESTADOS}
    if nuevo not in validos:
        return JsonResponse({"ok": False, "error": "Estado inválido"}, status=400)

    ot.estado = nuevo

    now = timezone.now()
    # setear timestamp del hito
    if nuevo == "LAB_PEDIDO": ot.ts_lab_pedido = ot.ts_lab_pedido or now
    if nuevo == "BISELADO": ot.ts_biselado = ot.ts_biselado or now
    if nuevo == "UV": ot.ts_uv = ot.ts_uv or now
    if nuevo == "LISTO": ot.ts_listo = ot.ts_listo or now
    if nuevo == "ENTREGADO": ot.ts_entregado = ot.ts_entregado or now

    ot.save()
    return JsonResponse({"ok": True})

@login_required
@role_required("ADMIN", "SUPERVISOR", "TALLER", "CAJA","VENDEDOR")
def operador_ordenes(request):
    q = (request.GET.get("q") or "").strip()

    # Activas: todo menos ENTREGADO (o entregados de hoy si quieres verlos)
    qs = OrdenTrabajo.objects.select_related("ticket", "ticket__cliente").order_by("fecha_hora_ultima_actualizacion")

    qs = qs.filter(estado__in=["LAB_PEDIDO","LAB_EN_PROCESO","BISELADO","UV","LISTO"])

    if q:
        qs = qs.filter(
            Q(ticket__numero__icontains=q) |
            Q(ticket__cliente__nombre__icontains=q)
        )

    return render(request, "core/operador_ordenes.html", {
        "ordenes": qs,
        "q": q,
        # Semáforo (minutos): ajusta libremente
        "SLA_OK": 0,
        "SLA_AMARILLO": 10,  # 1..10 min tarde = amarillo
        "SLA_ROJO": 11,      # >=11 min tarde = rojo
    })

@login_required
def operador_cambiar_estado(request, ticket_id):
    if request.method != "POST":
        return redirect("operador_ordenes")

    ot = get_object_or_404(OrdenTrabajo, ticket__id=ticket_id)
    nuevo = (request.POST.get("estado") or "").strip()

    validos = {k for k, _ in OrdenTrabajo.ESTADOS}
    if nuevo not in validos:
        return redirect("operador_ordenes")

    now = timezone.now()
    ot.estado = nuevo

    # setear timestamps por hito (solo si está vacío)
    if nuevo == "LAB_PEDIDO":
        ot.ts_lab_pedido = ot.ts_lab_pedido or now
    elif nuevo == "LAB_EN_PROCESO":
        # opcional: si quieres timestamp adicional, crea campo ts_lab_proceso
        ot.ts_lab_pedido = ot.ts_lab_pedido or now
    elif nuevo == "BISELADO":
        ot.ts_biselado = ot.ts_biselado or now
    elif nuevo == "UV":
        ot.ts_uv = ot.ts_uv or now
    elif nuevo == "LISTO":
        ot.ts_listo = ot.ts_listo or now
    elif nuevo == "ENTREGADO":
        ot.ts_entregado = ot.ts_entregado or now

    ot.save()
    return redirect("operador_ordenes")

