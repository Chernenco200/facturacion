"""
Toma de inventario de monturas con lectora y ajuste mensual.

Flujo:
    1. abrir_toma()                -> estado EN_CONTEO
    2. registrar_lectura()         -> una fila por escaneo
    3. calcular_diferencias()      -> avance en vivo (sin guardar)
    4. cerrar_toma()               -> congela el reporte (CERRADA)
    5. aprobar_ajuste()            -> ajuste + kardex + asiento (AJUSTADA)

Conteo con la tienda abierta
----------------------------
El stock del sistema se toma al momento del cierre. Una montura
escaneada y vendida después sigue sumando en el conteo, pero ya no
está en el stock del sistema; por eso se descuentan las ventas
registradas DESPUÉS de la primera lectura de cada producto. Las
ventas hechas antes de escanear no necesitan corrección: la montura
ni se contó ni está en el sistema.
"""

from collections import defaultdict
from datetime import datetime, time
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Min, OuterRef, Subquery
from django.utils import timezone

from .kardex import _ticket_dt, recalcular_kardex_producto
from .models import (
    TIPOS_MONTURA,
    AjusteInventario,
    Compra,
    DetalleAjusteInventario,
    DetalleTicketVenta,
    DetalleTomaInventario,
    KardexMovimiento,
    LecturaInventario,
    Producto,
    TomaInventario,
)

CENTIMO = Decimal("0.01")

# Cuentas del asiento de ajuste.
CUENTA_MERCADERIAS_MONTURAS = "20101"
CUENTA_FALTANTES = "65901"
CUENTA_SOBRANTES = "75901"
CUENTA_CAPITAL = "50101"
ORIGEN_ASIENTO = "AJUSTE_INVENTARIO"

MOTIVOS_QUE_NO_SON_AJUSTE = {
    DetalleAjusteInventario.Motivo.VENTA_NO_REGISTRADA,
    DetalleAjusteInventario.Motivo.COMPRA_NO_REGISTRADA,
}


def es_montura(producto):
    return (producto.tipo or "") in TIPOS_MONTURA


def toma_activa():
    return TomaInventario.objects.filter(
        estado=TomaInventario.Estado.EN_CONTEO
    ).first()


# ============================================================
# 1. ABRIR / ANULAR
# ============================================================

def puede_ser_inicial():
    """La toma inicial solo tiene sentido antes del primer ajuste."""
    return not AjusteInventario.objects.filter(
        estado=AjusteInventario.Estado.APROBADO
    ).exists()


def inicio_de_mes(momento):
    local = timezone.localtime(momento)
    return timezone.make_aware(
        datetime.combine(local.date().replace(day=1), time(0, 0))
    )


def abrir_toma(usuario, observacion="", es_inicial=False):
    if toma_activa():
        raise ValidationError("Ya hay una toma de inventario en conteo.")
    if es_inicial and not puede_ser_inicial():
        raise ValidationError(
            "Ya existe un ajuste de inventario aprobado: la toma inicial "
            "solo se hace una vez, antes de cualquier ajuste."
        )
    try:
        with transaction.atomic():
            return TomaInventario.objects.create(
                creada_por=usuario, observacion=(observacion or "")[:255],
                es_inicial=bool(es_inicial),
            )
    except IntegrityError:
        raise ValidationError("Ya hay una toma de inventario en conteo.")


def anular_toma(toma):
    if toma.estado not in (
        TomaInventario.Estado.EN_CONTEO, TomaInventario.Estado.CERRADA,
    ):
        raise ValidationError("Solo se anula una toma en conteo o cerrada sin ajustar.")
    toma.estado = TomaInventario.Estado.ANULADA
    toma.save(update_fields=["estado"])


# ============================================================
# 2. LECTURAS
# ============================================================

def registrar_lectura(toma, codigo, usuario=None, zona=""):
    """
    Devuelve (lectura, producto, mensaje_error).
    - Código inexistente: se guarda la lectura sin producto
      (sale en el reporte de códigos no reconocidos).
    - Producto que no es montura: no se guarda.
    """
    if toma.estado != TomaInventario.Estado.EN_CONTEO:
        raise ValidationError("La toma ya no está en conteo.")

    codigo = (codigo or "").strip()
    if not codigo:
        raise ValidationError("Código vacío.")

    producto = Producto.objects.filter(cod__iexact=codigo).first()

    if producto and not es_montura(producto):
        return None, producto, (
            f"{producto.cod} es «{producto.tipo or 'sin tipo'}», "
            "no es montura: no se cuenta."
        )

    lectura = LecturaInventario.objects.create(
        toma=toma,
        producto=producto,
        codigo_leido=codigo[:50],
        zona=(zona or "").strip()[:40],
        usuario=usuario if getattr(usuario, "is_authenticated", False) else None,
    )
    error = None if producto else f"El código {codigo} no existe en el sistema."
    return lectura, producto, error


