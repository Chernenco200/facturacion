
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from statistics import median

from django.db.models import Sum, Count, F
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone

from accounts.decorators import role_required

from .models import (
    TicketVenta,
    DetalleTicketVenta,
    PagoTicket,
    Producto,
    Gasto,
    TipoLunas,
    OrdenTrabajo,
    MovimientoCaja,
)


# -----------------------
# Helpers de fechas
# -----------------------
@dataclass
class DateRange:
    start: date
    end: date  # inclusive


def _parse_range(request) -> DateRange:
    """
    preset: today | week | month | custom
    custom: start=YYYY-MM-DD&end=YYYY-MM-DD (inclusive)
    """
    preset = (request.GET.get("preset") or "month").lower()
    today = timezone.localdate()

    if preset == "today":
        return DateRange(today, today)

    if preset == "week":
        start = today - timedelta(days=6)
        return DateRange(start, today)

    if preset == "month":
        start = today.replace(day=1)
        return DateRange(start, today)

    # custom
    start_s = request.GET.get("start")
    end_s = request.GET.get("end")
    try:
        start = datetime.strptime(start_s, "%Y-%m-%d").date() if start_s else today.replace(day=1)
        end = datetime.strptime(end_s, "%Y-%m-%d").date() if end_s else today
    except Exception:
        start = today.replace(day=1)
        end = today

    if end < start:
        start, end = end, start
    return DateRange(start, end)


def _daterange_list(dr: DateRange) -> list[date]:
    out = []
    cur = dr.start
    while cur <= dr.end:
        out.append(cur)
        cur += timedelta(days=1)
    return out


def _money(x) -> float:
    if x is None:
        return 0.0
    try:
        return float(x)
    except Exception:
        return 0.0


# -----------------------
# Views
# -----------------------
@role_required("ADMIN", "SUPERVISOR", "VENDEDOR", "CAJA", "TALLER")
def dashboard(request):
    return render(request, "core/dashboard.html")


