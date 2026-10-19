"""
Impuestos mensuales del Régimen Especial de Renta (RER).

Renta:  1.5% de los ingresos netos del mes (cuota definitiva).
IGV:    débito fiscal de ventas - crédito fiscal de compras.

Ambos se declaran en el Formulario Virtual 621. La tasa de renta
se puede cambiar con CONTABILIDAD_TASA_RENTA_MENSUAL en settings
(por ejemplo, si algún día pasas al Régimen MYPE Tributario).

Asiento de provisión (al cerrar el mes):

    DEBE   88101  Impuesto a la renta - RER
    HABER  40171  Impuesto a la renta por pagar

Cuando pagas a SUNAT, registras un gasto/operación con un
concepto cuya cuenta sea 40171 (renta) o 40111 (IGV).
"""

from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce

from .igv import CUENTA_IGV, DESCRIPCION_CREDITO_FISCAL
from .models import (
    AsientoContable,
    CuentaContable,
    DetalleAsiento,
    PeriodoContable,
)


CERO = Decimal("0.00")
CENTIMO = Decimal("0.01")
SOL = Decimal("1")

CUENTA_GASTO_RENTA = "88101"
CUENTA_RENTA_POR_PAGAR = "40171"

ORIGEN_RENTA = "RENTA_RER"

# Límite anual de ingresos netos del RER.
LIMITE_INGRESOS_RER = Decimal("525000")


def tasa_renta_mensual():
    return Decimal(
        str(getattr(settings, "CONTABILIDAD_TASA_RENTA_MENSUAL", "0.015"))
    )


def _cero_decimal():
    return Value(
        CERO,
        output_field=DecimalField(max_digits=15, decimal_places=2),
    )


def _movimientos_contabilizados():
    return DetalleAsiento.objects.filter(
        asiento__estado=AsientoContable.Estado.CONTABILIZADO,
    )


def ingresos_netos(fecha_desde, fecha_hasta):
    """
    Ingresos netos (sin IGV) entre dos fechas: saldo acreedor de
    todas las cuentas de ingreso. Las notas de crédito ya restan
    porque revierten el ingreso por el Debe. Se excluye el asiento
    de cierre anual.
    """

    totales = (
        _movimientos_contabilizados()
        .filter(
            cuenta__tipo=CuentaContable.TipoCuenta.INGRESO,
            asiento__fecha__gte=fecha_desde,
            asiento__fecha__lte=fecha_hasta,
        )
        .exclude(asiento__tipo=AsientoContable.TipoAsiento.CIERRE)
        .aggregate(
            haber=Coalesce(Sum("haber"), _cero_decimal()),
            debe=Coalesce(Sum("debe"), _cero_decimal()),
        )
    )

    return totales["haber"] - totales["debe"]


def calcular_renta_mensual(periodo):
    """
    Devuelve (ingresos_netos, cuota). La cuota se redondea a soles
    enteros, igual que en el Formulario 621.
    """

    base = ingresos_netos(periodo.fecha_inicio, periodo.fecha_fin)

    if base <= 0:
        return base, CERO

    cuota = (base * tasa_renta_mensual()).quantize(
        SOL,
        rounding=ROUND_HALF_UP,
    )

    return base, cuota.quantize(CENTIMO)


def provision_existente(periodo):
    return (
        AsientoContable.objects
        .filter(
            origen=ORIGEN_RENTA,
            origen_id=periodo.id,
        )
        .exclude(estado=AsientoContable.Estado.ANULADO)
        .first()
    )


