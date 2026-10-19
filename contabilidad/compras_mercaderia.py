"""
Contabilización de las compras de mercadería (core.Compra) y de
los pagos a cuenta de proveedores / trabajadores.

Compra de mercadería:

    DEBE   20xxx  Inventario (valor sin IGV recuperable)
    DEBE   40111  IGV crédito fiscal (solo factura)
    HABER  10xxx  Caja / Banco  (lo pagado)
    HABER  42xxx  Proveedor     (el saldo, con su tercero)

Pago a tercero:

    DEBE   41/42  Cuenta por pagar (con su tercero)
    HABER  10xxx  Caja / Banco
"""

from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .igv import (
    CUENTA_IGV,
    DESCRIPCION_CREDITO_FISCAL,
    igv_incluido,
    tasa_igv,
)
from .models import (
    AsientoContable,
    CompraMercaderia,
    CuentaContable,
    DetalleAsiento,
    PagoTercero,
    PeriodoContable,
    Tercero,
)
from .services import (
    contabilizar_asiento,
    tipo_tercero_para_cuenta,
    ultimo_numero_asiento,
)


CERO = Decimal("0.00")
CENTIMO = Decimal("0.01")

ORIGEN_COMPRA = "COMPRA_MERCADERIA"
ORIGEN_PAGO_TERCERO = "PAGO_TERCERO"


# ============================================================
# AUXILIARES
# ============================================================

def _q(valor):
    return Decimal(str(valor or 0)).quantize(CENTIMO, rounding=ROUND_HALF_UP)


def nombre_proveedor(proveedor):
    for atributo in ("razon_social", "nombre", "nombre_comercial"):
        valor = getattr(proveedor, atributo, "")
        if valor and str(valor).strip():
            return str(valor).strip()
    return str(proveedor)


def documento_proveedor(proveedor):
    for atributo in ("ruc", "numero_documento", "dni"):
        valor = getattr(proveedor, atributo, "")
        if valor and str(valor).strip():
            return str(valor).strip()
    return ""


def cuenta_inventario_producto(producto):
    """
    Misma clasificación que usa el costo de ventas, para que la
    cuenta 20 que se carga al comprar sea la que se abona al vender.
    """

    texto = (
        f"{producto.tipo or ''} {producto.descripcion or ''}"
    ).strip().lower()

    if "montura" in texto:
        codigo = "20101"
    elif "contacto" in texto:
        codigo = "20103"
    elif "líquido" in texto or "liquido" in texto:
        codigo = "20107"
    elif "accesorio" in texto or "estuche" in texto:
        codigo = "20106"
    elif "luna" in texto:
        codigo = "20102"
    else:
        return None

    return CuentaContable.objects.filter(codigo=codigo).first()


def calcular_importes(compra, usa_credito_fiscal, precios_incluyen_igv):
    """
    Devuelve (base_imponible, igv, total_comprobante) a partir de
    los subtotales del detalle de la compra.
    """

    suma_detalle = _q(
        compra.detalles.aggregate(total=Sum("subtotal"))["total"]
    )

    if compra.tipo_comprobante != "FA":
        usa_credito_fiscal = False

    if not usa_credito_fiscal:
        return suma_detalle, CERO, suma_detalle

    if precios_incluyen_igv:
        igv = igv_incluido(suma_detalle)
        return suma_detalle - igv, igv, suma_detalle

    igv = _q(suma_detalle * tasa_igv())
    return suma_detalle, igv, suma_detalle + igv


def costo_unitario_sin_igv(detalle_compra):
    """
    Costo con el que el producto entra al Kardex. Lo usa
    core/kardex.py: si la compra es factura con crédito fiscal y
    los precios incluyen IGV, se descuenta el IGV.
    """

    precio = Decimal(str(detalle_compra.precio_compra or 0))

    condicion = getattr(
        detalle_compra.compra,
        "condicion_contable",
        None,
    )

    if (
        condicion
        and condicion.usa_credito_fiscal
        and condicion.precios_incluyen_igv
        and detalle_compra.compra.tipo_comprobante == "FA"
    ):
        return (precio / (1 + tasa_igv())).quantize(Decimal("0.0001"))

    return precio


def _periodo_abierto(fecha):
    periodo = (
        PeriodoContable.objects
        .filter(fecha_inicio__lte=fecha, fecha_fin__gte=fecha)
        .first()
    )

    if not periodo:
        raise ValidationError(
            f"No existe un período contable para el {fecha:%d/%m/%Y}."
        )

    if periodo.estado == PeriodoContable.Estado.CERRADO:
        raise ValidationError(f"El período {periodo} está cerrado.")

    return periodo