def deshacer_ultima_lectura(toma, usuario):
    if toma.estado != TomaInventario.Estado.EN_CONTEO:
        raise ValidationError("La toma ya no está en conteo.")
    lectura = (
        toma.lecturas.filter(anulada=False, usuario=usuario)
        .order_by("-fecha_hora", "-id").first()
    )
    if not lectura:
        raise ValidationError("No tienes lecturas para deshacer.")
    lectura.anulada = True
    lectura.save(update_fields=["anulada"])
    return lectura


def recontar_producto(toma, producto):
    """Anula las lecturas de un producto para volver a escanearlo."""
    if toma.estado != TomaInventario.Estado.EN_CONTEO:
        raise ValidationError("La toma ya no está en conteo.")
    return toma.lecturas.filter(producto=producto, anulada=False).update(anulada=True)


def contado_de(toma, producto):
    return toma.lecturas.filter(producto=producto, anulada=False).count()


# ============================================================
# 3. CÁLCULO DE DIFERENCIAS
# ============================================================

def _stock_y_costo_al(momento, productos_qs):
    """
    Stock y costo promedio de cada producto en un instante dado,
    tomados del último movimiento del kardex hasta ese momento.
    """
    ultimo = (
        KardexMovimiento.objects
        .filter(producto=OuterRef("pk"), fecha__lte=momento)
        .order_by("-fecha", "-id")
    )
    filas = productos_qs.annotate(
        k_stock=Subquery(ultimo.values("stock_actual")[:1]),
        k_costo=Subquery(ultimo.values("costo_promedio")[:1]),
    ).values("id", "k_stock", "k_costo")
    return {
        f["id"]: (
            int(f["k_stock"] or 0),
            Decimal(str(f["k_costo"] or 0)),
        )
        for f in filas
    }


def _ventas_tras_lectura(toma, primeras, hasta):
    """Unidades vendidas de cada producto después de su primera lectura."""
    if not primeras:
        return {}
    vendidas = defaultdict(int)
    detalles = (
        DetalleTicketVenta.objects
        .filter(
            producto_id__in=list(primeras),
            ticket_numero__fecha_emision__gte=timezone.localtime(
                toma.fecha_inicio
            ).date(),
        )
        .select_related("ticket_numero")
    )
    for d in detalles:
        momento = _ticket_dt(d.ticket_numero)
        if primeras[d.producto_id] < momento <= hasta:
            vendidas[d.producto_id] += int(d.cantidad or 0)
    return vendidas


def calcular_diferencias(toma, hasta=None):
    """
    Lista de dicts (uno por producto con stock o con lecturas).
    No guarda nada: sirve para el avance en vivo y para el cierre.
    """
    hasta = hasta or timezone.now()

    lecturas = (
        toma.lecturas.filter(anulada=False, producto__isnull=False)
        .values("producto_id")
        .annotate(n=Count("id"), primera=Min("fecha_hora"))
    )
    contados = {l["producto_id"]: l["n"] for l in lecturas}
    primeras = {l["producto_id"]: l["primera"] for l in lecturas}

    monturas = Producto.objects.filter(tipo__in=TIPOS_MONTURA)
    stock_costo = _stock_y_costo_al(hasta, monturas)
    vendidas = _ventas_tras_lectura(toma, primeras, hasta)

    ids = {pid for pid, (s, _) in stock_costo.items() if s != 0} | set(contados)
    productos = Producto.objects.in_bulk(ids)

    filas = []
    for pid in ids:
        producto = productos[pid]
        stock, costo = stock_costo.get(pid, (0, Decimal("0")))
        if costo <= 0:
            costo = Decimal(str(producto.costo_promedio or producto.precio_compra or 0))
        contado = contados.get(pid, 0)
        vendido = min(vendidas.get(pid, 0), contado)
        diferencia = (contado - vendido) - stock
        filas.append({
            "producto": producto,
            "stock_sistema": stock,
            "contado": contado,
            "vendido_tras_lectura": vendido,
            "diferencia": diferencia,
            "costo_unitario": costo,
            "precio_venta": producto.precio_venta or Decimal("0"),
            "primera_lectura": primeras.get(pid),
            "valor_costo": (Decimal(diferencia) * costo).quantize(CENTIMO),
        })
    filas.sort(key=lambda f: (f["producto"].cod or ""))
    return filas