def _cuenta_gasto_renta():
    """
    88101 Impuesto a la renta - RER. Si el plan contable aún no
    la tiene (se agregó a cargar_plan_contable), se crea aquí.
    """

    padre, _ = CuentaContable.objects.get_or_create(
        codigo="88",
        defaults={
            "nombre": "Impuesto a la renta",
            "codigo_pcge": "88",
            "tipo": CuentaContable.TipoCuenta.GASTO,
            "naturaleza": CuentaContable.Naturaleza.DEUDORA,
            "estado_financiero": CuentaContable.EstadoFinanciero.ER,
            "nivel": 1,
            "acepta_movimientos": False,
        },
    )

    cuenta, _ = CuentaContable.objects.get_or_create(
        codigo=CUENTA_GASTO_RENTA,
        defaults={
            "nombre": "Impuesto a la renta - RER (cuota mensual)",
            "codigo_pcge": "881",
            "cuenta_padre": padre,
            "tipo": CuentaContable.TipoCuenta.GASTO,
            "naturaleza": CuentaContable.Naturaleza.DEUDORA,
            "estado_financiero": CuentaContable.EstadoFinanciero.ER,
            "nivel": 2,
            "acepta_movimientos": True,
        },
    )

    return cuenta


@transaction.atomic
def provisionar_renta_rer(periodo):
    """
    Registra (o actualiza) la provisión de la cuota mensual de
    renta del período. Es idempotente:

    - Si ya existe con el mismo importe, no hace nada.
    - Si el importe cambió (p. ej. se reabrió el mes y se
      agregaron ventas), anula la anterior y crea una nueva.

    Devuelve un dict con base, cuota, asiento y accion
    ("sin_cambios", "creada", "actualizada", "sin_ingresos").
    """

    # Import diferido para evitar importación circular.
    from .services import contabilizar_asiento, ultimo_numero_asiento

    if periodo.estado == PeriodoContable.Estado.CERRADO:
        raise ValidationError(
            "El período está cerrado; reábralo para "
            "actualizar la provisión de renta."
        )

    base, cuota = calcular_renta_mensual(periodo)

    existente = provision_existente(periodo)

    if existente and existente.total_debe == cuota:
        return {
            "base": base,
            "cuota": cuota,
            "asiento": existente,
            "accion": "sin_cambios",
        }

    if existente:
        existente.estado = AsientoContable.Estado.ANULADO
        existente.save(update_fields=["estado", "actualizado_en"])

    if cuota <= 0:
        return {
            "base": base,
            "cuota": CERO,
            "asiento": None,
            "accion": "sin_ingresos",
        }

    numero = (ultimo_numero_asiento(periodo) or 0) + 1

    tasa_texto = f"{tasa_renta_mensual() * 100:.1f}%"

    asiento = AsientoContable.objects.create(
        periodo=periodo,
        numero=numero,
        fecha=periodo.fecha_fin,
        tipo=AsientoContable.TipoAsiento.AUTOMATICO,
        glosa=(
            f"Impuesto a la renta RER {tasa_texto} - "
            f"{periodo} (ingresos netos S/ {base:.2f})"
        ),
        estado=AsientoContable.Estado.BORRADOR,
        origen=ORIGEN_RENTA,
        origen_id=periodo.id,
    )

    DetalleAsiento.objects.create(
        asiento=asiento,
        secuencia=1,
        cuenta=_cuenta_gasto_renta(),
        descripcion=f"Cuota mensual RER {tasa_texto}",
        debe=cuota,
        haber=CERO,
        referencia=f"Form. 621 - {periodo}",
    )

    DetalleAsiento.objects.create(
        asiento=asiento,
        secuencia=2,
        cuenta=CuentaContable.objects.get(codigo=CUENTA_RENTA_POR_PAGAR),
        descripcion=f"Renta RER por pagar - {periodo}",
        debe=CERO,
        haber=cuota,
        referencia=f"Form. 621 - {periodo}",
    )

    contabilizar_asiento(asiento)

    return {
        "base": base,
        "cuota": cuota,
        "asiento": asiento,
        "accion": "actualizada" if existente else "creada",
    }