def dashboard_data(request):
    dr = _parse_range(request)
    days = _daterange_list(dr)
    today = timezone.localdate()

    # -----------------------
    # 1) KPIs: Hoy
    # -----------------------
    ventas_hoy = TicketVenta.objects.filter(fecha_emision=today).aggregate(s=Sum("total"))["s"] or Decimal("0.00")
    tickets_hoy = TicketVenta.objects.filter(fecha_emision=today).count()

    cobros_hoy_qs = (
        PagoTicket.objects.filter(fecha_hora__date=today)
        .values("medio_pago")
        .annotate(s=Sum("monto"))
        .order_by()
    )
    cobros_hoy = {row["medio_pago"]: _money(row["s"]) for row in cobros_hoy_qs}

    saldo_pendiente_hoy = (
        TicketVenta.objects.filter(fecha_emision=today, saldo__gt=0)
        .aggregate(s=Sum("saldo"))["s"]
        or Decimal("0.00")
    )

    # -----------------------
    # 2) KPIs: Mes actual
    # -----------------------
    mes_start = today.replace(day=1)
    ventas_mes = TicketVenta.objects.filter(fecha_emision__range=(mes_start, today)).aggregate(s=Sum("total"))["s"] or Decimal("0.00")
    tickets_mes = TicketVenta.objects.filter(fecha_emision__range=(mes_start, today)).count()
    ticket_promedio_mes = (ventas_mes / tickets_mes) if tickets_mes else Decimal("0.00")

    # -----------------------
    # 3) Ventas por día (línea)
    # -----------------------
    ventas_por_dia_raw = (
        TicketVenta.objects.filter(fecha_emision__range=(dr.start, dr.end))
        .values("fecha_emision")
        .annotate(s=Sum("total"), c=Count("id"))
        .order_by("fecha_emision")
    )
    ventas_map = {r["fecha_emision"]: _money(r["s"]) for r in ventas_por_dia_raw}
    tickets_map = {r["fecha_emision"]: int(r["c"]) for r in ventas_por_dia_raw}

    ventas_por_dia = [
        {"date": d.strftime("%Y-%m-%d"), "ventas": ventas_map.get(d, 0.0), "tickets": tickets_map.get(d, 0)}
        for d in days
    ]

    # -----------------------
    # 4) Ventas por categoría (dona)
    #   - Basado en DetalleTicketVenta.producto.tipo o heurística por descripcion
    # -----------------------
    detalles = (
        DetalleTicketVenta.objects.select_related("ticket_numero", "producto")
        .filter(ticket_numero__fecha_emision__range=(dr.start, dr.end))
    )

    def _categoria(det) -> str:
        # Si hay producto y tipo, mapeamos a categorías del dashboard
        if det.producto and det.producto.tipo:
            t = det.producto.tipo.lower()
            if "monturas" in t:
                return "Monturas"
            if "accesorios" in t:
                return "Accesorios"
            if "lentes de contacto" in t:
                return "Lentes de Contacto"
            if "lectores" in t:
                return "Lectores"
            return "Otros"

        # Heurística por texto
        desc = (det.descripcion or "").lower()
        if "luna" in desc or "miope" in desc or "progres" in desc or "multifocal" in desc or "bifocal" in desc:
            return "Lunas"
        if "montura" in desc or "aro" in desc:
            return "Monturas"
        if "estuche" in desc or "spray" in desc or "paño" in desc or "accesorio" in desc:
            return "Accesorios"
        return "Otros"

    cat_totals = {"Lunas": 0.0, "Monturas": 0.0, "Accesorios": 0.0, "Lentes de Contacto": 0.0, "Lectores": 0.0, "Otros": 0.0}
    for det in detalles:
        cat = _categoria(det)
        cat_totals[cat] = cat_totals.get(cat, 0.0) + float(det.precio) * int(det.cantidad)

    ventas_categoria = [{"categoria": k, "monto": v} for k, v in cat_totals.items() if v > 0]

    # -----------------------
    # 5) Lunas (TipoLunas) - distribución (global)
    #   Nota: TipoLunas NO tiene fecha, por eso en MVP es global.
    # -----------------------
    lunas_enfoque = list(
        TipoLunas.objects.values("enfoque").annotate(c=Count("id")).order_by("-c")[:20]
    )
    lunas_material = list(
        TipoLunas.objects.values("material").annotate(c=Count("id")).order_by("-c")[:20]
    )
    lunas_tratamiento = list(
        TipoLunas.objects.values("tratamiento").annotate(c=Count("id")).order_by("-c")[:20]
    )

    # -----------------------
    # 6) Clientes / cobranzas (top deudores)
    # -----------------------
    top_deudores = list(
        TicketVenta.objects.filter(saldo__gt=0)
        .select_related("cliente")
        .values("cliente__nombre", "cliente__telefono")
        .annotate(saldo=Sum("saldo"))
        .order_by("-saldo")[:10]
    )

    clientes_nuevos_mes = (
        # Cliente.fecha_registro existe, pero está en models.py. Importarlo directo complica si lo tienes en otro archivo.
        # Para MVP lo dejamos en 0 si no está importado. Si quieres, lo activo en 1 minuto.
        0
    )

    # -----------------------
    # 7) Inventario
    # -----------------------
    STOCK_CRITICO = int(request.GET.get("stock_critico") or 5)

    stock_critico = list(
        Producto.objects.filter(activo=True, stock__lte=STOCK_CRITICO)
        .values("cod", "descripcion", "stock", "precio_venta")
        .order_by("stock", "descripcion")[:20]
    )

    top_vendidos = list(
        DetalleTicketVenta.objects.filter(ticket_numero__fecha_emision__range=(dr.start, dr.end), producto__isnull=False)
        .values("producto__cod", "producto__descripcion")
        .annotate(cant=Sum("cantidad"))
        .order_by("-cant")[:10]
    )

    # Productos "inmovilizados": vendidos 0 veces en el rango (aprox. MVP)
    vendidos_ids = set(
        DetalleTicketVenta.objects.filter(ticket_numero__fecha_emision__range=(dr.start, dr.end), producto__isnull=False)
        .values_list("producto_id", flat=True)
        .distinct()
    )
    inmovilizados = list(
        Producto.objects.filter(activo=True).exclude(id__in=vendidos_ids)
        .values("cod", "descripcion", "stock")[:15]
    )

    # -----------------------
    # 8) Caja (ingresos/egresos por día + flujo)
    # -----------------------
    # Usamos MovimientoCaja (tiene fecha_hora)
    mov = MovimientoCaja.objects.filter(fecha_hora__date__range=(dr.start, dr.end))
    mov_por_dia = (
        mov.annotate(d=TruncDate("fecha_hora"))
        .values("d", "tipo")
        .annotate(s=Sum("monto"))
        .order_by("d")
    )
    ingresos_map, egresos_map = {}, {}
    for r in mov_por_dia:
        d = r["d"]
        if r["tipo"] == "IN":
            ingresos_map[d] = _money(r["s"])
        else:
            egresos_map[d] = _money(r["s"])

    caja_por_dia = []
    for d in days:
        ing = ingresos_map.get(d, 0.0)
        egr = egresos_map.get(d, 0.0)
        caja_por_dia.append({"date": d.strftime("%Y-%m-%d"), "ingresos": ing, "egresos": egr, "flujo": ing - egr})

    gastos_rango = Gasto.objects.filter(fecha__range=(dr.start, dr.end)).aggregate(s=Sum("monto"))["s"] or Decimal("0.00")

    # -----------------------
    # 9) Taller / Biselado
    #   Tiempo en biselado: ts_biselado -> (ts_uv or ts_listo or ts_entregado or now)
    # -----------------------
    now = timezone.now()
    ot_biselado = OrdenTrabajo.objects.select_related("ticket", "ticket__cliente").filter(ts_biselado__isnull=False)

    # (opcional) limitamos por rango usando ts_biselado
    ot_biselado = ot_biselado.filter(ts_biselado__date__range=(dr.start, dr.end))

    biselado_minutos = []
    biselado_rows = []
    biselado_por_dia_map = {}

    for ot in ot_biselado:
        start = ot.ts_biselado
        end = ot.ts_uv or ot.ts_listo or ot.ts_entregado or now
        mins = int((end - start).total_seconds() // 60)
        if mins < 0:
            continue

        biselado_minutos.append(mins)

        d = start.date()
        biselado_por_dia_map.setdefault(d, []).append(mins)

        biselado_rows.append({
            "ticket": getattr(ot.ticket, "numero", ""),
            "cliente": (ot.ticket.cliente.nombre if ot.ticket and ot.ticket.cliente else ""),
            "estado": ot.estado,
            "inicio": start.strftime("%d/%m/%Y %H:%M"),
            "fin": end.strftime("%d/%m/%Y %H:%M"),
            "minutos": mins,
        })

    biselado_avg = (sum(biselado_minutos) / len(biselado_minutos)) if biselado_minutos else 0.0
    biselado_med = float(median(biselado_minutos)) if biselado_minutos else 0.0

    # Serie biselado por día: promedio diario
    biselado_serie = []
    for d in days:
        arr = biselado_por_dia_map.get(d, [])
        biselado_serie.append({
            "date": d.strftime("%Y-%m-%d"),
            "avg_min": (sum(arr) / len(arr)) if arr else 0.0
        })

    # Órdenes actualmente en biselado
    en_biselado = OrdenTrabajo.objects.select_related("ticket", "ticket__cliente").filter(
        estado="BISELADO",
        ts_biselado__isnull=False
    ).order_by("-ts_biselado")[:20]

    en_biselado_rows = []
    for ot in en_biselado:
        mins = int((now - ot.ts_biselado).total_seconds() // 60) if ot.ts_biselado else 0
        en_biselado_rows.append({
            "ticket": getattr(ot.ticket, "numero", ""),
            "cliente": (ot.ticket.cliente.nombre if ot.ticket and ot.ticket.cliente else ""),
            "inicio": ot.ts_biselado.strftime("%d/%m/%Y %H:%M") if ot.ts_biselado else "",
            "minutos": mins,
        })

    # Top 5 más lentas (en rango)
    biselado_top_lentas = sorted(biselado_rows, key=lambda x: x["minutos"], reverse=True)[:5]

    # -----------------------
    # 10) Destiempo vs LISTO (SLA)
    #   Regla: ts_listo > due_datetime() => tarde
    #   (usamos la lógica ya implementada en OrdenTrabajo.minutos_retraso())
    # -----------------------
    ot_listos = OrdenTrabajo.objects.select_related("ticket", "ticket__cliente").filter(
        ts_listo__isnull=False
    )

    # rango por fecha en que quedó listo
    ot_listos = ot_listos.filter(ts_listo__date__range=(dr.start, dr.end))

    a_tiempo = 0
    tarde = 0
    retrasos = []
    tardios_rows = []

    for ot in ot_listos:
        due = ot.due_datetime()
        if not due:
            continue

        # minutos_retraso() ya congela en LISTO si estado="LISTO"
        # PERO por seguridad, medimos directo contra ts_listo:
        fin = ot.ts_listo
        mins = int((fin - due).total_seconds() // 60)
        mins = mins if mins > 0 else 0

        if mins == 0:
            a_tiempo += 1
        else:
            tarde += 1
            retrasos.append(mins)
            tardios_rows.append({
                "ticket": getattr(ot.ticket, "numero", ""),
                "cliente": (ot.ticket.cliente.nombre if ot.ticket and ot.ticket.cliente else ""),
                "prometido": due.strftime("%d/%m/%Y %H:%M"),
                "listo": fin.strftime("%d/%m/%Y %H:%M"),
                "minutos_tarde": mins
            })

    retraso_prom = (sum(retrasos) / len(retrasos)) if retrasos else 0.0
    top_tardios = sorted(tardios_rows, key=lambda x: x["minutos_tarde"], reverse=True)[:10]

    # -----------------------
    # Respuesta JSON
    # -----------------------
    payload = {
        "range": {"start": dr.start.strftime("%Y-%m-%d"), "end": dr.end.strftime("%Y-%m-%d")},

        "kpis": {
            "hoy": {
                "ventas": _money(ventas_hoy),
                "tickets": tickets_hoy,
                "cobros": cobros_hoy,
                "saldo_pendiente": _money(saldo_pendiente_hoy),
            },
            "mes": {
                "ventas": _money(ventas_mes),
                "tickets": tickets_mes,
                "ticket_promedio": _money(ticket_promedio_mes),
            },
        },

        "ventas_por_dia": ventas_por_dia,
        "ventas_categoria": ventas_categoria,

        "lunas": {
            "enfoque": lunas_enfoque,
            "material": lunas_material,
            "tratamiento": lunas_tratamiento,
            "nota": "TipoLunas no tiene fecha; distribución global. Si quieres por mes, agregamos fecha_registro a TipoLunas."
        },

        "cobranzas": {
            "top_deudores": top_deudores,
            "clientes_nuevos_mes": clientes_nuevos_mes,
        },

        "inventario": {
            "stock_critico_umbral": STOCK_CRITICO,
            "stock_critico": stock_critico,
            "top_vendidos": top_vendidos,
            "inmovilizados": inmovilizados,
        },

        "caja": {
            "serie": caja_por_dia,
            "gastos_rango": _money(gastos_rango),
        },

        "taller": {
            "biselado": {
                "avg_min": biselado_avg,
                "median_min": biselado_med,
                "top_lentas": biselado_top_lentas,
                "en_biselado": en_biselado_rows,
                "serie": biselado_serie,
            }
        },

        "sla_listo": {
            "a_tiempo": a_tiempo,
            "tarde": tarde,
            "retraso_prom_min": retraso_prom,
            "top_tardios": top_tardios,
        },
    }

    return JsonResponse(payload)