def no_reconocidos(toma):
    return list(
        toma.lecturas.filter(anulada=False, producto__isnull=True)
        .values("codigo_leido")
        .annotate(veces=Count("id"), primera=Min("fecha_hora"))
        .order_by("codigo_leido")
    )


def compras_durante_conteo(toma, hasta=None):
    """Compras de monturas fechadas desde el inicio del conteo."""
    hasta = hasta or timezone.now()
    return (
        Compra.objects.filter(
            fecha__gte=timezone.localtime(toma.fecha_inicio).date(),
            fecha__lte=timezone.localtime(hasta).date(),
            detalles__producto__tipo__in=TIPOS_MONTURA,
        )
        .exclude(tipo_comprobante="NC")
        .distinct()
    )


def resumen(filas):
    r = {
        "faltantes": 0, "sobrantes": 0, "coinciden": 0, "lineas": len(filas),
        "unid_faltantes": 0, "unid_sobrantes": 0,
        "valor_faltante": Decimal("0"), "valor_sobrante": Decimal("0"),
        "venta_faltante": Decimal("0"),
    }
    for f in filas:
        get = (lambda k: getattr(f, k)) if not isinstance(f, dict) else f.get
        dif = get("diferencia")
        valor = (Decimal(abs(dif)) * get("costo_unitario")).quantize(CENTIMO)
        if dif < 0:
            r["faltantes"] += 1
            r["unid_faltantes"] += -dif
            r["valor_faltante"] += valor
            r["venta_faltante"] += Decimal(-dif) * (get("precio_venta") or 0)
        elif dif > 0:
            r["sobrantes"] += 1
            r["unid_sobrantes"] += dif
            r["valor_sobrante"] += valor
        else:
            r["coinciden"] += 1
    r["exactitud"] = (
        round(r["coinciden"] * 100 / r["lineas"], 1) if r["lineas"] else 100.0
    )
    return r


# ============================================================
# 4. CIERRE DEL CONTEO
# ============================================================

def _sincronizar_kardex_desfasado():
    """
    Recalcula el kardex de las monturas cuyo stock no coincide
    con su último movimiento (nunca recalculadas o editadas a mano),
    para comparar el conteo contra el stock real de los documentos.
    """
    ultimo = (
        KardexMovimiento.objects
        .filter(producto=OuterRef("pk"))
        .order_by("-fecha", "-id")
    )
    filas = (
        Producto.objects.filter(tipo__in=TIPOS_MONTURA)
        .annotate(k_stock=Subquery(ultimo.values("stock_actual")[:1]))
        .values("id", "stock", "k_stock")
    )
    ids = [
        f["id"] for f in filas
        if int(f["stock"] or 0) != int(f["k_stock"] or 0)
    ]
    total = 0
    for producto in Producto.objects.filter(id__in=ids):
        recalcular_kardex_producto(producto)
        total += 1
    return total


@transaction.atomic
def cerrar_toma(toma, usuario):
    toma = TomaInventario.objects.select_for_update().get(pk=toma.pk)
    if toma.estado != TomaInventario.Estado.EN_CONTEO:
        raise ValidationError("La toma no está en conteo.")
    if not toma.lecturas.filter(anulada=False).exists():
        raise ValidationError("No hay lecturas: escanea las monturas antes de cerrar.")

    _sincronizar_kardex_desfasado()

    ahora = timezone.now()
    filas = calcular_diferencias(toma, hasta=ahora)
    DetalleTomaInventario.objects.bulk_create([
        DetalleTomaInventario(
            toma=toma,
            producto=f["producto"],
            stock_sistema=f["stock_sistema"],
            contado=f["contado"],
            vendido_tras_lectura=f["vendido_tras_lectura"],
            diferencia=f["diferencia"],
            costo_unitario=f["costo_unitario"],
            precio_venta=f["precio_venta"],
            primera_lectura=f["primera_lectura"],
        )
        for f in filas
    ])
    toma.fecha_cierre = ahora
    toma.cerrada_por = usuario
    toma.estado = TomaInventario.Estado.CERRADA
    toma.save(update_fields=["fecha_cierre", "cerrada_por", "estado"])
    return toma


@transaction.atomic
def reabrir_toma(toma):
    toma = TomaInventario.objects.select_for_update().get(pk=toma.pk)
    if toma.estado != TomaInventario.Estado.CERRADA:
        raise ValidationError("Solo se reabre una toma cerrada y sin ajustar.")
    if toma_activa():
        raise ValidationError("Ya hay otra toma en conteo.")
    toma.detalles.all().delete()
    toma.estado = TomaInventario.Estado.EN_CONTEO
    toma.fecha_cierre = None
    toma.cerrada_por = None
    toma.save(update_fields=["estado", "fecha_cierre", "cerrada_por"])
    return toma