def liquidacion_mensual(periodo):
    """
    Resumen para llenar el Formulario 621 del período.
    """

    movimientos_mes = (
        _movimientos_contabilizados()
        .filter(asiento__periodo=periodo)
        .exclude(asiento__tipo=AsientoContable.TipoAsiento.CIERRE)
    )

    igv_mes = movimientos_mes.filter(cuenta__codigo=CUENTA_IGV)

    # Débito fiscal: IGV de ventas menos IGV de notas de crédito.
    debito = igv_mes.filter(
        asiento__origen__in=["VENTA", "NOTA_CREDITO"],
    ).aggregate(
        haber=Coalesce(Sum("haber"), _cero_decimal()),
        debe=Coalesce(Sum("debe"), _cero_decimal()),
    )

    igv_debito = debito["haber"] - debito["debe"]

    # Crédito fiscal: líneas marcadas al registrar compras/gastos
    # con factura.
    igv_credito = igv_mes.filter(
        descripcion__startswith=DESCRIPCION_CREDITO_FISCAL,
    ).aggregate(
        total=Coalesce(Sum("debe"), _cero_decimal()),
    )["total"]

    # Saldo a favor arrastrado: si la 40111 terminó el mes
    # anterior con saldo deudor, es crédito fiscal no usado.
    saldo_previo = (
        _movimientos_contabilizados()
        .filter(
            cuenta__codigo=CUENTA_IGV,
            asiento__fecha__lt=periodo.fecha_inicio,
        )
        .aggregate(
            haber=Coalesce(Sum("haber"), _cero_decimal()),
            debe=Coalesce(Sum("debe"), _cero_decimal()),
        )
    )

    saldo_favor_anterior = max(
        saldo_previo["debe"] - saldo_previo["haber"],
        CERO,
    )

    igv_resultado = igv_debito - igv_credito - saldo_favor_anterior

    # Ventas gravadas (base) para la casilla del 621.
    base, cuota = calcular_renta_mensual(periodo)

    provision = provision_existente(periodo)

    # Saldo de la 40111 al cierre del mes (incluye pagos a SUNAT
    # y saldos a favor de meses anteriores).
    saldo_40111 = (
        _movimientos_contabilizados()
        .filter(
            cuenta__codigo=CUENTA_IGV,
            asiento__fecha__lte=periodo.fecha_fin,
        )
        .aggregate(
            haber=Coalesce(Sum("haber"), _cero_decimal()),
            debe=Coalesce(Sum("debe"), _cero_decimal()),
        )
    )

    saldo_igv_cuenta = saldo_40111["haber"] - saldo_40111["debe"]

    # Acumulado del año para vigilar el límite del RER.
    inicio_anio = (
        PeriodoContable.objects
        .filter(anio=periodo.anio)
        .order_by("mes")
        .values_list("fecha_inicio", flat=True)
        .first()
    ) or periodo.fecha_inicio

    ingresos_anio = ingresos_netos(inicio_anio, periodo.fecha_fin)

    porcentaje_limite = (
        (ingresos_anio / LIMITE_INGRESOS_RER * 100).quantize(Decimal("0.1"))
        if ingresos_anio > 0
        else Decimal("0.0")
    )

    return {
        "periodo": periodo,
        "ventas_netas": base,
        "igv_debito": igv_debito,
        "igv_credito": igv_credito,
        "saldo_favor_anterior": saldo_favor_anterior,
        "igv_resultado": igv_resultado,
        "igv_a_pagar": max(igv_resultado, CERO),
        "igv_saldo_a_favor": abs(min(igv_resultado, CERO)),
        "igv_a_pagar_redondeado": max(igv_resultado, CERO).quantize(
            SOL, rounding=ROUND_HALF_UP
        ),
        "saldo_igv_cuenta": saldo_igv_cuenta,
        "tasa_renta": tasa_renta_mensual() * 100,
        "renta_cuota": cuota,
        "provision": provision,
        "provision_desfasada": bool(
            provision and provision.total_debe != cuota
        ),
        "ingresos_anio": ingresos_anio,
        "limite_rer": LIMITE_INGRESOS_RER,
        "porcentaje_limite": porcentaje_limite,
        "cerca_del_limite": porcentaje_limite >= Decimal("80"),
    }
