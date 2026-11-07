"""
Pantallas de la toma de inventario de monturas con lectora.

Permisos:
    Escanear .......................... ADMIN, SUPERVISOR, VENDEDOR, CAJA
    Abrir, cerrar, recontar, aprobar .. ADMIN, SUPERVISOR
    Anular un ajuste aprobado ......... ADMIN
"""

import json
from io import BytesIO

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import role_required

from . import inventario as inv
from .models import (
    AjusteInventario,
    DetalleAjusteInventario,
    Producto,
    TomaInventario,
)

ESCANEAN = ("ADMIN", "SUPERVISOR", "VENDEDOR", "CAJA")
GESTIONAN = ("ADMIN", "SUPERVISOR")


def _error(request, exc):
    texto = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
    messages.error(request, texto)


def _rol(request):
    return getattr(getattr(request.user, "profile", None), "rol", None)


# ============================================================
# LISTA / HISTORIAL MENSUAL
# ============================================================

@role_required(*ESCANEAN)
def tomas_lista(request):
    tomas = (
        TomaInventario.objects
        .select_related("creada_por", "cerrada_por")
        .annotate(n_lecturas=Count("lecturas", filter=Q(lecturas__anulada=False)))
        [:36]
    )
    filas = []
    for t in tomas:
        res = inv.resumen(list(t.detalles.all())) if t.estado in (
            TomaInventario.Estado.CERRADA, TomaInventario.Estado.AJUSTADA
        ) else None
        filas.append({"toma": t, "res": res})
    return render(request, "core/inventario/tomas_lista.html", {
        "filas": filas,
        "activa": inv.toma_activa(),
        "puede_gestionar": _rol(request) in GESTIONAN,
        "puede_ser_inicial": inv.puede_ser_inicial(),
    })


@require_POST
@role_required(*GESTIONAN)
def toma_nueva(request):
    try:
        toma = inv.abrir_toma(
            request.user,
            request.POST.get("observacion", ""),
            es_inicial=request.POST.get("es_inicial") == "1",
        )
    except ValidationError as e:
        _error(request, e)
        return redirect("tomas_lista")
    messages.success(request, f"Toma #{toma.pk} abierta. Ya pueden escanear.")
    return redirect("toma_escanear", toma_id=toma.pk)


@require_POST
@role_required(*GESTIONAN)
def toma_anular(request, toma_id):
    toma = get_object_or_404(TomaInventario, pk=toma_id)
    try:
        inv.anular_toma(toma)
        messages.success(request, f"Toma #{toma.pk} anulada.")
    except ValidationError as e:
        _error(request, e)
    return redirect("tomas_lista")


# ============================================================
# ESCANEO
# ============================================================

@role_required(*ESCANEAN)
def toma_escanear(request, toma_id):
    toma = get_object_or_404(TomaInventario, pk=toma_id)
    if toma.estado != TomaInventario.Estado.EN_CONTEO:
        messages.info(request, "Esta toma ya no está en conteo.")
        return redirect("toma_reporte", toma_id=toma.pk)
    ultimas = toma.lecturas.select_related("producto", "usuario")[:15]
    return render(request, "core/inventario/escanear.html", {
        "toma": toma,
        "ultimas": ultimas,
        "total": toma.lecturas.filter(anulada=False).count(),
        "puede_gestionar": _rol(request) in GESTIONAN,
    })


def _producto_json(producto):
    if not producto:
        return None
    foto = ""
    try:
        if producto.imagenF:
            foto = producto.imagenF.url
    except Exception:
        foto = ""
    return {
        "id": producto.pk,
        "cod": producto.cod,
        "descripcion": producto.descripcion or "",
        "marca": producto.get_marca_display() if producto.marca else "",
        "tipo": producto.tipo or "",
        "color": producto.color or "",
        "precio": str(producto.precio_venta or ""),
        "foto": foto,
    }


@require_POST
@role_required(*ESCANEAN)
def api_toma_lectura(request, toma_id):
    toma = get_object_or_404(TomaInventario, pk=toma_id)
    try:
        datos = json.loads(request.body or "{}")
    except ValueError:
        datos = request.POST
    try:
        lectura, producto, error = inv.registrar_lectura(
            toma, datos.get("codigo"), request.user, datos.get("zona", ""),
        )
    except ValidationError as e:
        return JsonResponse({"ok": False, "nivel": "error", "mensaje": e.messages[0]}, status=400)

    respuesta = {
        "ok": lectura is not None and producto is not None,
        "guardada": lectura is not None,
        "nivel": "ok" if (lectura and producto) else ("aviso" if lectura else "error"),
        "mensaje": error or "",
        "producto": _producto_json(producto),
        "contado_producto": inv.contado_de(toma, producto) if (lectura and producto) else 0,
        "total": toma.lecturas.filter(anulada=False).count(),
        "codigo": (datos.get("codigo") or "").strip(),
        "hora": timezone.localtime().strftime("%H:%M:%S"),
    }
    return JsonResponse(respuesta)