# ============================================================
# 5. AJUSTE + KARDEX + ASIENTO
# ============================================================

def _crear_asiento_ajuste(ajuste):
    """
    Toma mensual:
        Faltantes:  65901 Faltantes de inventario  /  20101 Monturas
        Sobrantes:  20101 Monturas                 /  75901 Sobrantes de inventario
    Toma inicial (apertura), al día 1 del mes:
        Sobrantes:  20101 Monturas                 /  50101 Capital aportado
        Faltantes:  50101 Capital aportado         /  20101 Monturas
    """
    inicial = bool(ajuste.toma_id and ajuste.toma.es_inicial)
    cta_gasto = CUENTA_CAPITAL if inicial else CUENTA_FALTANTES
    cta_ingreso = CUENTA_CAPITAL if inicial else CUENTA_SOBRANTES
    from contabilidad.models import (
        AsientoContable, CuentaContable, DetalleAsiento, PeriodoContable,
    )
    from contabilidad.services import contabilizar_asiento, ultimo_numero_asiento

    faltante = Decimal("0")
    sobrante = Decimal("0")
    for d in ajuste.detalles.all():
        if d.cantidad < 0:
            faltante += d.valor
        else:
            sobrante += d.valor
    faltante = faltante.quantize(CENTIMO, rounding=ROUND_HALF_UP)
    sobrante = sobrante.quantize(CENTIMO, rounding=ROUND_HALF_UP)
    if faltante <= 0 and sobrante <= 0:
        return None

    fecha = timezone.localtime(ajuste.fecha).date()
    periodo = PeriodoContable.objects.filter(anio=fecha.year, mes=fecha.month).first()
    if not periodo:
        raise ValidationError(
            f"No existe el período contable {fecha.month:02d}/{fecha.year}. "
            "Créalo antes de aprobar el ajuste."
        )
    if periodo.estado == PeriodoContable.Estado.CERRADO:
        raise ValidationError(
            f"El período contable {periodo} está cerrado; no se puede registrar el ajuste."
        )

    codigos = sorted({CUENTA_MERCADERIAS_MONTURAS, cta_gasto, cta_ingreso})
    cuentas = {c.codigo: c for c in CuentaContable.objects.filter(codigo__in=codigos)}
    faltan = [c for c in codigos if c not in cuentas]
    if faltan:
        raise ValidationError(
            "Faltan cuentas contables: " + ", ".join(faltan)
            + ". Ejecuta: python manage.py migrate (o cargar_plan_contable)."
        )

    numero = (ultimo_numero_asiento(periodo) or 0) + 1
    referencia = f"Toma #{ajuste.toma_id}" if ajuste.toma_id else f"Ajuste #{ajuste.pk}"
    asiento = AsientoContable.objects.create(
        numero=numero,
        fecha=fecha,
        periodo=periodo,
        tipo=(
            AsientoContable.TipoAsiento.APERTURA if inicial
            else AsientoContable.TipoAsiento.AJUSTE
        ),
        glosa=(
            f"Inventario inicial de monturas - {referencia}" if inicial
            else f"Ajuste de inventario de monturas - {referencia}"
        ),
        estado=AsientoContable.Estado.BORRADOR,
        origen=ORIGEN_ASIENTO,
        origen_id=ajuste.pk,
    )
    lineas = []
    if sobrante > 0:
        lineas += [
            (cuentas[CUENTA_MERCADERIAS_MONTURAS],
             "Inventario inicial de monturas" if inicial else "Ingreso por sobrantes",
             sobrante, Decimal("0")),
            (cuentas[cta_ingreso],
             "Aporte en mercaderías" if inicial else "Sobrantes de monturas",
             Decimal("0"), sobrante),
        ]
    if faltante > 0:
        lineas += [
            (cuentas[cta_gasto],
             "Menor inventario inicial" if inicial else "Faltantes de monturas",
             faltante, Decimal("0")),
            (cuentas[CUENTA_MERCADERIAS_MONTURAS],
             "Monturas no encontradas" if inicial else "Salida por faltantes",
             Decimal("0"), faltante),
        ]
    for i, (cuenta, desc, debe, haber) in enumerate(lineas, start=1):
        DetalleAsiento.objects.create(
            asiento=asiento, secuencia=i, cuenta=cuenta, descripcion=desc,
            debe=debe, haber=haber, referencia=referencia,
        )
    contabilizar_asiento(asiento)
    return asiento