def saldo_tercero_en_cuenta(tercero, cuenta):
    """Saldo acreedor (lo que se le debe) del tercero en una cuenta."""

    totales = (
        DetalleAsiento.objects
        .filter(
            tercero=tercero,
            cuenta=cuenta,
            asiento__estado=AsientoContable.Estado.CONTABILIZADO,
        )
        .aggregate(haber=Sum("haber"), debe=Sum("debe"))
    )

    return (totales["haber"] or CERO) - (totales["debe"] or CERO)


# ============================================================
# COMPRA DE MERCADERÍA
# ============================================================

@transaction.atomic
def contabilizar_compra_mercaderia(condicion):

    condicion = (
        CompraMercaderia.objects
        .select_for_update()
        .select_related("compra", "compra__proveedor")
        .get(pk=condicion.pk)
    )

    compra = condicion.compra

    if condicion.estado == CompraMercaderia.Estado.CONTABILIZADA:
        raise ValidationError("La compra ya está contabilizada.")

    if compra.tipo_comprobante == "NC":
        raise ValidationError(
            "Las notas de crédito de proveedores todavía no se "
            "contabilizan desde aquí; regístrela con un asiento manual."
        )

    detalles = list(
        compra.detalles.select_related("producto").order_by("id")
    )

    if not detalles:
        raise ValidationError("La compra no tiene productos.")

    # --------------------------------------------------------
    # Importes recalculados desde el detalle (no desde el total
    # enviado por el navegador).
    # --------------------------------------------------------

    base, igv, total = calcular_importes(
        compra,
        condicion.usa_credito_fiscal,
        condicion.precios_incluyen_igv,
    )

    if total <= 0:
        raise ValidationError("El total de la compra debe ser mayor que cero.")

    condicion.base_imponible = base
    condicion.igv_credito_fiscal = igv
    condicion.total_comprobante = total
    condicion.full_clean()

    # --------------------------------------------------------
    # Cuentas de inventario por producto
    # --------------------------------------------------------

    sin_cuenta = []
    importes_por_cuenta = {}
    suma_subtotales = sum(
        (Decimal(str(d.subtotal or 0)) for d in detalles),
        CERO,
    )

    for detalle in detalles:
        cuenta = cuenta_inventario_producto(detalle.producto)
        if cuenta is None:
            sin_cuenta.append(detalle.producto.descripcion or detalle.producto.cod)
            continue
        importes_por_cuenta.setdefault(cuenta, CERO)
        importes_por_cuenta[cuenta] += Decimal(str(detalle.subtotal or 0))

    if sin_cuenta:
        raise ValidationError(
            "No se sabe a qué cuenta de inventario van estos productos; "
            "indique su tipo (montura, luna, lente de contacto, líquido "
            "o accesorio): " + ", ".join(sin_cuenta)
        )

    # Reparto de la base sin IGV entre cuentas, proporcional a los
    # subtotales; la última absorbe el redondeo.
    lineas_inventario = []
    acumulado = CERO
    cuentas = list(importes_por_cuenta.items())

    for indice, (cuenta, subtotal) in enumerate(cuentas, start=1):
        if indice < len(cuentas) and suma_subtotales > 0:
            importe = _q(base * subtotal / suma_subtotales)
            acumulado += importe
        else:
            importe = base - acumulado
        if importe > 0:
            lineas_inventario.append((cuenta, importe))

    # --------------------------------------------------------
    # Período, tercero, cabecera
    # --------------------------------------------------------

    periodo = _periodo_abierto(compra.fecha)

    if (
        AsientoContable.objects
        .filter(origen=ORIGEN_COMPRA, origen_id=compra.id)
        .exclude(estado=AsientoContable.Estado.ANULADO)
        .exists()
    ):
        raise ValidationError("Esta compra ya tiene un asiento contable.")

    proveedor = nombre_proveedor(compra.proveedor)

    tercero = condicion.tercero

    if tercero is None and condicion.saldo_inicial > 0:
        tercero = Tercero.obtener_o_crear(
            proveedor,
            tipo_tercero_para_cuenta(condicion.cuenta_proveedor),
        )
        ruc = documento_proveedor(compra.proveedor)
        if tercero and ruc and not tercero.numero_documento:
            tercero.numero_documento = ruc
            tercero.save(update_fields=["numero_documento"])

    referencia = f"{compra.tipo_comprobante} {compra.serie}-{compra.numero}"

    numero = (ultimo_numero_asiento(periodo) or 0) + 1

    asiento = AsientoContable.objects.create(
        periodo=periodo,
        numero=numero,
        fecha=compra.fecha,
        tipo=AsientoContable.TipoAsiento.AUTOMATICO,
        glosa=f"Compra de mercadería - {proveedor} - {referencia}"[:500],
        estado=AsientoContable.Estado.BORRADOR,
        origen=ORIGEN_COMPRA,
        origen_id=compra.id,
    )

    secuencia = 1

    def linea(cuenta, debe=CERO, haber=CERO, descripcion="", tercero_linea=None):
        nonlocal secuencia
        DetalleAsiento.objects.create(
            asiento=asiento,
            secuencia=secuencia,
            cuenta=cuenta,
            descripcion=descripcion[:300],
            debe=debe,
            haber=haber,
            tercero=tercero_linea,
            referencia=referencia[:100],
        )
        secuencia += 1

    for cuenta, importe in lineas_inventario:
        linea(cuenta, debe=importe, descripcion=f"Ingreso a almacén - {cuenta.nombre}")

    if igv > 0:
        linea(
            CuentaContable.objects.get(codigo=CUENTA_IGV),
            debe=igv,
            descripcion=f"{DESCRIPCION_CREDITO_FISCAL} - {referencia}",
        )

    pagado = condicion.monto_pagado or CERO

    if pagado > 0:
        linea(
            condicion.cuenta_pago,
            haber=pagado,
            descripcion=f"Pago a {proveedor}",
        )

    if condicion.saldo_inicial > 0:
        linea(
            condicion.cuenta_proveedor,
            haber=condicion.saldo_inicial,
            descripcion=f"Por pagar a {proveedor}",
            tercero_linea=tercero,
        )

    contabilizar_asiento(asiento)

    condicion.tercero = tercero
    condicion.asiento = asiento
    condicion.estado = CompraMercaderia.Estado.CONTABILIZADA
    condicion.contabilizado_en = timezone.now()
    condicion.save()

    # --------------------------------------------------------
    # El costo del Kardex ahora debe ir sin IGV: recalcular.
    # --------------------------------------------------------

    from core.kardex import recalcular_kardex_producto

    for producto in {detalle.producto for detalle in detalles}:
        recalcular_kardex_producto(producto)

    return asiento


