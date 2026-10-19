"""
IGV: tasa, cálculo del IGV incluido en un importe y lectura del
IGV crédito fiscal desde los formularios.

Tasa vigente: 18% (desde 2026 se reparte en 15.5% IGV + 2.5% IPM
por la Ley 32387; el total no cambia). Si la tasa cambiara, basta
con definir CONTABILIDAD_TASA_IGV en settings.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.conf import settings


CENTIMO = Decimal("0.01")

CUENTA_IGV = "40111"

# Texto con el que se identifican las líneas de crédito fiscal
# en el mayor (lo usa la liquidación mensual).
DESCRIPCION_CREDITO_FISCAL = "IGV crédito fiscal"


def tasa_igv():
    return Decimal(
        str(getattr(settings, "CONTABILIDAD_TASA_IGV", "0.18"))
    )


def igv_incluido(total):
    """
    IGV contenido en un importe que ya incluye IGV.

    118.00 -> 18.00
    """

    total = Decimal(total or 0)

    if total <= 0:
        return Decimal("0.00")

    base = (total / (1 + tasa_igv())).quantize(
        CENTIMO,
        rounding=ROUND_HALF_UP,
    )

    return (total - base).quantize(CENTIMO)


def igv_maximo_permitido(total):
    """
    Tope razonable del IGV para un importe total
    (el IGV si todo el comprobante estuviera gravado),
    con un céntimo de tolerancia por redondeo.
    """

    return igv_incluido(total) + CENTIMO


def leer_igv_formulario(request, total, errores):
    """
    Lee del POST:

        con_credito_fiscal = "1"  (casilla marcada)
        igv_credito_fiscal = importe (opcional)

    Si la casilla está marcada y no se escribió el importe,
    lo calcula como el 18% incluido en el total.
    Devuelve Decimal("0.00") si no hay crédito fiscal.
    """

    if request.POST.get("con_credito_fiscal") != "1":
        return Decimal("0.00")

    texto = (
        request.POST.get("igv_credito_fiscal", "")
        .strip()
        .replace(",", ".")
    )

    if not texto:
        return igv_incluido(total)

    try:
        igv = Decimal(texto).quantize(
            CENTIMO,
            rounding=ROUND_HALF_UP,
        )
    except (InvalidOperation, ValueError):
        errores.append("El IGV ingresado no es válido.")
        return Decimal("0.00")

    if igv < 0:
        errores.append("El IGV no puede ser negativo.")
        return Decimal("0.00")

    return igv


def validar_igv_documento(igv, total, campo="igv_credito_fiscal"):
    """
    Reglas comunes para el modelo. Devuelve un dict de errores
    (vacío si todo está bien).
    """

    errores = {}

    igv = igv or Decimal("0.00")

    if igv < 0:
        errores[campo] = "El IGV no puede ser negativo."

    elif igv > 0 and total is not None:

        if igv > igv_maximo_permitido(total):
            errores[campo] = (
                "El IGV no puede superar el 18% incluido en "
                f"el total (máximo S/ {igv_incluido(total):.2f})."
            )

    return errores
