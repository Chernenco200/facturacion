"""
Saldos por pagar a proveedores y trabajadores.

El saldo se calcula desde el libro mayor (DetalleAsiento) y no
desde los documentos, para que siempre cuadre con el saldo de
las cuentas 41 y 42 del balance:

    saldo = SUMA(haber) - SUMA(debe)   en cuentas 41xxx y 42xxx

    saldo > 0  -> se le debe al tercero
    saldo < 0  -> se le pagó de más / anticipo a su favor nuestro

Las líneas sin tercero se agrupan como "Sin identificar" para
que el total del reporte sea igual al total del mayor. Se
corrigen con el comando `python manage.py asignar_terceros` o
editando la línea en el admin.
"""

from datetime import date
from decimal import Decimal

from django.db.models import Count, DecimalField, Max, Q, Sum, Value
from django.db.models.functions import Coalesce

from .models import (
    AsientoContable,
    CompraDirectaVenta,
    CompraMercaderia,
    DetalleAsiento,
    OperacionContable,
    ServicioTerceroVenta,
    Tercero,
)


PREFIJOS_POR_PAGAR = ("41", "42")

CERO = Decimal("0.00")


def _filtro_cuentas_por_pagar(prefijo="cuenta__codigo"):
    filtro = Q()

    for prefijo_cuenta in PREFIJOS_POR_PAGAR:
        filtro |= Q(**{f"{prefijo}__startswith": prefijo_cuenta})

    return filtro


def movimientos_por_pagar(fecha_corte=None):
    """
    Líneas contabilizadas de cuentas 41 y 42 hasta la fecha
    de corte (inclusive).
    """

    movimientos = (
        DetalleAsiento.objects
        .filter(
            _filtro_cuentas_por_pagar(),
            asiento__estado=AsientoContable.Estado.CONTABILIZADO,
        )
    )

    if fecha_corte:
        movimientos = movimientos.filter(
            asiento__fecha__lte=fecha_corte,
        )

    return movimientos


def resumen_saldos_por_pagar(
    fecha_corte=None,
    tipo=None,
    incluir_cancelados=False,
):
    """
    Devuelve un dict con:

        filas: lista de dicts por tercero
            tercero_id, nombre, tipo, tipo_display,
            total_haber, total_debe, saldo,
            ultimo_movimiento, movimientos

        total_por_pagar: suma de saldos positivos
        total_a_favor:   suma de saldos negativos (en positivo)
        saldo_neto:      total_por_pagar - total_a_favor
                         (= saldo de 41 + 42 en el mayor
                          si no se filtra por tipo)
        sin_identificar: fila de líneas sin tercero o None
    """

    cero_decimal = Value(
        CERO,
        output_field=DecimalField(max_digits=15, decimal_places=2),
    )

    movimientos = movimientos_por_pagar(fecha_corte)

    if tipo == "SIN_IDENTIFICAR":
        movimientos = movimientos.filter(tercero__isnull=True)
    elif tipo:
        movimientos = movimientos.filter(tercero__tipo=tipo)

    agrupado = (
        movimientos
        .values(
            "tercero_id",
            "tercero__nombre",
            "tercero__tipo",
            "tercero__numero_documento",
        )
        .annotate(
            total_haber=Coalesce(Sum("haber"), cero_decimal),
            total_debe=Coalesce(Sum("debe"), cero_decimal),
            ultimo_movimiento=Max("asiento__fecha"),
            movimientos=Count("id"),
        )
        .order_by("tercero__tipo", "tercero__nombre")
    )

    tipos = dict(Tercero.Tipo.choices)

    filas = []
    sin_identificar = None

    total_por_pagar = CERO
    total_a_favor = CERO

    for item in agrupado:

        saldo = item["total_haber"] - item["total_debe"]

        fila = {
            "tercero_id": item["tercero_id"],
            "nombre": item["tercero__nombre"] or "Sin identificar",
            "tipo": item["tercero__tipo"] or "",
            "tipo_display": tipos.get(item["tercero__tipo"], "—"),
            "numero_documento": item["tercero__numero_documento"] or "",
            "total_haber": item["total_haber"],
            "total_debe": item["total_debe"],
            "saldo": saldo,
            "saldo_absoluto": abs(saldo),
            "ultimo_movimiento": item["ultimo_movimiento"],
            "movimientos": item["movimientos"],
        }

        if saldo > 0:
            total_por_pagar += saldo
        elif saldo < 0:
            total_a_favor += abs(saldo)

        if item["tercero_id"] is None:
            sin_identificar = fila
            continue

        if saldo == 0 and not incluir_cancelados:
            continue

        filas.append(fila)

    # Mayor deuda primero dentro del reporte.
    filas.sort(key=lambda fila: fila["saldo"], reverse=True)

    return {
        "filas": filas,
        "sin_identificar": sin_identificar,
        "total_por_pagar": total_por_pagar,
        "total_a_favor": total_a_favor,
        "saldo_neto": total_por_pagar - total_a_favor,
    }