# ============================================================
# PAGO A UN TERCERO
# ============================================================

@transaction.atomic
def registrar_pago_tercero(
    tercero,
    cuenta_por_pagar,
    cuenta_pago,
    fecha_pago,
    monto,
    referencia="",
    observacion="",
):
    # Bloquea al tercero para que dos pagos simultáneos no
    # superen juntos su saldo.
    tercero = Tercero.objects.select_for_update().get(pk=tercero.pk)

    if not (cuenta_por_pagar.codigo.startswith(("41", "42"))):
        raise ValidationError("La cuenta por pagar debe ser 41 o 42.")

    if cuenta_pago.tipo != CuentaContable.TipoCuenta.ACTIVO:
        raise ValidationError("La cuenta de pago debe ser Caja o Banco.")

    for cuenta in (cuenta_por_pagar, cuenta_pago):
        if not cuenta.activo or not cuenta.acepta_movimientos:
            raise ValidationError(
                f"La cuenta {cuenta.codigo} está inactiva o no acepta movimientos."
            )

    monto = _q(monto)

    if monto <= 0:
        raise ValidationError("El monto debe ser mayor que cero.")

    saldo = saldo_tercero_en_cuenta(tercero, cuenta_por_pagar)

    if monto > saldo:
        raise ValidationError(
            f"El pago supera lo que se le debe en la cuenta "
            f"{cuenta_por_pagar.codigo} (S/ {saldo:.2f})."
        )

    periodo = _periodo_abierto(fecha_pago)

    pago = PagoTercero.objects.create(
        tercero=tercero,
        cuenta_por_pagar=cuenta_por_pagar,
        cuenta_pago=cuenta_pago,
        fecha_pago=fecha_pago,
        monto=monto,
        referencia=referencia[:100],
        observacion=observacion,
    )

    numero = (ultimo_numero_asiento(periodo) or 0) + 1

    asiento = AsientoContable.objects.create(
        periodo=periodo,
        numero=numero,
        fecha=fecha_pago,
        tipo=AsientoContable.TipoAsiento.AUTOMATICO,
        glosa=f"Pago a {tercero.nombre}"[:500],
        estado=AsientoContable.Estado.BORRADOR,
        origen=ORIGEN_PAGO_TERCERO,
        origen_id=pago.id,
    )

    DetalleAsiento.objects.create(
        asiento=asiento,
        secuencia=1,
        cuenta=cuenta_por_pagar,
        descripcion=f"Cancelación deuda {tercero.nombre}"[:300],
        debe=monto,
        haber=CERO,
        tercero=tercero,
        referencia=referencia[:100],
    )

    DetalleAsiento.objects.create(
        asiento=asiento,
        secuencia=2,
        cuenta=cuenta_pago,
        descripcion=f"Pago a {tercero.nombre}"[:300],
        debe=CERO,
        haber=monto,
        referencia=referencia[:100],
    )

    contabilizar_asiento(asiento)

    pago.asiento = asiento
    pago.save(update_fields=["asiento"])

    return pago