def asiento_de(ajuste):
    from contabilidad.models import AsientoContable
    return (
        AsientoContable.objects
        .filter(origen=ORIGEN_ASIENTO, origen_id=ajuste.pk)
        .exclude(estado=AsientoContable.Estado.ANULADO)
        .first()
    )


@transaction.atomic
def aprobar_ajuste(toma, usuario, motivos=None, observacion=""):
    """
    motivos: {producto_id: Motivo}. Crea el ajuste por todas las
    diferencias, recalcula el kardex y registra el asiento.
    Si algo falla (p. ej. período cerrado), no se guarda nada.
    """
    motivos = motivos or {}
    toma = TomaInventario.objects.select_for_update().get(pk=toma.pk)
    if toma.estado != TomaInventario.Estado.CERRADA:
        raise ValidationError("La toma debe estar cerrada y sin ajustar.")

    diferencias = list(
        toma.detalles.exclude(diferencia=0).select_related("producto")
    )
    if not diferencias:
        toma.estado = TomaInventario.Estado.AJUSTADA
        toma.save(update_fields=["estado"])
        return None

    if toma.es_inicial and not puede_ser_inicial():
        raise ValidationError(
            "Ya existe un ajuste aprobado: esta toma ya no puede ser la inicial."
        )
    # La toma inicial se fecha el día 1 del mes: el stock final es el
    # mismo (= conteo) y las ventas del mes anteriores a la toma toman
    # su costo de este inventario inicial.
    fecha_ajuste = inicio_de_mes(toma.fecha_inicio) if toma.es_inicial else toma.fecha_cierre

    validos = set(DetalleAjusteInventario.Motivo.values)
    ajuste = AjusteInventario.objects.create(
        toma=toma, fecha=fecha_ajuste, aprobado_por=usuario,
        observacion=(observacion or "")[:255],
    )
    DetalleAjusteInventario.objects.bulk_create([
        DetalleAjusteInventario(
            ajuste=ajuste,
            producto=d.producto,
            cantidad=d.diferencia,
            costo_unitario=d.costo_unitario,
            motivo=(
                motivos.get(d.producto_id)
                if motivos.get(d.producto_id) in validos
                else (
                    DetalleAjusteInventario.Motivo.PERDIDA
                    if d.diferencia < 0 and not toma.es_inicial
                    else DetalleAjusteInventario.Motivo.ERROR_REGISTRO
                )
            ),
        )
        for d in diferencias
    ])

    for d in diferencias:
        recalcular_kardex_producto(d.producto)

    _crear_asiento_ajuste(ajuste)

    toma.estado = TomaInventario.Estado.AJUSTADA
    toma.save(update_fields=["estado"])
    return ajuste


@transaction.atomic
def anular_ajuste(ajuste, usuario):
    from contabilidad.models import AsientoContable, PeriodoContable

    ajuste = AjusteInventario.objects.select_for_update().get(pk=ajuste.pk)
    if ajuste.estado != AjusteInventario.Estado.APROBADO:
        raise ValidationError("El ajuste ya está anulado.")

    asiento = asiento_de(ajuste)
    if asiento:
        if asiento.periodo.estado == PeriodoContable.Estado.CERRADO:
            raise ValidationError(
                f"El período contable {asiento.periodo} está cerrado; "
                "no se puede anular el ajuste."
            )
        asiento.estado = AsientoContable.Estado.ANULADO
        asiento.save(update_fields=["estado", "actualizado_en"])

    ajuste.estado = AjusteInventario.Estado.ANULADO
    ajuste.anulado_por = usuario
    ajuste.fecha_anulacion = timezone.now()
    ajuste.save(update_fields=["estado", "anulado_por", "fecha_anulacion"])

    for d in ajuste.detalles.select_related("producto"):
        recalcular_kardex_producto(d.producto)

    if ajuste.toma_id:
        TomaInventario.objects.filter(pk=ajuste.toma_id).update(
            estado=TomaInventario.Estado.CERRADA
        )
    return ajuste


# ============================================================
# 6. HISTORIAL
# ============================================================

def faltantes_recurrentes(minimo=2):
    estados = [TomaInventario.Estado.CERRADA, TomaInventario.Estado.AJUSTADA]
    return (
        DetalleTomaInventario.objects
        .filter(toma__estado__in=estados, diferencia__lt=0)
        .values("producto_id", "producto__cod", "producto__descripcion",
                "producto__marca", "producto__tipo")
        .annotate(veces=Count("toma", distinct=True))
        .filter(veces__gte=minimo)
        .order_by("-veces", "producto__cod")
    )