@require_POST
@role_required(*ESCANEAN)
def api_toma_deshacer(request, toma_id):
    toma = get_object_or_404(TomaInventario, pk=toma_id)
    try:
        lectura = inv.deshacer_ultima_lectura(toma, request.user)
    except ValidationError as e:
        return JsonResponse({"ok": False, "mensaje": e.messages[0]}, status=400)
    return JsonResponse({
        "ok": True,
        "mensaje": f"Se deshizo la lectura de {lectura.codigo_leido}.",
        "total": toma.lecturas.filter(anulada=False).count(),
    })


# ============================================================
# AVANCE EN VIVO, RECONTEO Y CIERRE
# ============================================================

@role_required(*GESTIONAN)
def toma_avance(request, toma_id):
    toma = get_object_or_404(TomaInventario, pk=toma_id)
    if toma.estado != TomaInventario.Estado.EN_CONTEO:
        return redirect("toma_reporte", toma_id=toma.pk)
    filas = inv.calcular_diferencias(toma)
    return render(request, "core/inventario/avance.html", {
        "toma": toma,
        "faltantes": [f for f in filas if f["diferencia"] < 0],
        "sobrantes": [f for f in filas if f["diferencia"] > 0],
        "res": inv.resumen(filas),
        "no_reconocidos": inv.no_reconocidos(toma),
        "compras": inv.compras_durante_conteo(toma),
    })


@require_POST
@role_required(*GESTIONAN)
def toma_recontar(request, toma_id, producto_id):
    toma = get_object_or_404(TomaInventario, pk=toma_id)
    producto = get_object_or_404(Producto, pk=producto_id)
    try:
        n = inv.recontar_producto(toma, producto)
        messages.success(
            request, f"{producto.cod}: {n} lectura(s) anuladas. Vuelve a escanearlo."
        )
    except ValidationError as e:
        _error(request, e)
    return redirect("toma_avance", toma_id=toma.pk)


@require_POST
@role_required(*GESTIONAN)
def toma_cerrar(request, toma_id):
    toma = get_object_or_404(TomaInventario, pk=toma_id)
    try:
        inv.cerrar_toma(toma, request.user)
        messages.success(request, "Conteo cerrado. Revisa las diferencias y aprueba el ajuste.")
    except ValidationError as e:
        _error(request, e)
        return redirect("toma_avance", toma_id=toma.pk)
    return redirect("toma_reporte", toma_id=toma.pk)


@require_POST
@role_required(*GESTIONAN)
def toma_reabrir(request, toma_id):
    toma = get_object_or_404(TomaInventario, pk=toma_id)
    try:
        inv.reabrir_toma(toma)
        messages.success(request, "Conteo reabierto: puedes seguir escaneando.")
    except ValidationError as e:
        _error(request, e)
        return redirect("toma_reporte", toma_id=toma.pk)
    return redirect("toma_escanear", toma_id=toma.pk)


# ============================================================
# REPORTE DE FALTANTES / SOBRANTES Y AJUSTE
# ============================================================

@role_required(*GESTIONAN)
def toma_reporte(request, toma_id):
    toma = get_object_or_404(
        TomaInventario.objects.select_related("creada_por", "cerrada_por"), pk=toma_id
    )
    if toma.estado == TomaInventario.Estado.EN_CONTEO:
        return redirect("toma_avance", toma_id=toma.pk)

    detalles = list(toma.detalles.select_related("producto"))
    ajuste = toma.ajustes.filter(estado=AjusteInventario.Estado.APROBADO).first()
    motivos_ajuste = {}
    if ajuste:
        motivos_ajuste = {
            d.producto_id: d.get_motivo_display() for d in ajuste.detalles.all()
        }
    return render(request, "core/inventario/reporte.html", {
        "toma": toma,
        "faltantes": [d for d in detalles if d.diferencia < 0],
        "sobrantes": [d for d in detalles if d.diferencia > 0],
        "coinciden": [d for d in detalles if d.diferencia == 0],
        "res": inv.resumen(detalles),
        "no_reconocidos": inv.no_reconocidos(toma),
        "ajuste": ajuste,
        "asiento": inv.asiento_de(ajuste) if ajuste else None,
        "motivos_ajuste": motivos_ajuste,
        "motivos": DetalleAjusteInventario.Motivo.choices,
        "es_admin": _rol(request) == "ADMIN",
        "editable": toma.estado == TomaInventario.Estado.CERRADA,
        "fecha_inicial": inv.inicio_de_mes(toma.fecha_inicio) if toma.es_inicial else None,
    })