# ============================================================
# CONDICIÓN DE PAGO DESDE UN FORMULARIO
# ============================================================
#
# La usan el registro de compras de core y la página
# "Contabilizar compra" de contabilidad.
# ============================================================

def cuentas_caja_banco():
    return (
        CuentaContable.objects
        .filter(
            activo=True,
            acepta_movimientos=True,
            codigo__in=["10101", "10401", "10402"],
        )
        .order_by("codigo")
    )


def cuentas_proveedores():
    return (
        CuentaContable.objects
        .filter(
            activo=True,
            acepta_movimientos=True,
            codigo__startswith="42",
        )
        .order_by("codigo")
    )


CAMPOS_CONDICION = (
    "forma_pago",
    "usa_credito_fiscal",
    "precios_incluyen_igv",
    "monto_pagado",
    "fecha_pago",
    "cuenta_pago",
    "cuenta_proveedor",
    "fecha_vencimiento",
    "observacion",
)


def leer_datos_condicion(post):
    """Extrae del POST los campos de la condición de pago."""
    return {
        campo: (post.get(campo) or "").strip()
        for campo in CAMPOS_CONDICION
    }


def preparar_condicion_compra(compra, datos, condicion=None):
    """
    Construye (sin guardar) la CompraMercaderia de una compra a
    partir de los datos del formulario. Devuelve
    (condicion, errores). Los importes se recalculan desde el
    detalle de la compra, que ya debe estar guardado.
    """

    from datetime import date as _date
    from decimal import InvalidOperation

    errores = []

    es_factura = compra.tipo_comprobante == "FA"
    usa_cf = es_factura and datos.get("usa_credito_fiscal") == "1"
    incluye = datos.get("precios_incluyen_igv") == "1"

    _, _, total = calcular_importes(compra, usa_cf, incluye)

    forma_pago = datos.get("forma_pago", "")

    if forma_pago not in CompraMercaderia.FormaPago.values:
        errores.append("Seleccione una forma de pago válida.")

    if forma_pago in ("EFECTIVO", "BANCO"):
        monto_pagado = total
    elif forma_pago == "PARCIAL":
        try:
            monto_pagado = Decimal(
                (datos.get("monto_pagado") or "").replace(",", ".")
            )
        except (InvalidOperation, ValueError):
            monto_pagado = CERO
            errores.append("El monto pagado no es válido.")
    else:
        monto_pagado = CERO

    def fecha(texto, etiqueta):
        if not texto:
            return None
        try:
            return _date.fromisoformat(texto)
        except ValueError:
            errores.append(f"La {etiqueta} no es válida.")
            return None

    fecha_pago = None
    cuenta_pago = None

    if forma_pago in ("EFECTIVO", "BANCO", "PARCIAL"):
        fecha_pago = fecha(datos.get("fecha_pago"), "fecha de pago")
        if datos.get("cuenta_pago"):
            cuenta_pago = cuentas_caja_banco().filter(
                id=datos["cuenta_pago"]
            ).first()

    fecha_vencimiento = None
    cuenta_proveedor = None

    if forma_pago in ("CREDITO", "PARCIAL"):
        fecha_vencimiento = fecha(
            datos.get("fecha_vencimiento"), "fecha de vencimiento"
        )
        if datos.get("cuenta_proveedor"):
            cuenta_proveedor = cuentas_proveedores().filter(
                id=datos["cuenta_proveedor"]
            ).first()

    if condicion is None:
        condicion = (
            CompraMercaderia.objects.filter(compra=compra).first()
            or CompraMercaderia(compra=compra)
        )

    condicion.usa_credito_fiscal = usa_cf
    condicion.precios_incluyen_igv = incluye
    condicion.forma_pago = forma_pago
    condicion.monto_pagado = monto_pagado
    condicion.fecha_pago = fecha_pago
    condicion.cuenta_pago = cuenta_pago
    condicion.cuenta_proveedor = cuenta_proveedor
    condicion.fecha_vencimiento = fecha_vencimiento
    condicion.observacion = datos.get("observacion", "")
    condicion.total_comprobante = total

    if not errores:
        try:
            condicion.full_clean()
        except ValidationError as error:
            if hasattr(error, "message_dict"):
                for mensajes in error.message_dict.values():
                    errores.extend(mensajes)
            else:
                errores.extend(error.messages)

    return condicion, errores