def estado_cuenta_tercero(tercero, fecha_corte=None):
    """
    Movimientos del tercero en cuentas 41/42 con saldo
    acumulado, en orden cronológico. `tercero` puede ser None
    para ver las líneas sin identificar.
    """

    movimientos = movimientos_por_pagar(fecha_corte)

    if tercero is None:
        movimientos = movimientos.filter(tercero__isnull=True)
    else:
        movimientos = movimientos.filter(tercero=tercero)

    movimientos = (
        movimientos
        .select_related("asiento", "asiento__periodo", "cuenta")
        .order_by("asiento__fecha", "asiento__numero", "secuencia")
    )

    lineas = []
    saldo = CERO
    total_debe = CERO
    total_haber = CERO

    for detalle in movimientos:

        saldo += detalle.haber - detalle.debe
        total_debe += detalle.debe
        total_haber += detalle.haber

        lineas.append({
            "detalle": detalle,
            "saldo": saldo,
        })

    return {
        "lineas": lineas,
        "total_debe": total_debe,
        "total_haber": total_haber,
        "saldo": saldo,
    }


def documentos_pendientes_tercero(tercero):
    """
    Documentos del tercero que aún tienen saldo, con el
    enlace para registrar el pago cuando el sistema lo permite.
    """

    pendientes = []

    operaciones = (
        OperacionContable.objects
        .filter(
            tercero=tercero,
            estado=OperacionContable.Estado.CONTABILIZADA,
            cuenta_por_pagar__isnull=False,
        )
        .select_related("concepto", "cuenta_por_pagar")
        .order_by("fecha", "id")
    )

    for operacion in operaciones:

        saldo = operacion.saldo_pendiente

        if saldo <= CERO:
            continue

        pendientes.append({
            "tipo": "operacion",
            "fecha": operacion.fecha,
            "descripcion": (
                operacion.descripcion
                or operacion.concepto.nombre
            ),
            "documento": " ".join(
                parte
                for parte in [
                    operacion.tipo_documento,
                    operacion.numero_documento,
                ]
                if parte
            ),
            "cuenta": operacion.cuenta_por_pagar,
            "importe": operacion.importe_total,
            "saldo": saldo,
            "vencimiento": operacion.fecha_vencimiento,
            "objeto_id": operacion.id,
        })

    compras = (
        CompraDirectaVenta.objects
        .filter(
            tercero=tercero,
            estado=CompraDirectaVenta.Estado.CONTABILIZADA,
            cuenta_proveedor__isnull=False,
        )
        .select_related(
            "cuenta_proveedor",
            "detalle_costo__detalle_ticket",
        )
        .order_by("fecha_compra", "id")
    )

    for compra in compras:

        saldo = compra.saldo_pendiente.quantize(Decimal("0.01"))

        if saldo <= CERO:
            continue

        pendientes.append({
            "tipo": "compra",
            "fecha": compra.fecha_compra,
            "descripcion": (
                compra.detalle_costo.detalle_ticket.descripcion
            ),
            "documento": " ".join(
                parte
                for parte in [
                    compra.tipo_documento,
                    compra.numero_documento,
                ]
                if parte
            ),
            "cuenta": compra.cuenta_proveedor,
            "importe": compra.costo_total.quantize(Decimal("0.01")),
            "saldo": saldo,
            "vencimiento": compra.fecha_vencimiento,
            "objeto_id": compra.id,
        })

    servicios = (
        ServicioTerceroVenta.objects
        .filter(
            tercero=tercero,
            estado=ServicioTerceroVenta.Estado.CONTABILIZADO,
            forma_pago=ServicioTerceroVenta.FormaPago.CREDITO,
        )
        .select_related("cuenta_proveedor", "propuesta__ticket")
        .order_by("fecha_servicio", "id")
    )

    for servicio in servicios:

        # Los servicios al crédito aún no tienen un registro
        # de pagos propio; se muestran por su importe total.
        pendientes.append({
            "tipo": "servicio",
            "fecha": servicio.fecha_servicio,
            "descripcion": (
                servicio.descripcion
                or servicio.get_tipo_servicio_display()
            ),
            "documento": (
                f"Ticket {servicio.propuesta.ticket.numero:06d}"
            ),
            "cuenta": servicio.cuenta_proveedor,
            "importe": servicio.costo,
            "saldo": servicio.costo,
            "vencimiento": None,
            "objeto_id": servicio.id,
        })

    compras_mercaderia = (
        CompraMercaderia.objects
        .filter(
            tercero=tercero,
            estado=CompraMercaderia.Estado.CONTABILIZADA,
            cuenta_proveedor__isnull=False,
        )
        .select_related("compra", "cuenta_proveedor")
        .order_by("compra__fecha", "id")
    )

    for condicion in compras_mercaderia:

        if condicion.saldo_inicial <= CERO:
            continue

        compra = condicion.compra

        # Los pagos a cuenta (PagoTercero) no se asignan a una
        # factura en particular; se muestra el saldo original.
        pendientes.append({
            "tipo": "compra_mercaderia",
            "fecha": compra.fecha,
            "descripcion": "Compra de mercadería",
            "documento": (
                f"{compra.tipo_comprobante} "
                f"{compra.serie}-{compra.numero}"
            ),
            "cuenta": condicion.cuenta_proveedor,
            "importe": condicion.total_comprobante,
            "saldo": condicion.saldo_inicial,
            "vencimiento": condicion.fecha_vencimiento,
            "objeto_id": condicion.id,
        })

    pendientes.sort(
        key=lambda item: (
            item["fecha"] is None,
            item["fecha"] or date.min,
        )
    )

    return pendientes