@require_POST
@role_required(*GESTIONAN)
def toma_aprobar_ajuste(request, toma_id):
    toma = get_object_or_404(TomaInventario, pk=toma_id)
    motivos = {}
    for clave, valor in request.POST.items():
        if clave.startswith("motivo_"):
            try:
                motivos[int(clave[7:])] = valor
            except ValueError:
                pass
    try:
        ajuste = inv.aprobar_ajuste(
            toma, request.user, motivos, request.POST.get("observacion", "")
        )
    except ValidationError as e:
        _error(request, e)
        return redirect("toma_reporte", toma_id=toma.pk)

    if ajuste is None:
        messages.success(request, "No había diferencias: la toma quedó ajustada.")
    else:
        avisos = ajuste.detalles.filter(motivo__in=inv.MOTIVOS_QUE_NO_SON_AJUSTE).count()
        messages.success(request, f"Ajuste #{ajuste.pk} aprobado: stock, kardex y asiento actualizados.")
        if avisos:
            messages.warning(
                request,
                f"{avisos} línea(s) marcadas como venta/compra no registrada. "
                "Lo ideal es registrar ese documento y anular este ajuste para "
                "rehacerlo, así la venta o la compra quedan en su lugar.",
            )
    return redirect("toma_reporte", toma_id=toma.pk)


@require_POST
@role_required("ADMIN")
def ajuste_anular(request, ajuste_id):
    ajuste = get_object_or_404(AjusteInventario, pk=ajuste_id)
    try:
        inv.anular_ajuste(ajuste, request.user)
        messages.success(
            request, f"Ajuste #{ajuste.pk} anulado. El stock y el kardex volvieron atrás."
        )
    except ValidationError as e:
        _error(request, e)
    if ajuste.toma_id:
        return redirect("toma_reporte", toma_id=ajuste.toma_id)
    return redirect("tomas_lista")


@role_required(*GESTIONAN)
def toma_exportar_excel(request, toma_id):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    toma = get_object_or_404(TomaInventario, pk=toma_id)
    detalles = list(toma.detalles.select_related("producto"))
    wb = Workbook()
    cab = ["Código", "Descripción", "Marca", "Tipo", "Stock sistema", "Contado",
           "Vendido tras escanear", "Diferencia", "Costo unit.", "Valor a costo",
           "Precio venta", "Valor a venta"]
    grupos = [
        ("Faltantes", [d for d in detalles if d.diferencia < 0]),
        ("Sobrantes", [d for d in detalles if d.diferencia > 0]),
        ("Coinciden", [d for d in detalles if d.diferencia == 0]),
    ]
    fuente = Font(name="Arial")
    negrita = Font(name="Arial", bold=True, color="FFFFFF")
    relleno = PatternFill("solid", fgColor="1F6FB8")
    for i, (nombre, filas) in enumerate(grupos):
        ws = wb.active if i == 0 else wb.create_sheet()
        ws.title = nombre
        ws.append([f"Toma #{toma.pk} - {nombre}"])
        ws["A1"].font = Font(name="Arial", bold=True, size=12)
        ws.append(cab)
        for c in ws[2]:
            c.font, c.fill = negrita, relleno
            c.alignment = Alignment(horizontal="center", wrap_text=True)
        for d in filas:
            p = d.producto
            ws.append([
                p.cod, p.descripcion or "", p.get_marca_display() if p.marca else "",
                p.tipo or "", d.stock_sistema, d.contado, d.vendido_tras_lectura,
                d.diferencia, float(d.costo_unitario), float(d.valor_costo),
                float(d.precio_venta or 0), float(d.valor_venta),
            ])
        for fila in ws.iter_rows(min_row=3):
            for c in fila:
                c.font = fuente
            for c in (fila[8], fila[9], fila[10], fila[11]):
                c.number_format = "#,##0.00"
        for col, ancho in zip("ABCDEFGHIJKL", [12, 34, 16, 20, 10, 9, 11, 10, 11, 12, 11, 12]):
            ws.column_dimensions[col].width = ancho
        ws.freeze_panes = "A3"

    ws = wb.create_sheet("No reconocidos")
    ws.append(["Código leído", "Veces"])
    for r in inv.no_reconocidos(toma):
        ws.append([r["codigo_leido"], r["veces"]])

    buffer = BytesIO()
    wb.save(buffer)
    resp = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="toma_inventario_{toma.pk}.xlsx"'
    return resp


@role_required(*GESTIONAN)
def faltantes_recurrentes(request):
    try:
        minimo = max(2, int(request.GET.get("minimo", 2)))
    except ValueError:
        minimo = 2
    return render(request, "core/inventario/faltantes_recurrentes.html", {
        "filas": inv.faltantes_recurrentes(minimo),
        "minimo": minimo,
    })
