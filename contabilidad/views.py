from django.shortcuts import render

from .models import (
    AsientoContable,
    PeriodoContable,
    CuentaContable,
    DetalleAsiento,
    PropuestaCostoVenta,
    DetallePropuestaCostoVenta,
    CompraDirectaVenta,
    ServicioTerceroVenta,
    PagoProveedor,
    OperacionContable,
    ConceptoOperacion,
    PagoOperacionContable,
    NotaCredito,
    DetalleNotaCredito,
    
)

from .services import generar_cierre_anual
from django.core.exceptions import ValidationError
from django.db.models import Sum, Q
from django.db.models.functions import Coalesce
from django.db.models import DecimalField, Value
from decimal import Decimal
from django.utils import timezone
from datetime import date
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from .services import contabilizar_costo_venta
from django.shortcuts import get_object_or_404, redirect, render
from django.db import transaction
from .services import contabilizar_pago_proveedor
from .services import contabilizar_pago_operacion_contable
from .services import contabilizar_nota_credito

from django.urls import reverse
from .services import contabilizar_operacion_contable

def libro_diario(request):

    periodo_id = request.GET.get("periodo")
    fecha_desde = request.GET.get("fecha_desde")
    fecha_hasta = request.GET.get("fecha_hasta")

    asientos = (
        AsientoContable.objects
        .filter(
            estado=AsientoContable.Estado.CONTABILIZADO
        )
        .select_related("periodo")
        .prefetch_related(
            "detalles__cuenta",
            "detalles__categoria_gerencial",
            "detalles__centro_costo",
        )
        .order_by(
            "fecha",
            "numero",
        )
    )

    if periodo_id:
        asientos = asientos.filter(
            periodo_id=periodo_id
        )

    if fecha_desde:
        asientos = asientos.filter(
            fecha__gte=fecha_desde
        )

    if fecha_hasta:
        asientos = asientos.filter(
            fecha__lte=fecha_hasta
        )

    periodos = PeriodoContable.objects.all()

    total_debe = sum(
        asiento.total_debe
        for asiento in asientos
    )

    total_haber = sum(
        asiento.total_haber
        for asiento in asientos
    )

    context = {
        "asientos": asientos,
        "periodos": periodos,
        "periodo_id": periodo_id,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "total_debe": total_debe,
        "total_haber": total_haber,
    }

    return render(
        request,
        "contabilidad/libro_diario.html",
        context,
    )



def libro_mayor(request):

    cuenta_id = request.GET.get("cuenta")
    periodo_id = request.GET.get("periodo")
    fecha_desde = request.GET.get("fecha_desde")
    fecha_hasta = request.GET.get("fecha_hasta")

    cuentas = (
        CuentaContable.objects
        .filter(
            activo=True,
            acepta_movimientos=True,
        )
        .order_by("codigo")
    )

    periodos = PeriodoContable.objects.all()

    movimientos = DetalleAsiento.objects.none()

    cuenta_seleccionada = None

    total_debe = Decimal("0.00")
    total_haber = Decimal("0.00")
    saldo_final = Decimal("0.00")

    if cuenta_id:

        cuenta_seleccionada = CuentaContable.objects.get(
            id=cuenta_id
        )

        movimientos = (
            DetalleAsiento.objects
            .filter(
                cuenta=cuenta_seleccionada,
                asiento__estado=(
                    AsientoContable.Estado.CONTABILIZADO
                ),
            )
            .select_related(
                "asiento",
                "asiento__periodo",
                "categoria_gerencial",
                "centro_costo",
            )
            .order_by(
                "asiento__fecha",
                "asiento__numero",
                "secuencia",
            )
        )

        if periodo_id:
            movimientos = movimientos.filter(
                asiento__periodo_id=periodo_id
            )

        if fecha_desde:
            movimientos = movimientos.filter(
                asiento__fecha__gte=fecha_desde
            )

        if fecha_hasta:
            movimientos = movimientos.filter(
                asiento__fecha__lte=fecha_hasta
            )

        movimientos_con_saldo = []

        saldo = Decimal("0.00")

        for movimiento in movimientos:

            total_debe += movimiento.debe
            total_haber += movimiento.haber

            if cuenta_seleccionada.naturaleza == "DEUDORA":
                saldo += movimiento.debe
                saldo -= movimiento.haber
            else:
                saldo += movimiento.haber
                saldo -= movimiento.debe

            movimientos_con_saldo.append(
                {
                    "movimiento": movimiento,
                    "saldo": saldo,
                }
            )

        saldo_final = saldo

    else:
        movimientos_con_saldo = []

    context = {
        "cuentas": cuentas,
        "periodos": periodos,
        "cuenta_id": cuenta_id,
        "cuenta_seleccionada": cuenta_seleccionada,
        "periodo_id": periodo_id,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "movimientos_con_saldo": movimientos_con_saldo,
        "total_debe": total_debe,
        "total_haber": total_haber,
        "saldo_final": saldo_final,
    }

    return render(
        request,
        "contabilidad/libro_mayor.html",
        context,
    )




def balance_comprobacion(request):

    periodo_id = request.GET.get("periodo")
    fecha_desde = request.GET.get("fecha_desde")
    fecha_hasta = request.GET.get("fecha_hasta")

    periodos = PeriodoContable.objects.all()

    movimientos = DetalleAsiento.objects.filter(
        asiento__estado=AsientoContable.Estado.CONTABILIZADO
    )

    if periodo_id:
        movimientos = movimientos.filter(
            asiento__periodo_id=periodo_id
        )

    if fecha_desde:
        movimientos = movimientos.filter(
            asiento__fecha__gte=fecha_desde
        )

    if fecha_hasta:
        movimientos = movimientos.filter(
            asiento__fecha__lte=fecha_hasta
        )

    cero = Value(
        Decimal("0.00"),
        output_field=DecimalField(
            max_digits=15,
            decimal_places=2,
        ),
    )

    cuentas = (
        movimientos
        .values(
            "cuenta_id",
            "cuenta__codigo",
            "cuenta__nombre",
            "cuenta__tipo",
        )
        .annotate(
            total_debe=Coalesce(
                Sum("debe"),
                cero,
            ),
            total_haber=Coalesce(
                Sum("haber"),
                cero,
            ),
        )
        .order_by("cuenta__codigo")
    )

    filas = []

    total_debe = Decimal("0.00")
    total_haber = Decimal("0.00")
    total_saldo_deudor = Decimal("0.00")
    total_saldo_acreedor = Decimal("0.00")

    for cuenta in cuentas:

        debe = cuenta["total_debe"]
        haber = cuenta["total_haber"]

        diferencia = debe - haber

        if diferencia > 0:
            saldo_deudor = diferencia
            saldo_acreedor = Decimal("0.00")

        elif diferencia < 0:
            saldo_deudor = Decimal("0.00")
            saldo_acreedor = abs(diferencia)

        else:
            saldo_deudor = Decimal("0.00")
            saldo_acreedor = Decimal("0.00")

        filas.append({
            "codigo": cuenta["cuenta__codigo"],
            "nombre": cuenta["cuenta__nombre"],
            "tipo": cuenta["cuenta__tipo"],
            "debe": debe,
            "haber": haber,
            "saldo_deudor": saldo_deudor,
            "saldo_acreedor": saldo_acreedor,
        })

        total_debe += debe
        total_haber += haber
        total_saldo_deudor += saldo_deudor
        total_saldo_acreedor += saldo_acreedor

    context = {
        "filas": filas,
        "periodos": periodos,
        "periodo_id": periodo_id,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,

        "total_debe": total_debe,
        "total_haber": total_haber,

        "total_saldo_deudor": total_saldo_deudor,
        "total_saldo_acreedor": total_saldo_acreedor,

        "cuadrado": total_debe == total_haber,

        "saldos_cuadrados": (
            total_saldo_deudor ==
            total_saldo_acreedor
        ),
    }

    return render(
        request,
        "contabilidad/balance_comprobacion.html",
        context,
    )

def estado_resultados(request):

    periodo_id = request.GET.get("periodo")
    fecha_desde = request.GET.get("fecha_desde")
    fecha_hasta = request.GET.get("fecha_hasta")

    periodos = PeriodoContable.objects.all()

    movimientos = (
        DetalleAsiento.objects
        .filter(
            asiento__estado=AsientoContable.Estado.CONTABILIZADO
        )
        .select_related(
            "cuenta",
            "categoria_gerencial",
            "centro_costo",
            "asiento",
        )
    )

    if periodo_id:
        movimientos = movimientos.filter(
            asiento__periodo_id=periodo_id
        )

    if fecha_desde:
        movimientos = movimientos.filter(
            asiento__fecha__gte=fecha_desde
        )

    if fecha_hasta:
        movimientos = movimientos.filter(
            asiento__fecha__lte=fecha_hasta
        )

    # ========================================================
    # FUNCIÓN AUXILIAR
    # ========================================================

    def saldo_movimientos(queryset):

        total = Decimal("0.00")

        for mov in queryset:

            if mov.cuenta.naturaleza == "ACREEDORA":
                total += mov.haber - mov.debe
            else:
                total += mov.debe - mov.haber

        return total

    # ========================================================
    # INGRESOS OPERACIONALES
    # ========================================================

    ingresos_operacionales_qs = movimientos.filter(
        cuenta__tipo="INGRESO",
        cuenta__codigo__startswith="70",
    )

    ingresos_operacionales = saldo_movimientos(
        ingresos_operacionales_qs
    )

    # ========================================================
    # COSTO DE VENTAS Y SERVICIOS
    # ========================================================

    # --------------------------------------------------------
    # 1. COSTO DE MERCADERÍA VENDIDA
    # --------------------------------------------------------

    costo_mercaderia_qs = movimientos.filter(
        cuenta__tipo="COSTO"
    )

    costo_mercaderia = saldo_movimientos(
        costo_mercaderia_qs
    )

    # --------------------------------------------------------
    # 2. SERVICIOS DIRECTOS TERCERIZADOS
    # --------------------------------------------------------

    servicios_directos_qs = movimientos.filter(
        categoria_gerencial__codigo__startswith="91"
    )

    servicios_directos = saldo_movimientos(
        servicios_directos_qs
    )

    # --------------------------------------------------------
    # 3. DESGLOSE DE SERVICIOS DIRECTOS
    # --------------------------------------------------------

    biselado_externo = saldo_movimientos(
        servicios_directos_qs.filter(
            categoria_gerencial__codigo="91301"
        )
    )

    coloreado_externo = saldo_movimientos(
        servicios_directos_qs.filter(
            categoria_gerencial__codigo="91302"
        )
    )

    soldadura_externa = saldo_movimientos(
        servicios_directos_qs.filter(
            categoria_gerencial__codigo="91303"
        )
    )

    cambio_flex_externo = saldo_movimientos(
        servicios_directos_qs.filter(
            categoria_gerencial__codigo="91304"
        )
    )

    medida_vista_tercerizada = saldo_movimientos(
        servicios_directos_qs.filter(
            categoria_gerencial__codigo="91305"
        )
    )

    otros_servicios_directos = (
        servicios_directos
        - biselado_externo
        - coloreado_externo
        - soldadura_externa
        - cambio_flex_externo
        - medida_vista_tercerizada
    )

    # --------------------------------------------------------
    # 4. TOTAL COSTO DE VENTAS Y SERVICIOS
    # --------------------------------------------------------

    costo_ventas = (
        costo_mercaderia
        + servicios_directos
    )

    utilidad_bruta = (
        ingresos_operacionales
        - costo_ventas
    )
    # ========================================================
    # GASTOS ADMINISTRATIVOS
    # ========================================================

    gastos_administrativos_qs = movimientos.filter(
        categoria_gerencial__codigo__startswith="92"
    )

    gastos_administrativos = saldo_movimientos(
        gastos_administrativos_qs
    )

    # ========================================================
    # GASTOS COMERCIALES
    # ========================================================

    gastos_comerciales_qs = movimientos.filter(
        categoria_gerencial__codigo__startswith="93"
    )

    gastos_comerciales = saldo_movimientos(
        gastos_comerciales_qs
    )

    utilidad_operativa = (
        utilidad_bruta
        - gastos_administrativos
        - gastos_comerciales
    )

    # ========================================================
    # INGRESOS FINANCIEROS
    # ========================================================

    ingresos_financieros_qs = movimientos.filter(
        cuenta__codigo__startswith="77"
    )

    ingresos_financieros = saldo_movimientos(
        ingresos_financieros_qs
    )

    # ========================================================
    # GASTOS FINANCIEROS
    # ========================================================

    gastos_financieros_qs = movimientos.filter(
        cuenta__codigo__startswith="67"
    )

    gastos_financieros = saldo_movimientos(
        gastos_financieros_qs
    )

    resultado_antes_impuestos = (
        utilidad_operativa
        + ingresos_financieros
        - gastos_financieros
    )

    # ========================================================
    # IMPUESTO A LA RENTA
    # ========================================================
    #
    # Por ahora lo dejamos en cero.
    # Después crearemos una cuenta específica de gasto
    # por impuesto a la renta.
    #

    impuesto_renta = Decimal("0.00")

    utilidad_neta = (
        resultado_antes_impuestos
        - impuesto_renta
    )

    context = {
        "periodos": periodos,
        "periodo_id": periodo_id,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,

        "ingresos_operacionales": ingresos_operacionales,
        "costo_ventas": costo_ventas,
        "utilidad_bruta": utilidad_bruta,

        "gastos_administrativos": gastos_administrativos,
        "gastos_comerciales": gastos_comerciales,
        "utilidad_operativa": utilidad_operativa,

        "ingresos_financieros": ingresos_financieros,
        "gastos_financieros": gastos_financieros,

        "resultado_antes_impuestos": resultado_antes_impuestos,
        "impuesto_renta": impuesto_renta,
        "utilidad_neta": utilidad_neta,

        "costo_mercaderia": costo_mercaderia,
        "servicios_directos": servicios_directos,

        "biselado_externo": biselado_externo,
        "coloreado_externo": coloreado_externo,
        "soldadura_externa": soldadura_externa,
        "cambio_flex_externo": cambio_flex_externo,
        "medida_vista_tercerizada": medida_vista_tercerizada,
        "otros_servicios_directos": otros_servicios_directos,
    }

    return render(
        request,
        "contabilidad/estado_resultados.html",
        context,
    )


def validar_costo_venta(request, propuesta_id):

    propuesta = get_object_or_404(
        PropuestaCostoVenta.objects
        .select_related(
            "ticket",
            "ticket__cliente",
        )
        .prefetch_related(
            "detalles__producto",
            "detalles__detalle_ticket",
            "servicios_terceros",
        ),
        id=propuesta_id,
    )

    # ========================================================
    # 1. VALIDAR / ACTUALIZAR COSTOS DE MERCADERÍA
    # ========================================================

    if request.method == "POST":

        errores = False

        for detalle in propuesta.detalles.all():

            campo = f"costo_{detalle.id}"

            valor = request.POST.get(
                campo,
                "",
            ).strip()

            # ------------------------------------------------
            # SI EL CAMPO ESTÁ VACÍO
            # ------------------------------------------------

            if valor == "":

                if detalle.costo_unitario is None:
                    errores = True

                continue

            # ------------------------------------------------
            # CONVERTIR COSTO
            # ------------------------------------------------

            try:

                costo = Decimal(
                    valor.replace(",", ".")
                )

                if costo < 0:
                    raise ValueError

            except (
                ValueError,
                ArithmeticError,
            ):

                errores = True
                continue

            # ------------------------------------------------
            # SI EL USUARIO CAMBIÓ EL COSTO,
            # EL ORIGEN PASA A MANUAL
            # ------------------------------------------------

            if detalle.costo_unitario != costo:

                detalle.costo_unitario = costo

                detalle.origen_costo = (
                    DetallePropuestaCostoVenta
                    .OrigenCosto
                    .MANUAL
                )

            detalle.validado = True

            detalle.save(
                update_fields=[
                    "costo_unitario",
                    "origen_costo",
                    "validado",
                ]
            )

        # ====================================================
        # 2. SI EXISTEN ERRORES
        # ====================================================

        if errores:

            messages.error(
                request,
                (
                    "Debe completar correctamente todos "
                    "los costos pendientes."
                ),
            )

        # ====================================================
        # 3. SI TODO ESTÁ CORRECTO
        # ====================================================

        else:

            # Las líneas que ya tenían costo automático
            # también quedan validadas.
            propuesta.detalles.filter(
                costo_unitario__isnull=False
            ).update(
                validado=True
            )

            propuesta.estado = (
                PropuestaCostoVenta
                .Estado
                .VALIDADA
            )

            propuesta.validado_en = (
                timezone.now()
            )

            propuesta.save(
                update_fields=[
                    "estado",
                    "validado_en",
                ]
            )

            messages.success(
                request,
                (
                    "Costo de venta validado "
                    "correctamente."
                ),
            )

            return redirect(
                "contabilidad:validar_costo_venta",
                propuesta_id=propuesta.id,
            )

    # ========================================================
    # 4. TOTAL DE SERVICIOS DE TERCEROS
    # ========================================================
    #
    # Solo sumamos los servicios que realmente fueron
    # confirmados o ya contabilizados.
    #
    # Los servicios simplemente PROPUESTOS con S/ 0.00
    # no forman parte del costo real de la venta.
    # ========================================================

    total_servicios_terceros = (
        propuesta.servicios_terceros
        .filter(
            estado__in=[
                ServicioTerceroVenta
                .Estado
                .CONFIRMADO,

                ServicioTerceroVenta
                .Estado
                .CONTABILIZADO,
            ]
        )
        .aggregate(
            total=Coalesce(
                Sum("costo"),
                Decimal("0.00"),
            )
        )["total"]
    )

    # ========================================================
    # 5. COSTO TOTAL ASOCIADO A LA VENTA
    # ========================================================

    costo_total_asociado = (
        propuesta.costo_total
        + total_servicios_terceros
    )

    # ========================================================
    # 6. CONTEXTO
    # ========================================================

    context = {
        "propuesta": propuesta,

        "total_servicios_terceros":
            total_servicios_terceros,

        "costo_total_asociado":
            costo_total_asociado,
    }

    # ========================================================
    # 7. RENDER
    # ========================================================

    return render(
        request,
        "contabilidad/validar_costo_venta.html",
        context,
    )

def registrar_compra_directa(request, detalle_costo_id):

    detalle_costo = get_object_or_404(
        DetallePropuestaCostoVenta.objects.select_related(
            "propuesta__ticket",
            "detalle_ticket",
            "producto",
        ),
        id=detalle_costo_id,
    )

    # ========================================================
    # 1. BUSCAR COMPRA EXISTENTE
    # ========================================================

    compra_existente = (
        CompraDirectaVenta.objects
        .filter(
            detalle_costo=detalle_costo
        )
        .select_related(
            "cuenta_pago",
            "cuenta_proveedor",
        )
        .first()
    )

    # ========================================================
    # 2. NO MODIFICAR SI YA ESTÁ CONTABILIZADA
    # ========================================================

    if (
        compra_existente
        and compra_existente.estado
        == CompraDirectaVenta.Estado.CONTABILIZADA
    ):

        messages.warning(
            request,
            "La compra directa ya se encuentra contabilizada "
            "y no puede modificarse desde esta pantalla."
        )

        return redirect(
            "contabilidad:validar_costo_venta",
            propuesta_id=detalle_costo.propuesta.id,
        )

    # ========================================================
    # 3. CUENTAS DE PAGO
    # ========================================================

    cuentas_pago = (
        CuentaContable.objects
        .filter(
            codigo__in=[
                "10101",
                "10401",
                "10402",
            ],
            activo=True,
            acepta_movimientos=True,
        )
        .order_by("codigo")
    )

    # ========================================================
    # 4. CUENTAS POR PAGAR
    # ========================================================

    cuentas_proveedor = (
        CuentaContable.objects
        .filter(
            codigo__startswith="42",
            activo=True,
            acepta_movimientos=True,
        )
        .order_by("codigo")
    )

    # ========================================================
    # 5. OBJETO DE TRABAJO
    # ========================================================

    if compra_existente:

        compra = compra_existente

    else:

        compra = CompraDirectaVenta(
            detalle_costo=detalle_costo,
            cantidad=detalle_costo.cantidad,
        )

    # ========================================================
    # 6. POST
    # ========================================================

    if request.method == "POST":

        errores = []

        # ----------------------------------------------------
        # COSTO UNITARIO
        # ----------------------------------------------------

        costo_unitario_txt = (
            request.POST
            .get("costo_unitario", "")
            .strip()
        )

        costo_unitario = None

        if not costo_unitario_txt:

            errores.append(
                "Debe ingresar el costo unitario."
            )

        else:

            try:

                costo_unitario = Decimal(
                    costo_unitario_txt.replace(",", ".")
                )

                if costo_unitario <= 0:
                    errores.append(
                        "El costo unitario debe ser mayor que cero."
                    )

            except Exception:

                errores.append(
                    "El costo unitario ingresado no es válido."
                )

        # ----------------------------------------------------
        # DATOS GENERALES
        # ----------------------------------------------------

        proveedor_nombre = (
            request.POST
            .get("proveedor_nombre", "")
            .strip()
        )

        fecha_compra_txt = (
            request.POST
            .get("fecha_compra", "")
            .strip()
        )

        tipo_documento = (
            request.POST
            .get("tipo_documento", "")
            .strip()
        )

        numero_documento = (
            request.POST
            .get("numero_documento", "")
            .strip()
        )

        forma_pago = (
            request.POST
            .get("forma_pago", "")
            .strip()
        )

        monto_pagado_txt = (
            request.POST
            .get("monto_pagado", "")
            .strip()
        )

        fecha_pago_txt = (
            request.POST
            .get("fecha_pago", "")
            .strip()
        )

        fecha_vencimiento_txt = (
            request.POST
            .get("fecha_vencimiento", "")
            .strip()
        )

        cuenta_pago_id = (
            request.POST
            .get("cuenta_pago", "")
            .strip()
        )

        cuenta_proveedor_id = (
            request.POST
            .get("cuenta_proveedor", "")
            .strip()
        )

        observacion = (
            request.POST
            .get("observacion", "")
            .strip()
        )

        # ====================================================
        # FECHA DE COMPRA
        # ====================================================

        fecha_compra = None

        if not fecha_compra_txt:

            errores.append(
                "Debe ingresar la fecha de compra."
            )

        else:

            try:

                fecha_compra = date.fromisoformat(
                    fecha_compra_txt
                )

            except ValueError:

                errores.append(
                    "La fecha de compra no es válida."
                )

        # ====================================================
        # MONTO PAGADO
        # ====================================================

        monto_pagado = None

        try:

            monto_pagado = Decimal(
                monto_pagado_txt or "0.00"
            )

        except Exception:

            errores.append(
                "El monto pagado ingresado no es válido."
            )

        # ====================================================
        # FORMA DE PAGO
        # ====================================================

        formas_validas = {
            valor
            for valor, etiqueta
            in CompraDirectaVenta.FormaPago.choices
        }

        if forma_pago not in formas_validas:

            errores.append(
                "Debe seleccionar una forma de pago válida."
            )

        # ====================================================
        # FECHA DE PAGO
        # ====================================================

        fecha_pago = None

        if fecha_pago_txt:

            try:

                fecha_pago = date.fromisoformat(
                    fecha_pago_txt
                )

            except ValueError:

                errores.append(
                    "La fecha de pago no es válida."
                )

        # ====================================================
        # FECHA DE VENCIMIENTO
        # ====================================================

        fecha_vencimiento = None

        if fecha_vencimiento_txt:

            try:

                fecha_vencimiento = date.fromisoformat(
                    fecha_vencimiento_txt
                )

            except ValueError:

                errores.append(
                    "La fecha de vencimiento no es válida."
                )

        # ====================================================
        # CUENTA DE PAGO
        # ====================================================

        cuenta_pago = None

        if cuenta_pago_id:

            cuenta_pago = (
                CuentaContable.objects
                .filter(
                    id=cuenta_pago_id,
                    activo=True,
                    acepta_movimientos=True,
                    codigo__in=[
                        "10101",
                        "10401",
                        "10402",
                    ],
                )
                .first()
            )

            if not cuenta_pago:

                errores.append(
                    "La cuenta de pago seleccionada "
                    "no es válida."
                )

        # ====================================================
        # CUENTA DE PROVEEDOR
        # ====================================================

        cuenta_proveedor = None

        if cuenta_proveedor_id:

            cuenta_proveedor = (
                CuentaContable.objects
                .filter(
                    id=cuenta_proveedor_id,
                    activo=True,
                    acepta_movimientos=True,
                    codigo__startswith="42",
                )
                .first()
            )

            if not cuenta_proveedor:

                errores.append(
                    "La cuenta por pagar seleccionada "
                    "no es válida."
                )

        # ====================================================
        # ASIGNAR VALORES
        # ====================================================

        compra.proveedor_nombre = proveedor_nombre
        compra.fecha_compra = fecha_compra
        compra.tipo_documento = tipo_documento
        compra.numero_documento = numero_documento

        compra.cantidad = detalle_costo.cantidad

        if costo_unitario is not None:
            compra.costo_unitario = costo_unitario

        compra.forma_pago = forma_pago

        compra.monto_pagado = (
            monto_pagado
            if monto_pagado is not None
            else Decimal("0.00")
        )

        compra.fecha_pago = fecha_pago
        compra.fecha_vencimiento = fecha_vencimiento
        compra.cuenta_pago = cuenta_pago
        compra.cuenta_proveedor = cuenta_proveedor
        compra.observacion = observacion

        compra.estado = (
            CompraDirectaVenta.Estado.CONFIRMADA
        )

        compra.confirmado_en = timezone.now()

        # ====================================================
        # VALIDAR Y GUARDAR
        # ====================================================

        if not errores:

            try:

                compra.full_clean()

                with transaction.atomic():

                    compra.save()

                    # ========================================
                    # LA COMPRA DIRECTA DETERMINA EL COSTO
                    # DE LA LÍNEA DE VENTA
                    # ========================================

                    detalle_costo.costo_unitario = (
                        compra.costo_unitario
                    )

                    detalle_costo.origen_costo = (
                        DetallePropuestaCostoVenta
                        .OrigenCosto
                        .MANUAL
                    )

                    detalle_costo.validado = False

                    detalle_costo.save(
                        update_fields=[
                            "costo_unitario",
                            "origen_costo",
                            "validado",
                        ]
                    )

            except ValidationError as error:

                if hasattr(
                    error,
                    "message_dict"
                ):

                    for campo, mensajes_error in (
                        error.message_dict.items()
                    ):

                        for mensaje in mensajes_error:

                            errores.append(
                                mensaje
                            )

                else:

                    for mensaje in error.messages:

                        errores.append(
                            mensaje
                        )

        # ====================================================
        # RESULTADO
        # ====================================================

        if errores:

            for error in errores:

                messages.error(
                    request,
                    error,
                )

        else:

            messages.success(
                request,
                "Compra directa registrada correctamente."
            )

            return redirect(
                "contabilidad:validar_costo_venta",
                propuesta_id=detalle_costo.propuesta.id,
            )

    # ========================================================
    # 7. CONTEXTO
    # ========================================================

    context = {

        "detalle_costo":
            detalle_costo,

        "compra_existente":
            compra,

        "cuentas_pago":
            cuentas_pago,

        "cuentas_proveedor":
            cuentas_proveedor,

        "formas_pago":
            CompraDirectaVenta.FormaPago.choices,
    }

    return render(
        request,
        "contabilidad/registrar_compra_directa.html",
        context,
    )

def registrar_servicio_tercero(request, servicio_id):

    servicio = get_object_or_404(
        ServicioTerceroVenta.objects.select_related(
            "propuesta__ticket"
        ),
        id=servicio_id,
    )

    if request.method == "POST":

        proveedor_nombre = request.POST.get(
            "proveedor_nombre",
            ""
        ).strip()

        fecha_servicio = request.POST.get(
            "fecha_servicio"
        )

        costo_texto = request.POST.get(
            "costo",
            ""
        ).strip()

        forma_pago = request.POST.get(
            "forma_pago",
            ""
        )

        cuenta_pago_id = request.POST.get(
            "cuenta_pago"
        )

        cuenta_proveedor_id = request.POST.get(
            "cuenta_proveedor"
        )

        try:
            costo = Decimal(
                costo_texto.replace(",", ".")
            )

        except Exception:
            messages.error(
                request,
                "El costo ingresado no es válido."
            )

            return redirect(
                "contabilidad:registrar_servicio_tercero",
                servicio_id=servicio.id,
            )

        cuenta_pago = None
        cuenta_proveedor = None

        if cuenta_pago_id:
            cuenta_pago = CuentaContable.objects.get(
                id=cuenta_pago_id
            )

        if cuenta_proveedor_id:
            cuenta_proveedor = CuentaContable.objects.get(
                id=cuenta_proveedor_id
            )

        servicio.proveedor_nombre = proveedor_nombre
        servicio.fecha_servicio = fecha_servicio
        servicio.costo = costo
        servicio.forma_pago = forma_pago
        servicio.cuenta_pago = cuenta_pago
        servicio.cuenta_proveedor = cuenta_proveedor
        servicio.estado = ServicioTerceroVenta.Estado.CONFIRMADO

        try:
            servicio.full_clean()
            servicio.save()

        except ValidationError as error:

            messages.error(
                request,
                " ".join(error.messages)
            )

        else:

            messages.success(
                request,
                "Servicio de tercero registrado correctamente."
            )

            return redirect(
                "contabilidad:validar_costo_venta",
                propuesta_id=servicio.propuesta.id,
            )

    cuentas_pago = (
        CuentaContable.objects
        .filter(
            codigo__in=[
                "10101",
                "10401",
                "10402",
            ],
            activo=True,
        )
        .order_by("codigo")
    )

    cuentas_proveedor = (
        CuentaContable.objects
        .filter(
            codigo="42105",
            activo=True,
        )
    )

    context = {
        "servicio": servicio,
        "cuentas_pago": cuentas_pago,
        "cuentas_proveedor": cuentas_proveedor,
    }

    return render(
        request,
        "contabilidad/registrar_servicio_tercero.html",
        context,
    )


def eliminar_servicio_tercero(request, servicio_id):

    servicio = get_object_or_404(
        ServicioTerceroVenta,
        id=servicio_id,
    )

    propuesta_id = servicio.propuesta_id

    if servicio.estado == ServicioTerceroVenta.Estado.CONTABILIZADO:

        messages.error(
            request,
            "No se puede eliminar un servicio ya contabilizado."
        )

        return redirect(
            "contabilidad:validar_costo_venta",
            propuesta_id=propuesta_id,
        )

    if request.method == "POST":

        descripcion = servicio.descripcion

        servicio.delete()

        messages.success(
            request,
            f"Se eliminó la propuesta: {descripcion}."
        )

    return redirect(
        "contabilidad:validar_costo_venta",
        propuesta_id=propuesta_id,
    )

def contabilizar_propuesta_costo(request, propuesta_id):

    propuesta = get_object_or_404(
        PropuestaCostoVenta.objects.select_related(
            "ticket"
        ),
        id=propuesta_id,
    )

    if request.method != "POST":

        return redirect(
            "contabilidad:validar_costo_venta",
            propuesta_id=propuesta.id,
        )

    if (
        propuesta.estado
        == PropuestaCostoVenta.Estado.CONTABILIZADA
    ):

        messages.warning(
            request,
            "Esta propuesta ya fue contabilizada."
        )

        return redirect(
            "contabilidad:validar_costo_venta",
            propuesta_id=propuesta.id,
        )

    if (
        propuesta.estado
        != PropuestaCostoVenta.Estado.VALIDADA
    ):

        messages.error(
            request,
            "Primero debe validar el costo de venta "
            "antes de contabilizarlo."
        )

        return redirect(
            "contabilidad:validar_costo_venta",
            propuesta_id=propuesta.id,
        )

    try:

        asiento = contabilizar_costo_venta(
            propuesta
        )

    except ValidationError as error:

        messages.error(
            request,
            " ".join(error.messages)
        )

        return redirect(
            "contabilidad:validar_costo_venta",
            propuesta_id=propuesta.id,
        )

    except Exception as error:

        messages.error(
            request,
            (
                "No se pudo contabilizar el costo "
                f"de venta: {error}"
            )
        )

        return redirect(
            "contabilidad:validar_costo_venta",
            propuesta_id=propuesta.id,
        )

    messages.success(
        request,
        (
            "Costo de venta contabilizado correctamente. "
            f"Asiento N.º {asiento.numero}."
        )
    )

    return redirect(
        "contabilidad:validar_costo_venta",
        propuesta_id=propuesta.id,
    )

def balance_general(request):

    fecha_corte_str = request.GET.get("fecha_corte")

    if fecha_corte_str:
        fecha_corte = date.fromisoformat(fecha_corte_str)
    else:
        fecha_corte = timezone.localdate()

    inicio_ejercicio = date(
        fecha_corte.year,
        1,
        1,
    )

    movimientos = (
        DetalleAsiento.objects
        .filter(
            asiento__estado=AsientoContable.Estado.CONTABILIZADO,
            asiento__fecha__lte=fecha_corte,
        )
        .select_related(
            "cuenta",
            "asiento",
        )
    )

    movimientos_resultado = movimientos.filter(
        asiento__fecha__gte=inicio_ejercicio,
        cuenta__tipo__in=[
            "INGRESO",
            "COSTO",
            "GASTO",
        ],
    )    

    # ========================================================
    # 1. FECHA DE CORTE
    # ========================================================

    if fecha_corte:
        movimientos = movimientos.filter(
            asiento__fecha__lte=fecha_corte
        )

    # ========================================================
    # 2. AGRUPAR MOVIMIENTOS POR CUENTA
    # ========================================================

    agrupados = (
        movimientos
        .values(
            "cuenta_id",
            "cuenta__codigo",
            "cuenta__nombre",
            "cuenta__tipo",
            "cuenta__naturaleza",
            "cuenta__clasificacion_balance",
        )
        .annotate(
            total_debe=Sum("debe"),
            total_haber=Sum("haber"),
        )
        .order_by("cuenta__codigo")
    )

    # ========================================================
    # 3. CONTENEDORES DEL BALANCE
    # ========================================================

    activos_corrientes = []
    activos_no_corrientes = []

    pasivos_corrientes = []
    pasivos_no_corrientes = []

    patrimonio = []

    # ========================================================
    # 4. TOTALES
    # ========================================================

    total_activo_corriente = Decimal("0.00")
    total_activo_no_corriente = Decimal("0.00")

    total_pasivo_corriente = Decimal("0.00")
    total_pasivo_no_corriente = Decimal("0.00")

    total_patrimonio_contable = Decimal("0.00")

    # ========================================================
    # 5. CALCULAR SALDOS DE CUENTAS DE BALANCE
    # ========================================================

    for item in agrupados:

        debe = (
            item["total_debe"]
            or Decimal("0.00")
        )

        haber = (
            item["total_haber"]
            or Decimal("0.00")
        )

        naturaleza = item[
            "cuenta__naturaleza"
        ]

        # ----------------------------------------------------
        # SALDO SEGÚN NATURALEZA
        # ----------------------------------------------------

        if naturaleza == "ACREEDORA":

            saldo = (
                haber - debe
            )

        else:

            saldo = (
                debe - haber
            )

        # ----------------------------------------------------
        # DATOS PARA EL TEMPLATE
        # ----------------------------------------------------

        datos = {
            "codigo": item["cuenta__codigo"],
            "nombre": item["cuenta__nombre"],
            "saldo": saldo,
        }

        clasificacion = item[
            "cuenta__clasificacion_balance"
        ]

        # ----------------------------------------------------
        # ACTIVO CORRIENTE
        # ----------------------------------------------------

        if clasificacion == "ACTIVO_CORRIENTE":

            activos_corrientes.append(
                datos
            )

            total_activo_corriente += (
                saldo
            )

        # ----------------------------------------------------
        # ACTIVO NO CORRIENTE
        # ----------------------------------------------------

        elif clasificacion == "ACTIVO_NO_CORRIENTE":

            activos_no_corrientes.append(
                datos
            )

            total_activo_no_corriente += (
                saldo
            )

        # ----------------------------------------------------
        # PASIVO CORRIENTE
        # ----------------------------------------------------

        elif clasificacion == "PASIVO_CORRIENTE":

            pasivos_corrientes.append(
                datos
            )

            total_pasivo_corriente += (
                saldo
            )

        # ----------------------------------------------------
        # PASIVO NO CORRIENTE
        # ----------------------------------------------------

        elif clasificacion == "PASIVO_NO_CORRIENTE":

            pasivos_no_corrientes.append(
                datos
            )

            total_pasivo_no_corriente += (
                saldo
            )

        # ----------------------------------------------------
        # PATRIMONIO
        # ----------------------------------------------------

        elif clasificacion == "PATRIMONIO":

            patrimonio.append(
                datos
            )

            total_patrimonio_contable += (
                saldo
            )

    # ========================================================
    # 6. RESULTADO DEL EJERCICIO
    # ========================================================
    #
    # Mientras no hagamos el asiento formal de cierre:
    #
    # Ingresos
    # -
    # Costos
    # -
    # Gastos
    #
    # forman parte del patrimonio como
    # "Resultado del ejercicio".
    # ========================================================
# ========================================================
# RESULTADO DEL EJERCICIO
# ========================================================

    resultado_ejercicio = Decimal("0.00")

    for mov in movimientos_resultado:

        tipo = mov.cuenta.tipo
        naturaleza = mov.cuenta.naturaleza

        # INGRESOS
        if tipo == "INGRESO":

            if naturaleza == "ACREEDORA":
                resultado_ejercicio += (
                    mov.haber - mov.debe
                )
            else:
                resultado_ejercicio += (
                    mov.debe - mov.haber
                )

        # COSTOS Y GASTOS
        elif tipo in [
            "COSTO",
            "GASTO",
        ]:

            if naturaleza == "DEUDORA":
                resultado_ejercicio -= (
                    mov.debe - mov.haber
                )
            else:
                resultado_ejercicio -= (
                    mov.haber - mov.debe
                )


    # ========================================================
    # 7. TOTAL ACTIVO
    # ========================================================

    total_activo = (
        total_activo_corriente
        + total_activo_no_corriente
    )

    # ========================================================
    # 8. TOTAL PASIVO
    # ========================================================

    total_pasivo = (
        total_pasivo_corriente
        + total_pasivo_no_corriente
    )

    # ========================================================
    # 9. TOTAL PATRIMONIO
    # ========================================================

    total_patrimonio = (
        total_patrimonio_contable
        + resultado_ejercicio
    )

    # ========================================================
    # 10. PASIVO + PATRIMONIO
    # ========================================================

    total_pasivo_patrimonio = (
        total_pasivo
        + total_patrimonio
    )

    # ========================================================
    # 11. COMPROBACIÓN
    # ========================================================

    diferencia = (
        total_activo
        - total_pasivo_patrimonio
    )

    # Evitar pequeñas diferencias decimales visuales

    if abs(diferencia) < Decimal("0.01"):
        diferencia = Decimal("0.00")

    # ========================================================
    # 12. CONTEXTO
    # ========================================================

    context = {

        "fecha_corte":
            fecha_corte,

        # ACTIVOS
        "activos_corrientes":
            activos_corrientes,

        "activos_no_corrientes":
            activos_no_corrientes,

        "total_activo_corriente":
            total_activo_corriente,

        "total_activo_no_corriente":
            total_activo_no_corriente,

        "total_activo":
            total_activo,

        # PASIVOS
        "pasivos_corrientes":
            pasivos_corrientes,

        "pasivos_no_corrientes":
            pasivos_no_corrientes,

        "total_pasivo_corriente":
            total_pasivo_corriente,

        "total_pasivo_no_corriente":
            total_pasivo_no_corriente,

        "total_pasivo":
            total_pasivo,

        # PATRIMONIO
        "patrimonio":
            patrimonio,

        "total_patrimonio_contable":
            total_patrimonio_contable,

        "resultado_ejercicio":
            resultado_ejercicio,

        "total_patrimonio":
            total_patrimonio,

        # COMPROBACIÓN
        "total_pasivo_patrimonio":
            total_pasivo_patrimonio,

        "diferencia":
            diferencia,
    }

    return render(
        request,
        "contabilidad/balance_general.html",
        context,
    )

    fecha_corte = request.GET.get("fecha_corte")

    movimientos = (
        DetalleAsiento.objects
        .filter(
            asiento__estado=AsientoContable.Estado.CONTABILIZADO
        )
        .select_related(
            "cuenta",
            "asiento",
        )
    )

    # ========================================================
    # FECHA DE CORTE
    # ========================================================

    if fecha_corte:
        movimientos = movimientos.filter(
            asiento__fecha__lte=fecha_corte
        )

    # ========================================================
    # FUNCIÓN PARA OBTENER EL SALDO DE UNA CUENTA
    # ========================================================

    def saldo_cuenta(cuenta, debe, haber):

        if cuenta.naturaleza == "ACREEDORA":
            return haber - debe

        return debe - haber

    # ========================================================
    # ACTIVOS, PASIVOS Y PATRIMONIO
    # ========================================================

    activos = {}
    pasivos = {}
    patrimonio = {}

    total_activo = Decimal("0.00")
    total_pasivo = Decimal("0.00")
    total_patrimonio_contable = Decimal("0.00")

    agrupados = (
        movimientos
        .values(
            "cuenta_id",
            "cuenta__codigo",
            "cuenta__nombre",
            "cuenta__tipo",
            "cuenta__naturaleza",
        )
        .annotate(
            total_debe=Sum("debe"),
            total_haber=Sum("haber"),
        )
        .order_by("cuenta__codigo")
    )

    for item in agrupados:

        debe = item["total_debe"] or Decimal("0.00")
        haber = item["total_haber"] or Decimal("0.00")

        if item["cuenta__naturaleza"] == "ACREEDORA":
            saldo = haber - debe
        else:
            saldo = debe - haber

        datos = {
            "codigo": item["cuenta__codigo"],
            "nombre": item["cuenta__nombre"],
            "saldo": saldo,
        }

        tipo = item["cuenta__tipo"]

        if tipo == "ACTIVO":

            activos[item["cuenta_id"]] = datos
            total_activo += saldo

        elif tipo == "PASIVO":

            pasivos[item["cuenta_id"]] = datos
            total_pasivo += saldo

        elif tipo == "PATRIMONIO":

            patrimonio[item["cuenta_id"]] = datos
            total_patrimonio_contable += saldo

    # ========================================================
    # RESULTADO ACUMULADO
    # ========================================================
    #
    # Mientras no exista un asiento formal de cierre,
    # incorporamos ingresos, costos y gastos al patrimonio.
    # ========================================================

    resultado_acumulado = Decimal("0.00")

    for mov in movimientos:

        if mov.cuenta.tipo == "INGRESO":

            if mov.cuenta.naturaleza == "ACREEDORA":
                resultado_acumulado += (
                    mov.haber - mov.debe
                )
            else:
                resultado_acumulado += (
                    mov.debe - mov.haber
                )

        elif mov.cuenta.tipo in ["COSTO", "GASTO"]:

            if mov.cuenta.naturaleza == "DEUDORA":
                resultado_acumulado -= (
                    mov.debe - mov.haber
                )
            else:
                resultado_acumulado -= (
                    mov.haber - mov.debe
                )

    # ========================================================
    # TOTAL PATRIMONIO
    # ========================================================

    total_patrimonio = (
        total_patrimonio_contable
        + resultado_acumulado
    )

    total_pasivo_patrimonio = (
        total_pasivo
        + total_patrimonio
    )

    # ========================================================
    # COMPROBACIÓN
    # ========================================================

    diferencia = (
        total_activo
        - total_pasivo_patrimonio
    )

    context = {
        "fecha_corte": fecha_corte.isoformat(),

        "activos": activos.values(),
        "pasivos": pasivos.values(),
        "patrimonio": patrimonio.values(),

        "total_activo": total_activo,
        "total_pasivo": total_pasivo,

        "total_patrimonio_contable":
            total_patrimonio_contable,

        "resultado_acumulado":
            resultado_acumulado,

        "total_patrimonio":
            total_patrimonio,

        "total_pasivo_patrimonio":
            total_pasivo_patrimonio,

        "diferencia": diferencia,
    }

    return render(
        request,
        "contabilidad/balance_general.html",
        context,
    )

def estado_cambios_patrimonio(request):

    anio_str = request.GET.get("anio")

    if anio_str:
        anio = int(anio_str)
    else:
        anio = timezone.localdate().year

    fecha_inicio = date(anio, 1, 1)
    fecha_fin = date(anio, 12, 31)

    # ========================================================
    # 1. MOVIMIENTOS CONTABILIZADOS
    # ========================================================

    movimientos = (
        DetalleAsiento.objects
        .filter(
            asiento__estado=AsientoContable.Estado.CONTABILIZADO
        )
        .select_related(
            "cuenta",
            "asiento",
        )
    )

    # ========================================================
    # 2. FUNCIÓN AUXILIAR DE SALDO
    # ========================================================

    def saldo_cuenta(queryset, naturaleza):

        total_debe = (
            queryset.aggregate(
                total=Sum("debe")
            )["total"]
            or Decimal("0.00")
        )

        total_haber = (
            queryset.aggregate(
                total=Sum("haber")
            )["total"]
            or Decimal("0.00")
        )

        if naturaleza == "ACREEDORA":
            return total_haber - total_debe

        return total_debe - total_haber

    # ========================================================
    # 3. SALDOS INICIALES
    # ========================================================
    #
    # Todo lo ocurrido antes del 1 de enero del ejercicio.
    # ========================================================

    movimientos_anteriores = movimientos.filter(
        asiento__fecha__lt=fecha_inicio
    )

    capital_inicial = saldo_cuenta(
        movimientos_anteriores.filter(
            cuenta__codigo="50101"
        ),
        "ACREEDORA",
    )

    utilidades_iniciales = saldo_cuenta(
        movimientos_anteriores.filter(
            cuenta__codigo="59101"
        ),
        "ACREEDORA",
    )

    perdidas_iniciales = saldo_cuenta(
        movimientos_anteriores.filter(
            cuenta__codigo="59201"
        ),
        "DEUDORA",
    )

    resultados_acumulados_iniciales = (
        utilidades_iniciales
        - perdidas_iniciales
    )

    # ========================================================
    # 4. MOVIMIENTOS DEL EJERCICIO
    # ========================================================

    movimientos_ejercicio = movimientos.filter(
        asiento__fecha__gte=fecha_inicio,
        asiento__fecha__lte=fecha_fin,
    )

    # --------------------------------------------------------
    # APORTES / REDUCCIONES DE CAPITAL
    # --------------------------------------------------------

    movimientos_capital = movimientos_ejercicio.filter(
        cuenta__codigo="50101"
    )

    aportes_capital = Decimal("0.00")
    reducciones_capital = Decimal("0.00")

    for mov in movimientos_capital:

        if mov.haber > mov.debe:
            aportes_capital += (
                mov.haber - mov.debe
            )

        elif mov.debe > mov.haber:
            reducciones_capital += (
                mov.debe - mov.haber
            )

    # --------------------------------------------------------
    # MOVIMIENTOS DE UTILIDADES ACUMULADAS
    # --------------------------------------------------------

    movimientos_utilidades = movimientos_ejercicio.filter(
        cuenta__codigo="59101"
    )

    aumento_utilidades = Decimal("0.00")
    disminucion_utilidades = Decimal("0.00")

    for mov in movimientos_utilidades:

        if mov.haber > mov.debe:
            aumento_utilidades += (
                mov.haber - mov.debe
            )

        elif mov.debe > mov.haber:
            disminucion_utilidades += (
                mov.debe - mov.haber
            )

    # --------------------------------------------------------
    # MOVIMIENTOS DE PÉRDIDAS ACUMULADAS
    # --------------------------------------------------------

    movimientos_perdidas = movimientos_ejercicio.filter(
        cuenta__codigo="59201"
    )

    aumento_perdidas = Decimal("0.00")
    disminucion_perdidas = Decimal("0.00")

    for mov in movimientos_perdidas:

        if mov.debe > mov.haber:
            aumento_perdidas += (
                mov.debe - mov.haber
            )

        elif mov.haber > mov.debe:
            disminucion_perdidas += (
                mov.haber - mov.debe
            )

    # ========================================================
    # 5. RESULTADO DEL EJERCICIO
    # ========================================================

    resultado_ejercicio = Decimal("0.00")

    movimientos_resultado = movimientos_ejercicio.filter(
        cuenta__tipo__in=[
            "INGRESO",
            "COSTO",
            "GASTO",
        ]
    )

    for mov in movimientos_resultado:

        if mov.cuenta.tipo == "INGRESO":

            if mov.cuenta.naturaleza == "ACREEDORA":
                resultado_ejercicio += (
                    mov.haber - mov.debe
                )
            else:
                resultado_ejercicio += (
                    mov.debe - mov.haber
                )

        elif mov.cuenta.tipo in [
            "COSTO",
            "GASTO",
        ]:

            if mov.cuenta.naturaleza == "DEUDORA":
                resultado_ejercicio -= (
                    mov.debe - mov.haber
                )
            else:
                resultado_ejercicio -= (
                    mov.haber - mov.debe
                )

    # ========================================================
    # 6. DIVIDENDOS / DISTRIBUCIONES
    # ========================================================
    #
    # La cuenta 44120 permite detectar dividendos declarados.
    #
    # Si aún no existen movimientos, será cero.
    # ========================================================

    dividendos_declarados = saldo_cuenta(
        movimientos_ejercicio.filter(
            cuenta__codigo="44120"
        ),
        "ACREEDORA",
    )

    if dividendos_declarados < 0:
        dividendos_declarados = Decimal("0.00")

    # ========================================================
    # 7. SALDOS FINALES
    # ========================================================

    capital_final = (
        capital_inicial
        + aportes_capital
        - reducciones_capital
    )

    resultados_acumulados_finales = (
        resultados_acumulados_iniciales
        + aumento_utilidades
        - disminucion_utilidades
        - aumento_perdidas
        + disminucion_perdidas
    )

    # Mientras no exista el cierre anual,
    # el resultado del ejercicio se mantiene separado.

    total_inicial = (
        capital_inicial
        + resultados_acumulados_iniciales
    )

    total_movimientos = (
        aportes_capital
        - reducciones_capital
        + aumento_utilidades
        - disminucion_utilidades
        - aumento_perdidas
        + disminucion_perdidas
        + resultado_ejercicio
    )

    total_final = (
        capital_final
        + resultados_acumulados_finales
        + resultado_ejercicio
    )

    # ========================================================
    # 8. CONTEXTO
    # ========================================================

    context = {
        "anio": anio,

        "capital_inicial":
            capital_inicial,

        "resultados_acumulados_iniciales":
            resultados_acumulados_iniciales,

        "total_inicial":
            total_inicial,

        "aportes_capital":
            aportes_capital,

        "reducciones_capital":
            reducciones_capital,

        "aumento_utilidades":
            aumento_utilidades,

        "disminucion_utilidades":
            disminucion_utilidades,

        "aumento_perdidas":
            aumento_perdidas,

        "disminucion_perdidas":
            disminucion_perdidas,

        "dividendos_declarados":
            dividendos_declarados,

        "resultado_ejercicio":
            resultado_ejercicio,

        "capital_final":
            capital_final,

        "resultados_acumulados_finales":
            resultados_acumulados_finales,

        "total_movimientos":
            total_movimientos,

        "total_final":
            total_final,
    }

    return render(
        request,
        "contabilidad/estado_cambios_patrimonio.html",
        context,
    )


def estado_flujo_efectivo(request):

    # ========================================================
    # 1. PERÍODO
    # ========================================================

    anio_str = request.GET.get("anio")
    mes_str = request.GET.get("mes")

    if anio_str:
        anio = int(anio_str)
    else:
        anio = timezone.localdate().year

    mes = int(mes_str) if mes_str else 0

    meses_dict = {
        1: "Enero",
        2: "Febrero",
        3: "Marzo",
        4: "Abril",
        5: "Mayo",
        6: "Junio",
        7: "Julio",
        8: "Agosto",
        9: "Septiembre",
        10: "Octubre",
        11: "Noviembre",
        12: "Diciembre",
    }

    meses = [
        (1, "Enero"),
        (2, "Febrero"),
        (3, "Marzo"),
        (4, "Abril"),
        (5, "Mayo"),
        (6, "Junio"),
        (7, "Julio"),
        (8, "Agosto"),
        (9, "Septiembre"),
        (10, "Octubre"),
        (11, "Noviembre"),
        (12, "Diciembre"),
    ]

    # --------------------------------------------------------
    # PERÍODO MENSUAL
    # --------------------------------------------------------

    if mes:

        import calendar

        ultimo_dia = calendar.monthrange(
            anio,
            mes
        )[1]

        fecha_inicio = date(
            anio,
            mes,
            1
        )

        fecha_fin = date(
            anio,
            mes,
            ultimo_dia
        )

        nombre_periodo = (
            f"{meses_dict[mes]} {anio}"
        )

    # --------------------------------------------------------
    # PERÍODO ANUAL
    # --------------------------------------------------------

    else:

        fecha_inicio = date(
            anio,
            1,
            1
        )

        fecha_fin = date(
            anio,
            12,
            31
        )

        nombre_periodo = (
            f"Ejercicio {anio}"
        )

    # ========================================================
    # 2. CUENTAS DE EFECTIVO
    # ========================================================

    cuentas_efectivo = [
        "10101",  # Caja
        "10401",  # Banco principal
    ]

    # ========================================================
    # 3. MOVIMIENTOS CONTABILIZADOS
    # ========================================================

    movimientos = (
        DetalleAsiento.objects
        .filter(
            asiento__estado=(
                AsientoContable
                .Estado
                .CONTABILIZADO
            )
        )
        .select_related(
            "cuenta",
            "asiento",
        )
    )

    # ========================================================
    # 4. SALDO INICIAL
    # ========================================================
    #
    # Todo movimiento de Caja/Banco anterior al inicio
    # del período seleccionado.
    # ========================================================

    saldo_inicial_qs = movimientos.filter(
        cuenta__codigo__in=cuentas_efectivo,
        asiento__fecha__lt=fecha_inicio,
    )

    saldo_inicial = Decimal("0.00")

    for mov in saldo_inicial_qs:

        saldo_inicial += (
            mov.debe
            - mov.haber
        )

    # ========================================================
    # 5. MOVIMIENTOS DE EFECTIVO DEL PERÍODO
    # ========================================================

    movimientos_efectivo = movimientos.filter(
        cuenta__codigo__in=cuentas_efectivo,
        asiento__fecha__gte=fecha_inicio,
        asiento__fecha__lte=fecha_fin,
    )

    # ========================================================
    # 6. ACUMULADORES
    # ========================================================

    # OPERACIÓN

    cobros_clientes = Decimal("0.00")

    pagos_proveedores = Decimal("0.00")

    pagos_gastos_operativos = Decimal("0.00")

    pagos_impuestos = Decimal("0.00")

    otros_operacion_entradas = Decimal("0.00")

    otros_operacion_salidas = Decimal("0.00")

    # INVERSIÓN

    compra_activos_fijos = Decimal("0.00")

    otros_inversion_entradas = Decimal("0.00")

    otros_inversion_salidas = Decimal("0.00")

    # FINANCIAMIENTO

    aportes_capital = Decimal("0.00")

    prestamos_recibidos = Decimal("0.00")

    pago_prestamos = Decimal("0.00")

    dividendos_pagados = Decimal("0.00")

    otros_financiamiento_entradas = Decimal("0.00")

    otros_financiamiento_salidas = Decimal("0.00")

    # ========================================================
    # 7. FUNCIÓN AUXILIAR: CONTRAPARTIDAS
    # ========================================================

    def contrapartidas(
        asiento,
        detalle_efectivo
    ):

        return (
            asiento.detalles
            .exclude(
                id=detalle_efectivo.id
            )
            .select_related(
                "cuenta"
            )
            .all()
        )

    # ========================================================
    # 8. CLASIFICAR CADA MOVIMIENTO DE EFECTIVO
    # ========================================================

    for mov in movimientos_efectivo:

        variacion = (
            mov.debe
            - mov.haber
        )

        # -----------------------------------------------
        # ENTRADA / SALIDA
        # -----------------------------------------------

        if variacion > 0:

            entrada = True

            importe = variacion

        elif variacion < 0:

            entrada = False

            importe = abs(
                variacion
            )

        else:

            continue

        # -----------------------------------------------
        # CONTRAPARTIDAS
        # -----------------------------------------------

        contras = contrapartidas(
            mov.asiento,
            mov,
        )

        clasificado = False

        for contra in contras:

            codigo = (
                contra
                .cuenta
                .codigo
            )

            # =================================================
            # ACTIVIDADES DE OPERACIÓN
            # =================================================

            # CLIENTES

            if codigo.startswith("12"):

                if entrada:

                    cobros_clientes += importe

                else:

                    otros_operacion_salidas += (
                        importe
                    )

                clasificado = True

                break

            # VENTAS

            if codigo.startswith("70"):

                if entrada:

                    cobros_clientes += importe

                else:

                    otros_operacion_salidas += (
                        importe
                    )

                clasificado = True

                break

            # PROVEEDORES

            if codigo.startswith("42"):

                if entrada:

                    otros_operacion_entradas += (
                        importe
                    )

                else:

                    pagos_proveedores += importe

                clasificado = True

                break

            # TRIBUTOS

            if codigo.startswith("40"):

                if entrada:

                    otros_operacion_entradas += (
                        importe
                    )

                else:

                    pagos_impuestos += importe

                clasificado = True

                break

            # GASTOS OPERATIVOS

            if codigo.startswith(
                (
                    "62",
                    "63",
                    "65",
                    "68",
                )
            ):

                if entrada:

                    otros_operacion_entradas += (
                        importe
                    )

                else:

                    pagos_gastos_operativos += (
                        importe
                    )

                clasificado = True

                break

            # COSTOS / INVENTARIOS

            if codigo.startswith(
                (
                    "69",
                    "20",
                )
            ):

                if entrada:

                    otros_operacion_entradas += (
                        importe
                    )

                else:

                    pagos_proveedores += (
                        importe
                    )

                clasificado = True

                break

            # =================================================
            # ACTIVIDADES DE INVERSIÓN
            # =================================================

            if codigo.startswith("33"):

                if entrada:

                    otros_inversion_entradas += (
                        importe
                    )

                else:

                    compra_activos_fijos += (
                        importe
                    )

                clasificado = True

                break

            # =================================================
            # ACTIVIDADES DE FINANCIAMIENTO
            # =================================================

            # CAPITAL

            if codigo.startswith("50"):

                if entrada:

                    aportes_capital += (
                        importe
                    )

                else:

                    otros_financiamiento_salidas += (
                        importe
                    )

                clasificado = True

                break

            # DIVIDENDOS POR PAGAR

            if codigo == "44120":

                if entrada:

                    otros_financiamiento_entradas += (
                        importe
                    )

                else:

                    dividendos_pagados += (
                        importe
                    )

                clasificado = True

                break

            # PRÉSTAMOS / OBLIGACIONES

            if codigo.startswith(
                (
                    "45",
                    "46",
                )
            ):

                if entrada:

                    prestamos_recibidos += (
                        importe
                    )

                else:

                    pago_prestamos += (
                        importe
                    )

                clasificado = True

                break

        # ====================================================
        # SIN CLASIFICAR
        # ====================================================

        if not clasificado:

            if entrada:

                otros_operacion_entradas += (
                    importe
                )

            else:

                otros_operacion_salidas += (
                    importe
                )

    # ========================================================
    # 9. FLUJO NETO DE OPERACIÓN
    # ========================================================

    entradas_operacion = (
        cobros_clientes
        + otros_operacion_entradas
    )

    salidas_operacion = (
        pagos_proveedores
        + pagos_gastos_operativos
        + pagos_impuestos
        + otros_operacion_salidas
    )

    flujo_operacion = (
        entradas_operacion
        - salidas_operacion
    )

    # ========================================================
    # 10. FLUJO NETO DE INVERSIÓN
    # ========================================================

    entradas_inversion = (
        otros_inversion_entradas
    )

    salidas_inversion = (
        compra_activos_fijos
        + otros_inversion_salidas
    )

    flujo_inversion = (
        entradas_inversion
        - salidas_inversion
    )

    # ========================================================
    # 11. FLUJO NETO DE FINANCIAMIENTO
    # ========================================================

    entradas_financiamiento = (
        aportes_capital
        + prestamos_recibidos
        + otros_financiamiento_entradas
    )

    salidas_financiamiento = (
        pago_prestamos
        + dividendos_pagados
        + otros_financiamiento_salidas
    )

    flujo_financiamiento = (
        entradas_financiamiento
        - salidas_financiamiento
    )

    # ========================================================
    # 12. VARIACIÓN NETA
    # ========================================================

    variacion_neta = (
        flujo_operacion
        + flujo_inversion
        + flujo_financiamiento
    )

    # ========================================================
    # 13. SALDO FINAL CALCULADO
    # ========================================================

    saldo_final_calculado = (
        saldo_inicial
        + variacion_neta
    )

    # ========================================================
    # 14. SALDO FINAL CONTABLE
    # ========================================================

    saldo_final_qs = movimientos.filter(
        cuenta__codigo__in=cuentas_efectivo,
        asiento__fecha__lte=fecha_fin,
    )

    saldo_final_contable = Decimal(
        "0.00"
    )

    for mov in saldo_final_qs:

        saldo_final_contable += (
            mov.debe
            - mov.haber
        )

    # ========================================================
    # 15. COMPROBACIÓN
    # ========================================================

    diferencia = (
        saldo_final_contable
        - saldo_final_calculado
    )

    if abs(diferencia) < Decimal("0.01"):

        diferencia = Decimal(
            "0.00"
        )

    # ========================================================
    # 16. CONTEXTO
    # ========================================================

    context = {

        # PERÍODO

        "anio": anio,

        "mes": mes,

        "meses": meses,

        "nombre_periodo":
            nombre_periodo,

        "fecha_inicio":
            fecha_inicio,

        "fecha_fin":
            fecha_fin,

        # SALDO INICIAL

        "saldo_inicial":
            saldo_inicial,

        # OPERACIÓN

        "cobros_clientes":
            cobros_clientes,

        "pagos_proveedores":
            pagos_proveedores,

        "pagos_gastos_operativos":
            pagos_gastos_operativos,

        "pagos_impuestos":
            pagos_impuestos,

        "otros_operacion_entradas":
            otros_operacion_entradas,

        "otros_operacion_salidas":
            otros_operacion_salidas,

        "flujo_operacion":
            flujo_operacion,

        # INVERSIÓN

        "compra_activos_fijos":
            compra_activos_fijos,

        "otros_inversion_entradas":
            otros_inversion_entradas,

        "otros_inversion_salidas":
            otros_inversion_salidas,

        "flujo_inversion":
            flujo_inversion,

        # FINANCIAMIENTO

        "aportes_capital":
            aportes_capital,

        "prestamos_recibidos":
            prestamos_recibidos,

        "pago_prestamos":
            pago_prestamos,

        "dividendos_pagados":
            dividendos_pagados,

        "otros_financiamiento_entradas":
            otros_financiamiento_entradas,

        "otros_financiamiento_salidas":
            otros_financiamiento_salidas,

        "flujo_financiamiento":
            flujo_financiamiento,

        # CONCILIACIÓN

        "variacion_neta":
            variacion_neta,

        "saldo_final_calculado":
            saldo_final_calculado,

        "saldo_final_contable":
            saldo_final_contable,

        "diferencia":
            diferencia,
    }

    return render(
        request,
        "contabilidad/estado_flujo_efectivo.html",
        context,
    )

def estados_financieros(request):

    anio_str = request.GET.get("anio")

    if anio_str:
        anio = int(anio_str)
    else:
        anio = timezone.localdate().year

    fecha_inicio = date(anio, 1, 1)
    fecha_fin = date(anio, 12, 31)

    movimientos = (
        DetalleAsiento.objects
        .filter(
            asiento__estado=AsientoContable.Estado.CONTABILIZADO,
            asiento__fecha__gte=fecha_inicio,
            asiento__fecha__lte=fecha_fin,
        )
        .select_related(
            "cuenta",
            "asiento",
        )
    )

    # ========================================================
    # FUNCIÓN AUXILIAR
    # ========================================================

    def saldo_movimientos(queryset):

        total = Decimal("0.00")

        for mov in queryset:

            if mov.cuenta.naturaleza == "ACREEDORA":
                total += mov.haber - mov.debe
            else:
                total += mov.debe - mov.haber

        return total

    # ========================================================
    # INGRESOS
    # ========================================================

    ingresos = saldo_movimientos(
        movimientos.filter(
            cuenta__tipo="INGRESO"
        )
    )

    # ========================================================
    # COSTOS Y GASTOS
    # ========================================================

    costos = saldo_movimientos(
        movimientos.filter(
            cuenta__tipo="COSTO"
        )
    )

    gastos = saldo_movimientos(
        movimientos.filter(
            cuenta__tipo="GASTO"
        )
    )

    utilidad_neta = (
        ingresos
        - costos
        - gastos
    )

    # ========================================================
    # SALDOS DE BALANCE
    # ========================================================

    movimientos_balance = (
        DetalleAsiento.objects
        .filter(
            asiento__estado=AsientoContable.Estado.CONTABILIZADO,
            asiento__fecha__lte=fecha_fin,
        )
        .select_related(
            "cuenta",
            "asiento",
        )
    )

    total_activo = Decimal("0.00")
    total_pasivo = Decimal("0.00")
    patrimonio_contable = Decimal("0.00")

    for mov in movimientos_balance:

        tipo = mov.cuenta.tipo
        naturaleza = mov.cuenta.naturaleza

        if naturaleza == "ACREEDORA":
            saldo = mov.haber - mov.debe
        else:
            saldo = mov.debe - mov.haber

        if tipo == "ACTIVO":
            total_activo += saldo

        elif tipo == "PASIVO":
            total_pasivo += saldo

        elif tipo == "PATRIMONIO":
            patrimonio_contable += saldo

    total_patrimonio = (
        patrimonio_contable
        + utilidad_neta
    )

    # ========================================================
    # EFECTIVO
    # ========================================================

    efectivo = Decimal("0.00")

    for mov in movimientos_balance.filter(
        cuenta__codigo__in=[
            "10101",
            "10401",
        ]
    ):

        efectivo += (
            mov.debe
            - mov.haber
        )

    # ========================================================
    # CONTEXTO
    # ========================================================

    context = {
        "anio": anio,

        "ingresos": ingresos,
        "utilidad_neta": utilidad_neta,

        "total_activo": total_activo,
        "total_pasivo": total_pasivo,
        "total_patrimonio": total_patrimonio,

        "efectivo": efectivo,
    }

    return render(
        request,
        "contabilidad/estados_financieros.html",
        context,
    )


def cerrar_periodo_contable(request, periodo_id):

    periodo = get_object_or_404(
        PeriodoContable,
        id=periodo_id,
    )

    # ========================================================
    # ASIENTOS DEL PERIODO
    # ========================================================

    asientos_periodo = (
        AsientoContable.objects
        .filter(periodo=periodo)
        .exclude(
            estado=AsientoContable.Estado.ANULADO
        )
    )

    asientos_borrador = (
        asientos_periodo
        .filter(
            estado=AsientoContable.Estado.BORRADOR
        )
    )

    asientos_descuadrados = []

    for asiento in asientos_periodo:

        if not asiento.esta_cuadrado:
            asientos_descuadrados.append(
                asiento
            )

    # ========================================================
    # PROPUESTAS DE COSTO PENDIENTES
    # ========================================================

    propuestas_pendientes = (
        PropuestaCostoVenta.objects
        .filter(
            ticket__fecha_emision__gte=periodo.fecha_inicio,
            ticket__fecha_emision__lte=periodo.fecha_fin,
        )
        .exclude(
            estado=PropuestaCostoVenta.Estado.CONTABILIZADA
        )
        .select_related(
            "ticket",
        )
    )

    # ========================================================
    # COMPRAS DIRECTAS PENDIENTES
    # ========================================================

    compras_directas_pendientes = (
        CompraDirectaVenta.objects
        .filter(
            fecha_compra__gte=periodo.fecha_inicio,
            fecha_compra__lte=periodo.fecha_fin,
        )
        .exclude(
            estado=CompraDirectaVenta.Estado.CONTABILIZADA
        )
    )

    # ========================================================
    # PAGOS A PROVEEDORES REGISTRADOS NO CONTABILIZADOS
    # ========================================================

    pagos_proveedor_pendientes = (
        PagoProveedor.objects
        .filter(
            fecha_pago__gte=periodo.fecha_inicio,
            fecha_pago__lte=periodo.fecha_fin,
            estado=PagoProveedor.Estado.REGISTRADO,
        )
        .select_related(
            "compra",
            "cuenta_pago",
        )
    )

    # ========================================================
    # PAGOS DE OPERACIONES REGISTRADOS NO CONTABILIZADOS
    # ========================================================

    pagos_operacion_pendientes = (
        PagoOperacionContable.objects
        .filter(
            fecha_pago__gte=periodo.fecha_inicio,
            fecha_pago__lte=periodo.fecha_fin,
            estado=PagoOperacionContable.Estado.REGISTRADO,
        )
        .select_related(
            "operacion",
            "operacion__concepto",
            "cuenta_pago",
        )
    )

    # ========================================================
    # OPERACIONES CONTABLES EN BORRADOR
    # ========================================================

    operaciones_borrador = (
        OperacionContable.objects
        .filter(
            fecha__gte=periodo.fecha_inicio,
            fecha__lte=periodo.fecha_fin,
            estado=OperacionContable.Estado.BORRADOR,
        )
        .select_related(
            "concepto",
        )
    )

    # ========================================================
    # NOTAS DE CRÉDITO EN BORRADOR
    # ========================================================

    notas_credito_borrador = (
        NotaCredito.objects
        .filter(
            fecha_emision__gte=periodo.fecha_inicio,
            fecha_emision__lte=periodo.fecha_fin,
            estado=NotaCredito.Estado.BORRADOR,
        )
        .select_related(
            "ticket",
            "ticket__cliente",
            "cuenta_devolucion",
        )
        .order_by(
            "fecha_emision",
            "numero",
        )
    )

    # ========================================================
    # VALIDAR SI EL PERIODO PUEDE CERRARSE
    # ========================================================

    puede_cerrar = (
        periodo.estado == PeriodoContable.Estado.ABIERTO
        and not asientos_borrador.exists()
        and len(asientos_descuadrados) == 0
        and not propuestas_pendientes.exists()
        and not compras_directas_pendientes.exists()
        and not pagos_proveedor_pendientes.exists()
        and not pagos_operacion_pendientes.exists()
        and not operaciones_borrador.exists()
        and not notas_credito_borrador.exists()
    )

    # ========================================================
    # CERRAR PERIODO
    # ========================================================

    if request.method == "POST":

        if periodo.estado == PeriodoContable.Estado.CERRADO:

            messages.warning(
                request,
                "El período ya se encuentra cerrado."
            )

            return redirect(
                "contabilidad:cerrar_periodo_contable",
                periodo_id=periodo.id,
            )

        if not puede_cerrar:

            messages.error(
                request,
                "El período no puede cerrarse porque existen "
                "operaciones pendientes de regularizar."
            )

            return redirect(
                "contabilidad:cerrar_periodo_contable",
                periodo_id=periodo.id,
            )

        with transaction.atomic():

            periodo.estado = (
                PeriodoContable.Estado.CERRADO
            )

            periodo.save(
                update_fields=[
                    "estado",
                ]
            )

        messages.success(
            request,
            f"Período {periodo} cerrado correctamente."
        )

        return redirect(
            "contabilidad:cerrar_periodo_contable",
            periodo_id=periodo.id,
        )

    # ========================================================
    # CONTEXTO
    # ========================================================

    context = {

        "periodo":
            periodo,

        "asientos_periodo":
            asientos_periodo,

        "asientos_borrador":
            asientos_borrador,

        "asientos_descuadrados":
            asientos_descuadrados,

        "propuestas_pendientes":
            propuestas_pendientes,

        "compras_directas_pendientes":
            compras_directas_pendientes,

        "pagos_proveedor_pendientes":
            pagos_proveedor_pendientes,

        "pagos_operacion_pendientes":
            pagos_operacion_pendientes,

        "operaciones_borrador":
            operaciones_borrador,

        "notas_credito_borrador":
            notas_credito_borrador,

        "puede_cerrar":
            puede_cerrar,
    }

    return render(
        request,
        "contabilidad/cerrar_periodo_contable.html",
        context,
    )


def reabrir_periodo_contable(request, periodo_id):

    periodo = get_object_or_404(
        PeriodoContable,
        id=periodo_id,
    )

    if request.method == "POST":

        motivo = request.POST.get(
            "motivo_reapertura",
            ""
        ).strip()

        if periodo.estado == PeriodoContable.Estado.ABIERTO:

            messages.warning(
                request,
                "El período ya se encuentra abierto."
            )

            return redirect(
                "contabilidad:cerrar_periodo_contable",
                periodo_id=periodo.id,
            )

        if not motivo:

            messages.error(
                request,
                "Debe ingresar el motivo de la reapertura."
            )

            return redirect(
                "contabilidad:cerrar_periodo_contable",
                periodo_id=periodo.id,
            )

        periodo.estado = PeriodoContable.Estado.ABIERTO
        periodo.fecha_reapertura = timezone.now()
        periodo.reabierto_por = request.user
        periodo.motivo_reapertura = motivo

        periodo.save(
            update_fields=[
                "estado",
                "fecha_reapertura",
                "reabierto_por",
                "motivo_reapertura",
            ]
        )

        messages.success(
            request,
            f"Período {periodo} reabierto correctamente."
        )

        return redirect(
            "contabilidad:cerrar_periodo_contable",
            periodo_id=periodo.id,
        )

    return redirect(
        "contabilidad:cerrar_periodo_contable",
        periodo_id=periodo.id,
    )

from decimal import Decimal

from django.db.models import Sum
from django.shortcuts import render


def cierre_anual(request, anio):

    # ========================================================
    # 1. PERIODOS DEL AÑO
    # ========================================================

    periodos = (
        PeriodoContable.objects
        .filter(anio=anio)
        .order_by("mes")
    )

    cantidad_periodos = periodos.count()

    existen_12_periodos = (
        cantidad_periodos == 12
    )

    # ========================================================
    # 2. ENERO A NOVIEMBRE
    # ========================================================

    periodos_enero_noviembre = (
        periodos
        .filter(
            mes__gte=1,
            mes__lte=11,
        )
    )

    meses_abiertos_enero_noviembre = (
        periodos_enero_noviembre
        .filter(
            estado=PeriodoContable.Estado.ABIERTO
        )
    )

    enero_noviembre_cerrados = (
        periodos_enero_noviembre.count() == 11
        and not meses_abiertos_enero_noviembre.exists()
    )

    # ========================================================
    # 3. DICIEMBRE
    # ========================================================

    diciembre = (
        periodos
        .filter(mes=12)
        .first()
    )

    diciembre_existe = (
        diciembre is not None
    )

    diciembre_abierto = (
        diciembre is not None
        and
        diciembre.estado == PeriodoContable.Estado.ABIERTO
    )

    # ========================================================
    # 4. VERIFICAR SI YA EXISTE CIERRE ANUAL
    # ========================================================

    cierre_existente = None

    if diciembre:

        cierre_existente = (
            AsientoContable.objects
            .filter(
                periodo=diciembre,
                origen="CIERRE_ANUAL",
                origen_id=anio,
            )
            .exclude(
                estado=AsientoContable.Estado.ANULADO
            )
            .first()
        )

    # ========================================================
    # 5. CONDICIÓN PARA GENERAR CIERRE ANUAL
    # ========================================================

    puede_cerrar_anio = (
        existen_12_periodos
        and enero_noviembre_cerrados
        and diciembre_existe
        and diciembre_abierto
        and cierre_existente is None
    )

    # ========================================================
    # 6. MOVIMIENTOS CONTABILIZADOS DEL EJERCICIO
    # ========================================================

    movimientos = (
        DetalleAsiento.objects
        .filter(
            asiento__periodo__anio=anio,
            asiento__estado=AsientoContable.Estado.CONTABILIZADO,
        )
        .select_related(
            "cuenta",
            "categoria_gerencial",
            "centro_costo",
            "asiento",
        )
    )

    # ========================================================
    # 7. FUNCIÓN AUXILIAR DE SALDO
    # ========================================================

    def saldo_movimientos(queryset):

        total = Decimal("0.00")

        for mov in queryset:

            if mov.cuenta.naturaleza == "ACREEDORA":
                total += mov.haber - mov.debe
            else:
                total += mov.debe - mov.haber

        return total

    # ========================================================
    # 8. INGRESOS OPERACIONALES
    # ========================================================

    ingresos = saldo_movimientos(
        movimientos.filter(
            cuenta__tipo="INGRESO",
            cuenta__codigo__startswith="70",
        )
    )

    # ========================================================
    # 9. COSTO DE MERCADERÍA
    # ========================================================

    costo_mercaderia = saldo_movimientos(
        movimientos.filter(
            cuenta__tipo="COSTO"
        )
    )

    # ========================================================
    # 10. SERVICIOS DIRECTOS TERCERIZADOS
    # ========================================================

    servicios_directos = saldo_movimientos(
        movimientos.filter(
            categoria_gerencial__codigo__startswith="91"
        )
    )

    costos = (
        costo_mercaderia
        + servicios_directos
    )

    # ========================================================
    # 11. GASTOS ADMINISTRATIVOS
    # ========================================================

    gastos_administrativos = saldo_movimientos(
        movimientos.filter(
            categoria_gerencial__codigo__startswith="92"
        )
    )

    # ========================================================
    # 12. GASTOS COMERCIALES
    # ========================================================

    gastos_comerciales = saldo_movimientos(
        movimientos.filter(
            categoria_gerencial__codigo__startswith="93"
        )
    )

    # ========================================================
    # 13. INGRESOS FINANCIEROS
    # ========================================================

    ingresos_financieros = saldo_movimientos(
        movimientos.filter(
            cuenta__codigo__startswith="77"
        )
    )

    # ========================================================
    # 14. GASTOS FINANCIEROS
    # ========================================================

    gastos_financieros = saldo_movimientos(
        movimientos.filter(
            cuenta__codigo__startswith="67"
        )
    )

    gastos = (
        gastos_administrativos
        + gastos_comerciales
        + gastos_financieros
    )

    # ========================================================
    # 15. RESULTADO DEL EJERCICIO
    # ========================================================

    resultado_ejercicio = (
        ingresos
        - costos
        - gastos
        + ingresos_financieros
    )

    if resultado_ejercicio > 0:

        tipo_resultado = "UTILIDAD"

    elif resultado_ejercicio < 0:

        tipo_resultado = "PERDIDA"

    else:

        tipo_resultado = "CERO"

    # ========================================================
    # 16. EJECUTAR CIERRE ANUAL
    # ========================================================

    if request.method == "POST":

        if cierre_existente:

            messages.warning(
                request,
                f"El ejercicio {anio} ya tiene un "
                "asiento de cierre anual."
            )

            return redirect(
                "contabilidad:cierre_anual",
                anio=anio,
            )

        if not puede_cerrar_anio:

            messages.error(
                request,
                f"El ejercicio {anio} todavía no cumple "
                "las condiciones para ejecutar el cierre anual."
            )

            return redirect(
                "contabilidad:cierre_anual",
                anio=anio,
            )

        try:

            asiento = generar_cierre_anual(anio)

            messages.success(
                request,
                f"Cierre anual {anio} generado correctamente. "
                f"Asiento N.º {asiento.numero}."
            )

        except ValidationError as e:

            if hasattr(e, "messages") and e.messages:

                mensaje = e.messages[0]

            else:

                mensaje = str(e)

            messages.error(
                request,
                mensaje,
            )

        return redirect(
            "contabilidad:cierre_anual",
            anio=anio,
        )

    # ========================================================
    # 17. CONTEXTO
    # ========================================================

    context = {

        "anio": anio,

        "periodos": periodos,
        "cantidad_periodos": cantidad_periodos,
        "existen_12_periodos": existen_12_periodos,

        "enero_noviembre_cerrados":
            enero_noviembre_cerrados,

        "meses_abiertos_enero_noviembre":
            meses_abiertos_enero_noviembre,

        "diciembre": diciembre,
        "diciembre_existe": diciembre_existe,
        "diciembre_abierto": diciembre_abierto,

        "puede_cerrar_anio": puede_cerrar_anio,

        "ingresos": ingresos,
        "costos": costos,
        "gastos": gastos,

        "costo_mercaderia": costo_mercaderia,
        "servicios_directos": servicios_directos,

        "gastos_administrativos":
            gastos_administrativos,

        "gastos_comerciales":
            gastos_comerciales,

        "ingresos_financieros":
            ingresos_financieros,

        "gastos_financieros":
            gastos_financieros,

        "resultado_ejercicio":
            resultado_ejercicio,

        "tipo_resultado":
            tipo_resultado,

        "cierre_existente":
            cierre_existente,
    }

    return render(
        request,
        "contabilidad/cierre_anual.html",
        context,
    )

    # ========================================================
    # 1. PERIODOS DEL AÑO
    # ========================================================

    periodos = (
        PeriodoContable.objects
        .filter(anio=anio)
        .order_by("mes")
    )

    cantidad_periodos = periodos.count()

    existen_12_periodos = (
        cantidad_periodos == 12
    )

    # ========================================================
    # 2. ENERO A NOVIEMBRE
    # ========================================================

    periodos_enero_noviembre = periodos.filter(
        mes__gte=1,
        mes__lte=11,
    )

    meses_abiertos_enero_noviembre = (
        periodos_enero_noviembre
        .filter(
            estado=PeriodoContable.Estado.ABIERTO
        )
    )

    enero_noviembre_cerrados = (
        periodos_enero_noviembre.count() == 11
        and not meses_abiertos_enero_noviembre.exists()
    )

    # ========================================================
    # 3. DICIEMBRE
    # ========================================================

    diciembre = (
        periodos
        .filter(mes=12)
        .first()
    )

    diciembre_existe = (
        diciembre is not None
    )

    diciembre_abierto = (
        diciembre is not None
        and diciembre.estado == PeriodoContable.Estado.ABIERTO
    )

    # ========================================================
    # 4. CONDICIÓN PARA CIERRE ANUAL
    # ========================================================

    puede_cerrar_anio = (
        existen_12_periodos
        and enero_noviembre_cerrados
        and diciembre_existe
        and diciembre_abierto
    )

    # ========================================================
    # 5. MOVIMIENTOS CONTABILIZADOS DEL EJERCICIO
    # ========================================================

    movimientos = (
        DetalleAsiento.objects
        .filter(
            asiento__periodo__anio=anio,
            asiento__estado=AsientoContable.Estado.CONTABILIZADO,
        )
        .select_related(
            "cuenta",
            "categoria_gerencial",
            "centro_costo",
            "asiento",
        )
    )


    # ========================================================
    # 6. FUNCIÓN AUXILIAR
    # ========================================================

    def saldo_movimientos(queryset):

        total = Decimal("0.00")

        for mov in queryset:

            if mov.cuenta.naturaleza == "ACREEDORA":
                total += mov.haber - mov.debe
            else:
                total += mov.debe - mov.haber

        return total


    # ========================================================
    # 7. INGRESOS OPERACIONALES
    # ========================================================

    ingresos = saldo_movimientos(
        movimientos.filter(
            cuenta__tipo="INGRESO",
            cuenta__codigo__startswith="70",
        )
    )


    # ========================================================
    # 8. COSTO DE VENTAS Y SERVICIOS
    # ========================================================

    costo_mercaderia = saldo_movimientos(
        movimientos.filter(
            cuenta__tipo="COSTO"
        )
    )

    servicios_directos = saldo_movimientos(
        movimientos.filter(
            categoria_gerencial__codigo__startswith="91"
        )
    )

    costos = (
        costo_mercaderia
        + servicios_directos
    )


    # ========================================================
    # 9. GASTOS OPERATIVOS
    # ========================================================

    gastos_administrativos = saldo_movimientos(
        movimientos.filter(
            categoria_gerencial__codigo__startswith="92"
        )
    )

    gastos_comerciales = saldo_movimientos(
        movimientos.filter(
            categoria_gerencial__codigo__startswith="93"
        )
    )

    ingresos_financieros = saldo_movimientos(
        movimientos.filter(
            cuenta__codigo__startswith="77"
        )
    )

    gastos_financieros = saldo_movimientos(
        movimientos.filter(
            cuenta__codigo__startswith="67"
        )
    )

    gastos = (
        gastos_administrativos
        + gastos_comerciales
        + gastos_financieros
    )

    resultado_ejercicio = (
        ingresos
        - costos
        - gastos
        + ingresos_financieros
    )

    if resultado_ejercicio > 0:
        tipo_resultado = "UTILIDAD"

    elif resultado_ejercicio < 0:
        tipo_resultado = "PERDIDA"

    else:
        tipo_resultado = "CERO"
    # ========================================================
    # 10. VERIFICAR SI YA EXISTE CIERRE
    # ========================================================

    cierre_existente = None

    if diciembre:

        cierre_existente = (
            AsientoContable.objects
            .filter(
                periodo=diciembre,
                origen="CIERRE_ANUAL",
                origen_id=anio,
            )
            .exclude(
                estado=AsientoContable.Estado.ANULADO
            )
            .first()
        )

    # ========================================================
    # 11. CONTEXTO
    # ========================================================

    context = {

        "anio": anio,

        "periodos": periodos,
        "cantidad_periodos": cantidad_periodos,

        "existen_12_periodos": existen_12_periodos,

        "enero_noviembre_cerrados":
            enero_noviembre_cerrados,

        "meses_abiertos_enero_noviembre":
            meses_abiertos_enero_noviembre,

        "diciembre": diciembre,
        "diciembre_existe": diciembre_existe,
        "diciembre_abierto": diciembre_abierto,

        "puede_cerrar_anio": puede_cerrar_anio,

        # Vista previa
        "ingresos": ingresos,
        "costos": costos,
        "gastos": gastos,
        "resultado_ejercicio": resultado_ejercicio,
        "tipo_resultado": tipo_resultado,

        "cierre_existente": cierre_existente,
    }

    return render(
        request,
        "contabilidad/cierre_anual.html",
        context,
    )

    # ========================================================
    # 1. OBTENER LOS PERIODOS DEL AÑO
    # ========================================================

    periodos = (
        PeriodoContable.objects
        .filter(anio=anio)
        .order_by("mes")
    )

    # ========================================================
    # 2. VALIDAR QUE EXISTAN LOS 12 MESES
    # ========================================================

    cantidad_periodos = periodos.count()

    existen_12_periodos = (
        cantidad_periodos == 12
    )

    # ========================================================
    # 3. VALIDAR ENERO A NOVIEMBRE
    # ========================================================

    periodos_enero_noviembre = (
        periodos
        .filter(mes__gte=1, mes__lte=11)
    )

    meses_abiertos_enero_noviembre = (
        periodos_enero_noviembre
        .filter(
            estado=PeriodoContable.Estado.ABIERTO
        )
    )

    enero_noviembre_cerrados = (
        periodos_enero_noviembre.count() == 11
        and not meses_abiertos_enero_noviembre.exists()
    )

    # ========================================================
    # 4. VALIDAR DICIEMBRE
    # ========================================================

    diciembre = (
        periodos
        .filter(mes=12)
        .first()
    )

    diciembre_existe = (
        diciembre is not None
    )

    diciembre_abierto = (
        diciembre is not None
        and diciembre.estado == PeriodoContable.Estado.ABIERTO
    )

    # ========================================================
    # 5. DETERMINAR SI PUEDE HACERSE EL CIERRE ANUAL
    # ========================================================

    puede_cerrar_anio = (
        existen_12_periodos
        and enero_noviembre_cerrados
        and diciembre_existe
        and diciembre_abierto
    )

    # ========================================================
    # 6. CONTEXTO
    # ========================================================

    context = {
        "anio": anio,
        "periodos": periodos,
        "cantidad_periodos": cantidad_periodos,
        "existen_12_periodos": existen_12_periodos,
        "enero_noviembre_cerrados": enero_noviembre_cerrados,
        "meses_abiertos_enero_noviembre": meses_abiertos_enero_noviembre,
        "diciembre": diciembre,
        "diciembre_existe": diciembre_existe,
        "diciembre_abierto": diciembre_abierto,
        "puede_cerrar_anio": puede_cerrar_anio,
    }

    return render(
        request,
        "contabilidad/cierre_anual.html",
        context,
    )

def pendientes_contables(request):

    periodo_id = request.GET.get("periodo")

    periodos = (
        PeriodoContable.objects
        .all()
        .order_by("-anio", "-mes")
    )

    periodo = None

    if periodo_id:

        periodo = get_object_or_404(
            PeriodoContable,
            id=periodo_id,
        )

    else:

        periodo = (
            PeriodoContable.objects
            .filter(
                estado=PeriodoContable.Estado.ABIERTO
            )
            .order_by("-anio", "-mes")
            .first()
        )

    if not periodo:

        return render(
            request,
            "contabilidad/pendientes_contables.html",
            {
                "periodos": periodos,
                "periodo": None,
            },
        )

    # ========================================================
    # 1. PROPUESTAS DE COSTO PENDIENTES
    # ========================================================

    propuestas_pendientes = (
        PropuestaCostoVenta.objects
        .filter(
            ticket__fecha_emision__gte=periodo.fecha_inicio,
            ticket__fecha_emision__lte=periodo.fecha_fin,
        )
        .exclude(
            estado=PropuestaCostoVenta.Estado.CONTABILIZADA
        )
        .select_related("ticket")
    )

    # ========================================================
    # 2. COMPRAS DIRECTAS PENDIENTES
    # ========================================================

    compras_directas_pendientes = (
        CompraDirectaVenta.objects
        .filter(
            fecha_compra__gte=periodo.fecha_inicio,
            fecha_compra__lte=periodo.fecha_fin,
        )
        .exclude(
            estado=CompraDirectaVenta.Estado.CONTABILIZADA
        )
        .select_related(
            "detalle_costo",
            "detalle_costo__detalle_ticket",
            "cuenta_pago",
            "cuenta_proveedor",
        )
    )

    # ========================================================
    # 3. PAGOS A PROVEEDOR PENDIENTES
    # ========================================================

    pagos_proveedor_pendientes = (
        PagoProveedor.objects
        .filter(
            fecha_pago__gte=periodo.fecha_inicio,
            fecha_pago__lte=periodo.fecha_fin,
            estado=PagoProveedor.Estado.REGISTRADO,
        )
        .select_related(
            "compra",
            "cuenta_pago",
        )
        .order_by(
            "fecha_pago",
            "id",
        )
    )

    # ========================================================
    # 4. PAGOS DE OPERACIONES PENDIENTES
    # ========================================================

    pagos_operacion_pendientes = (
        PagoOperacionContable.objects
        .filter(
            fecha_pago__gte=periodo.fecha_inicio,
            fecha_pago__lte=periodo.fecha_fin,
            estado=PagoOperacionContable.Estado.REGISTRADO,
        )
        .select_related(
            "operacion",
            "operacion__concepto",
            "operacion__cuenta_por_pagar",
            "cuenta_pago",
        )
        .order_by(
            "fecha_pago",
            "id",
        )
    )

    # ========================================================
    # 5. OPERACIONES CONTABLES EN BORRADOR
    # ========================================================

    operaciones_borrador = (
        OperacionContable.objects
        .filter(
            fecha__gte=periodo.fecha_inicio,
            fecha__lte=periodo.fecha_fin,
            estado=OperacionContable.Estado.BORRADOR,
        )
        .select_related(
            "concepto",
            "concepto__cuenta_contable",
            "cuenta_pago",
            "cuenta_por_pagar",
        )
        .order_by(
            "fecha",
            "id",
        )
    )

    # ========================================================
    # 6. NOTAS DE CRÉDITO EN BORRADOR
    # ========================================================

    notas_credito_pendientes = (
        NotaCredito.objects
        .filter(
            fecha_emision__gte=periodo.fecha_inicio,
            fecha_emision__lte=periodo.fecha_fin,
            estado=NotaCredito.Estado.BORRADOR,
        )
        .select_related(
            "ticket",
            "ticket__cliente",
            "cuenta_devolucion",
        )
        .order_by(
            "fecha_emision",
            "numero",
        )
    )

    # ========================================================
    # 7. ASIENTOS EN BORRADOR
    # ========================================================

    asientos_borrador = (
        AsientoContable.objects
        .filter(
            periodo=periodo,
            estado=AsientoContable.Estado.BORRADOR,
        )
        .order_by(
            "fecha",
            "numero",
        )
    )

    # ========================================================
    # 8. ASIENTOS DESCUADRADOS
    # ========================================================

    asientos_periodo = (
        AsientoContable.objects
        .filter(
            periodo=periodo
        )
        .exclude(
            estado=AsientoContable.Estado.ANULADO
        )
    )

    asientos_descuadrados = []

    for asiento in asientos_periodo:

        if not asiento.esta_cuadrado:

            asientos_descuadrados.append(
                asiento
            )

    # ========================================================
    # 9. CUENTAS POR PAGAR - COMPRAS DIRECTAS
    # NO BLOQUEAN EL CIERRE
    # ========================================================

    compras_con_deuda = (
        CompraDirectaVenta.objects
        .filter(
            fecha_compra__lte=periodo.fecha_fin,
            estado=CompraDirectaVenta.Estado.CONTABILIZADA,
            cuenta_proveedor__isnull=False,
        )
        .select_related(
            "detalle_costo",
            "detalle_costo__detalle_ticket",
            "cuenta_proveedor",
        )
        .prefetch_related(
            "pagos_proveedor"
        )
        .order_by(
            "fecha_vencimiento",
            "fecha_compra",
            "id",
        )
    )

    cuentas_por_pagar = []

    total_cuentas_por_pagar = Decimal(
        "0.00"
    )

    for compra in compras_con_deuda:

        saldo = compra.saldo_pendiente

        if saldo > Decimal("0.00"):

            cuentas_por_pagar.append(
                compra
            )

            total_cuentas_por_pagar += saldo

    # ========================================================
    # 10. CUENTAS POR PAGAR - OPERACIONES CONTABLES
    # NO BLOQUEAN EL CIERRE
    # ========================================================

    operaciones_con_deuda = (
        OperacionContable.objects
        .filter(
            fecha__lte=periodo.fecha_fin,
            estado=OperacionContable.Estado.CONTABILIZADA,
            cuenta_por_pagar__isnull=False,
        )
        .select_related(
            "concepto",
            "cuenta_por_pagar",
        )
        .prefetch_related(
            "pagos_posteriores"
        )
        .order_by(
            "fecha_vencimiento",
            "fecha",
            "id",
        )
    )

    operaciones_por_pagar = []

    total_operaciones_por_pagar = Decimal(
        "0.00"
    )

    for operacion in operaciones_con_deuda:

        saldo = operacion.saldo_pendiente

        if saldo > Decimal("0.00"):

            operaciones_por_pagar.append(
                operacion
            )

            total_operaciones_por_pagar += saldo

    # ========================================================
    # 11. CANTIDADES
    # ========================================================

    cantidad_propuestas = (
        propuestas_pendientes.count()
    )

    cantidad_compras_directas = (
        compras_directas_pendientes.count()
    )

    cantidad_pagos_proveedor = (
        pagos_proveedor_pendientes.count()
    )

    cantidad_pagos_operacion = (
        pagos_operacion_pendientes.count()
    )

    cantidad_operaciones_borrador = (
        operaciones_borrador.count()
    )

    cantidad_notas_credito = (
        notas_credito_pendientes.count()
    )

    cantidad_borradores = (
        asientos_borrador.count()
    )

    cantidad_descuadrados = (
        len(
            asientos_descuadrados
        )
    )

    cantidad_cuentas_por_pagar = (
        len(
            cuentas_por_pagar
        )
    )

    cantidad_operaciones_por_pagar = (
        len(
            operaciones_por_pagar
        )
    )

    # ========================================================
    # 12. PENDIENTES BLOQUEANTES
    # ========================================================

    total_pendientes = (
        cantidad_propuestas
        + cantidad_compras_directas
        + cantidad_pagos_proveedor
        + cantidad_pagos_operacion
        + cantidad_operaciones_borrador
        + cantidad_notas_credito
        + cantidad_borradores
        + cantidad_descuadrados
    )

    periodo_sin_pendientes = (
        total_pendientes == 0
    )

    # ========================================================
    # 13. TOTAL GENERAL DE CUENTAS POR PAGAR
    # ========================================================

    cantidad_total_cuentas_por_pagar = (
        cantidad_cuentas_por_pagar
        + cantidad_operaciones_por_pagar
    )

    total_general_cuentas_por_pagar = (
        total_cuentas_por_pagar
        + total_operaciones_por_pagar
    )

    # ========================================================
    # 14. CONTEXTO
    # ========================================================

    context = {

        "periodos":
            periodos,

        "periodo":
            periodo,

        "propuestas_pendientes":
            propuestas_pendientes,

        "compras_directas_pendientes":
            compras_directas_pendientes,

        "pagos_proveedor_pendientes":
            pagos_proveedor_pendientes,

        "pagos_operacion_pendientes":
            pagos_operacion_pendientes,

        "operaciones_borrador":
            operaciones_borrador,

        "notas_credito_pendientes":
            notas_credito_pendientes,

        "asientos_borrador":
            asientos_borrador,

        "asientos_descuadrados":
            asientos_descuadrados,

        "cuentas_por_pagar":
            cuentas_por_pagar,

        "operaciones_por_pagar":
            operaciones_por_pagar,

        "cantidad_propuestas":
            cantidad_propuestas,

        "cantidad_compras_directas":
            cantidad_compras_directas,

        "cantidad_pagos_proveedor":
            cantidad_pagos_proveedor,

        "cantidad_pagos_operacion":
            cantidad_pagos_operacion,

        "cantidad_operaciones_borrador":
            cantidad_operaciones_borrador,

        "cantidad_notas_credito":
            cantidad_notas_credito,

        "cantidad_borradores":
            cantidad_borradores,

        "cantidad_descuadrados":
            cantidad_descuadrados,

        "cantidad_cuentas_por_pagar":
            cantidad_cuentas_por_pagar,

        "cantidad_operaciones_por_pagar":
            cantidad_operaciones_por_pagar,

        "total_cuentas_por_pagar":
            total_cuentas_por_pagar,

        "total_operaciones_por_pagar":
            total_operaciones_por_pagar,

        "cantidad_total_cuentas_por_pagar":
            cantidad_total_cuentas_por_pagar,

        "total_general_cuentas_por_pagar":
            total_general_cuentas_por_pagar,

        "total_pendientes":
            total_pendientes,

        "periodo_sin_pendientes":
            periodo_sin_pendientes,
    }

    return render(
        request,
        "contabilidad/pendientes_contables.html",
        context,
    )
def editar_compra_directa(request, compra_id):

    compra = get_object_or_404(
        CompraDirectaVenta.objects.select_related(
            "detalle_costo",
            "detalle_costo__detalle_ticket",
            "cuenta_pago",
            "cuenta_proveedor",
        ),
        id=compra_id,
    )

    # ========================================================
    # NO PERMITIR EDITAR UNA COMPRA YA CONTABILIZADA
    # ========================================================

    if (
        compra.estado
        == CompraDirectaVenta.Estado.CONTABILIZADA
    ):

        messages.warning(
            request,
            "La compra directa ya se encuentra contabilizada "
            "y no puede ser modificada."
        )

        return redirect(
            "contabilidad:pendientes_contables"
        )

    # ========================================================
    # CUENTAS PARA PAGOS
    # ========================================================

    cuentas_pago = (
        CuentaContable.objects
        .filter(
            activo=True,
            acepta_movimientos=True,
            codigo__in=[
                "10101",
                "10401",
            ],
        )
        .order_by("codigo")
    )

    # ========================================================
    # CUENTAS POR PAGAR
    # ========================================================

    cuentas_proveedor = (
        CuentaContable.objects
        .filter(
            activo=True,
            acepta_movimientos=True,
            codigo__startswith="42",
        )
        .order_by("codigo")
    )

    # ========================================================
    # POST
    # ========================================================

    if request.method == "POST":

        proveedor_nombre = (
            request.POST
            .get("proveedor_nombre", "")
            .strip()
        )

        fecha_compra = (
            request.POST
            .get("fecha_compra", "")
            .strip()
        )

        tipo_documento = (
            request.POST
            .get("tipo_documento", "")
            .strip()
        )

        numero_documento = (
            request.POST
            .get("numero_documento", "")
            .strip()
        )

        cantidad_txt = (
            request.POST
            .get("cantidad", "")
            .strip()
        )

        costo_unitario_txt = (
            request.POST
            .get("costo_unitario", "")
            .strip()
        )

        forma_pago = (
            request.POST
            .get("forma_pago", "")
            .strip()
        )

        monto_pagado_txt = (
            request.POST
            .get("monto_pagado", "")
            .strip()
        )

        fecha_pago = (
            request.POST
            .get("fecha_pago", "")
            .strip()
        )

        fecha_vencimiento = (
            request.POST
            .get("fecha_vencimiento", "")
            .strip()
        )

        cuenta_pago_id = (
            request.POST
            .get("cuenta_pago", "")
            .strip()
        )

        cuenta_proveedor_id = (
            request.POST
            .get("cuenta_proveedor", "")
            .strip()
        )

        observacion = (
            request.POST
            .get("observacion", "")
            .strip()
        )

        errores = []

        # ====================================================
        # CANTIDAD
        # ====================================================

        try:

            cantidad = Decimal(cantidad_txt)

            if cantidad <= Decimal("0.00"):

                errores.append(
                    "La cantidad debe ser mayor que cero."
                )

        except Exception:

            cantidad = None

            errores.append(
                "La cantidad ingresada no es válida."
            )

        # ====================================================
        # COSTO UNITARIO
        # ====================================================

        try:

            costo_unitario = Decimal(
                costo_unitario_txt
            )

            if costo_unitario <= Decimal("0.00"):

                errores.append(
                    "El costo unitario debe ser mayor que cero."
                )

        except Exception:

            costo_unitario = None

            errores.append(
                "El costo unitario ingresado no es válido."
            )

        # ====================================================
        # MONTO PAGADO
        # ====================================================

        try:

            monto_pagado = Decimal(
                monto_pagado_txt or "0.00"
            )

            if monto_pagado < Decimal("0.00"):

                errores.append(
                    "El monto pagado no puede ser negativo."
                )

        except Exception:

            monto_pagado = None

            errores.append(
                "El monto pagado ingresado no es válido."
            )

        # ====================================================
        # FORMA DE PAGO
        # ====================================================

        formas_validas = {
            valor
            for valor, etiqueta
            in CompraDirectaVenta.FormaPago.choices
        }

        if forma_pago not in formas_validas:

            errores.append(
                "Debe seleccionar una forma de pago válida."
            )

        # ====================================================
        # FECHA COMPRA
        # ====================================================

        if not fecha_compra:

            errores.append(
                "Debe ingresar la fecha de compra."
            )

        # ====================================================
        # CUENTAS
        # ====================================================

        cuenta_pago = None
        cuenta_proveedor = None

        # ----------------------------------------------------
        # CRÉDITO
        # ----------------------------------------------------

        if (
            forma_pago
            == CompraDirectaVenta.FormaPago.CREDITO
        ):

            if cuenta_proveedor_id:

                cuenta_proveedor = (
                    CuentaContable.objects
                    .filter(
                        id=cuenta_proveedor_id,
                        activo=True,
                        acepta_movimientos=True,
                        codigo__startswith="42",
                    )
                    .first()
                )

            if not cuenta_proveedor:

                errores.append(
                    "Debe seleccionar la cuenta por pagar "
                    "al proveedor."
                )

        # ----------------------------------------------------
        # PAGO PARCIAL
        # ----------------------------------------------------

        elif (
            forma_pago
            == CompraDirectaVenta.FormaPago.PARCIAL
        ):

            if cuenta_pago_id:

                cuenta_pago = (
                    CuentaContable.objects
                    .filter(
                        id=cuenta_pago_id,
                        activo=True,
                        acepta_movimientos=True,
                    )
                    .first()
                )

            if not cuenta_pago:

                errores.append(
                    "Debe seleccionar la cuenta utilizada "
                    "para realizar el pago parcial."
                )

            if cuenta_proveedor_id:

                cuenta_proveedor = (
                    CuentaContable.objects
                    .filter(
                        id=cuenta_proveedor_id,
                        activo=True,
                        acepta_movimientos=True,
                        codigo__startswith="42",
                    )
                    .first()
                )

            if not cuenta_proveedor:

                errores.append(
                    "Debe seleccionar la cuenta por pagar "
                    "donde quedará registrado el saldo."
                )

        # ----------------------------------------------------
        # CONTADO
        # ----------------------------------------------------

        else:

            if cuenta_pago_id:

                cuenta_pago = (
                    CuentaContable.objects
                    .filter(
                        id=cuenta_pago_id,
                        activo=True,
                        acepta_movimientos=True,
                    )
                    .first()
                )

            if not cuenta_pago:

                errores.append(
                    "Debe seleccionar la cuenta desde "
                    "la que se realizó el pago."
                )

        # ====================================================
        # ASIGNAR DATOS
        # ====================================================

        if not errores:

            compra.proveedor_nombre = proveedor_nombre

            compra.fecha_compra = fecha_compra

            compra.tipo_documento = tipo_documento

            compra.numero_documento = numero_documento

            compra.cantidad = cantidad

            compra.costo_unitario = costo_unitario

            compra.forma_pago = forma_pago

            compra.monto_pagado = monto_pagado

            compra.observacion = observacion

            # ------------------------------------------------
            # FECHA PAGO
            # ------------------------------------------------

            compra.fecha_pago = (
                fecha_pago
                if fecha_pago
                else None
            )

            # ------------------------------------------------
            # VENCIMIENTO
            # ------------------------------------------------

            compra.fecha_vencimiento = (
                fecha_vencimiento
                if fecha_vencimiento
                else None
            )

            # ------------------------------------------------
            # CUENTAS
            # ------------------------------------------------

            compra.cuenta_pago = cuenta_pago

            compra.cuenta_proveedor = (
                cuenta_proveedor
            )

            # =================================================
            # VALIDACIÓN DEL MODELO
            # =================================================

            try:

                compra.full_clean()

                compra.save()

                messages.success(
                    request,
                    "Compra directa actualizada "
                    "correctamente."
                )

                periodo = (
                    PeriodoContable.objects
                    .filter(
                        fecha_inicio__lte=compra.fecha_compra,
                        fecha_fin__gte=compra.fecha_compra,
                    )
                    .first()
                )

                if periodo:

                    url = reverse(
                        "contabilidad:pendientes_contables"
                    )

                    return redirect(
                        f"{url}?periodo={periodo.id}"
                    )

                return redirect(
                    "contabilidad:pendientes_contables"
                )

            except ValidationError as exc:

                if hasattr(
                    exc,
                    "message_dict",
                ):

                    for campo, mensajes_error in (
                        exc.message_dict.items()
                    ):

                        for mensaje in mensajes_error:

                            errores.append(
                                mensaje
                            )

                else:

                    for mensaje in exc.messages:

                        errores.append(
                            mensaje
                        )

        # ====================================================
        # MENSAJES DE ERROR
        # ====================================================

        for error in errores:

            messages.error(
                request,
                error,
            )

    # ========================================================
    # CONTEXTO
    # ========================================================

    context = {

        "compra": compra,

        "cuentas_pago":
            cuentas_pago,

        "cuentas_proveedor":
            cuentas_proveedor,

        "formas_pago":
            CompraDirectaVenta.FormaPago.choices,
    }

    return render(
        request,
        "contabilidad/editar_compra_directa.html",
        context,
    )

def registrar_pago_proveedor(request, compra_id):

    compra = get_object_or_404(
        CompraDirectaVenta.objects
        .select_related(
            "cuenta_proveedor",
            "detalle_costo",
            "detalle_costo__detalle_ticket",
        )
        .prefetch_related(
            "pagos_proveedor",
        ),
        id=compra_id,
    )

    # ========================================================
    # 1. VALIDAR COMPRA
    # ========================================================

    if (
        compra.estado
        != CompraDirectaVenta.Estado.CONTABILIZADA
    ):

        messages.error(
            request,
            "La compra debe estar contabilizada antes "
            "de registrar pagos posteriores."
        )

        return redirect(
            "contabilidad:pendientes_contables"
        )

    # ========================================================
    # 2. VALIDAR SALDO
    # ========================================================

    saldo_actual = (
        compra.saldo_pendiente
    )

    if saldo_actual <= Decimal("0.00"):

        messages.info(
            request,
            "La compra ya se encuentra totalmente pagada."
        )

        return redirect(
            "contabilidad:pendientes_contables"
        )

    # ========================================================
    # 3. CUENTAS DISPONIBLES PARA EL PAGO
    # ========================================================

    cuentas_pago = (
        CuentaContable.objects
        .filter(
            activo=True,
            acepta_movimientos=True,
            codigo__in=[
                "10101",
                "10401",
            ],
        )
        .order_by(
            "codigo"
        )
    )

    # ========================================================
    # 4. POST
    # ========================================================

    if request.method == "POST":

        fecha_pago_txt = (
            request.POST
            .get("fecha_pago", "")
            .strip()
        )

        monto_txt = (
            request.POST
            .get("monto", "")
            .strip()
        )

        cuenta_pago_id = (
            request.POST
            .get("cuenta_pago", "")
            .strip()
        )

        observacion = (
            request.POST
            .get("observacion", "")
            .strip()
        )

        errores = []

        # ====================================================
        # FECHA
        # ====================================================

        fecha_pago = None

        if not fecha_pago_txt:

            errores.append(
                "Debe ingresar la fecha del pago."
            )

        else:

            try:

                fecha_pago = date.fromisoformat(
                    fecha_pago_txt
                )

            except ValueError:

                errores.append(
                    "La fecha de pago no es válida."
                )

        # ====================================================
        # MONTO
        # ====================================================

        monto = None

        try:

            monto = Decimal(
                monto_txt
            )

            if monto <= Decimal("0.00"):

                errores.append(
                    "El monto debe ser mayor que cero."
                )

            elif monto > saldo_actual:

                errores.append(
                    (
                        "El monto no puede superar "
                        f"el saldo pendiente de "
                        f"S/ {saldo_actual:.2f}."
                    )
                )

        except Exception:

            errores.append(
                "El monto ingresado no es válido."
            )

        # ====================================================
        # CUENTA DE PAGO
        # ====================================================

        cuenta_pago = None

        if not cuenta_pago_id:

            errores.append(
                "Debe seleccionar la cuenta "
                "desde la que se realizó el pago."
            )

        else:

            cuenta_pago = (
                CuentaContable.objects
                .filter(
                    id=cuenta_pago_id,
                    activo=True,
                    acepta_movimientos=True,
                    codigo__in=[
                        "10101",
                        "10401",
                    ],
                )
                .first()
            )

            if not cuenta_pago:

                errores.append(
                    "La cuenta de pago seleccionada "
                    "no es válida."
                )

        # ====================================================
        # PERÍODO
        # ====================================================

        periodo_pago = None

        if fecha_pago:

            periodo_pago = (
                PeriodoContable.objects
                .filter(
                    fecha_inicio__lte=fecha_pago,
                    fecha_fin__gte=fecha_pago,
                )
                .first()
            )

            if not periodo_pago:

                errores.append(
                    "No existe un período contable "
                    "para la fecha del pago."
                )

            elif (
                periodo_pago.estado
                == PeriodoContable.Estado.CERRADO
            ):

                errores.append(
                    f"El período {periodo_pago} "
                    "se encuentra cerrado."
                )

        # ====================================================
        # CREAR Y CONTABILIZAR
        # ====================================================

        if not errores:

            try:

                with transaction.atomic():

                    pago = PagoProveedor(
                        compra=compra,
                        fecha_pago=fecha_pago,
                        monto=monto,
                        cuenta_pago=cuenta_pago,
                        observacion=observacion,
                        estado=PagoProveedor.Estado.REGISTRADO,
                    )

                    pago.full_clean()

                    pago.save()

                    asiento = (
                        contabilizar_pago_proveedor(
                            pago
                        )
                    )

                messages.success(
                    request,
                    (
                        "Pago registrado y contabilizado "
                        "correctamente. "
                        f"Asiento N.° {asiento.numero} "
                        f"del período {asiento.periodo}."
                    )
                )

                url = reverse(
                    "contabilidad:pendientes_contables"
                )

                return redirect(
                    f"{url}?periodo={periodo_pago.id}"
                )

            except ValidationError as exc:

                if hasattr(
                    exc,
                    "message_dict",
                ):

                    for campo, mensajes_error in (
                        exc.message_dict.items()
                    ):

                        for mensaje in mensajes_error:

                            errores.append(
                                mensaje
                            )

                else:

                    for mensaje in exc.messages:

                        errores.append(
                            mensaje
                        )

            except Exception as exc:

                errores.append(
                    "No fue posible registrar el pago. "
                    f"Detalle: {exc}"
                )

        # ====================================================
        # MENSAJES
        # ====================================================

        for error in errores:

            messages.error(
                request,
                error,
            )

    # ========================================================
    # 5. HISTORIAL
    # ========================================================

    pagos_anteriores = (
        compra.pagos_proveedor
        .exclude(
            estado=PagoProveedor.Estado.ANULADO
        )
        .select_related(
            "cuenta_pago"
        )
        .order_by(
            "fecha_pago",
            "id",
        )
    )

    context = {

        "compra":
            compra,

        "saldo_actual":
            saldo_actual,

        "cuentas_pago":
            cuentas_pago,

        "pagos_anteriores":
            pagos_anteriores,
    }

    return render(
        request,
        "contabilidad/registrar_pago_proveedor.html",
        context,
    )

# ============================================================
# REGISTRAR GASTO / OPERACIÓN
# ============================================================

def registrar_pago_operacion(request, operacion_id):

    operacion = get_object_or_404(
        OperacionContable.objects
        .select_related(
            "concepto",
            "cuenta_por_pagar",
        )
        .prefetch_related(
            "pagos_posteriores",
        ),
        id=operacion_id,
    )

    # ========================================================
    # 1. VALIDAR OPERACIÓN
    # ========================================================

    if (
        operacion.estado
        != OperacionContable.Estado.CONTABILIZADA
    ):

        messages.error(
            request,
            "La operación debe estar contabilizada antes "
            "de registrar pagos posteriores."
        )

        return redirect(
            "contabilidad:pendientes_contables"
        )

    if not operacion.cuenta_por_pagar_id:

        messages.error(
            request,
            "La operación no tiene una cuenta por pagar asociada."
        )

        return redirect(
            "contabilidad:pendientes_contables"
        )

    # ========================================================
    # 2. VALIDAR SALDO
    # ========================================================

    saldo_actual = (
        operacion.saldo_pendiente
    )

    if saldo_actual <= Decimal("0.00"):

        messages.info(
            request,
            "La operación ya se encuentra totalmente pagada."
        )

        return redirect(
            "contabilidad:pendientes_contables"
        )

    # ========================================================
    # 3. CUENTAS DISPONIBLES PARA EL PAGO
    # ========================================================

    cuentas_pago = (
        CuentaContable.objects
        .filter(
            activo=True,
            acepta_movimientos=True,
            codigo__in=[
                "10101",
                "10401",
            ],
        )
        .order_by(
            "codigo"
        )
    )

    # ========================================================
    # 4. POST
    # ========================================================

    if request.method == "POST":

        fecha_pago_txt = (
            request.POST
            .get("fecha_pago", "")
            .strip()
        )

        monto_txt = (
            request.POST
            .get("monto", "")
            .strip()
        )

        cuenta_pago_id = (
            request.POST
            .get("cuenta_pago", "")
            .strip()
        )

        observacion = (
            request.POST
            .get("observacion", "")
            .strip()
        )

        errores = []

        # ====================================================
        # FECHA
        # ====================================================

        fecha_pago = None

        if not fecha_pago_txt:

            errores.append(
                "Debe ingresar la fecha del pago."
            )

        else:

            try:

                fecha_pago = date.fromisoformat(
                    fecha_pago_txt
                )

            except ValueError:

                errores.append(
                    "La fecha de pago no es válida."
                )

        # ====================================================
        # MONTO
        # ====================================================

        monto = None

        try:

            monto = Decimal(
                monto_txt
            )

            if monto <= Decimal("0.00"):

                errores.append(
                    "El monto debe ser mayor que cero."
                )

            elif monto > saldo_actual:

                errores.append(
                    (
                        "El monto no puede superar "
                        f"el saldo pendiente de "
                        f"S/ {saldo_actual:.2f}."
                    )
                )

        except Exception:

            errores.append(
                "El monto ingresado no es válido."
            )

        # ====================================================
        # CUENTA DE PAGO
        # ====================================================

        cuenta_pago = None

        if not cuenta_pago_id:

            errores.append(
                "Debe seleccionar la cuenta "
                "desde la que se realizó el pago."
            )

        else:

            cuenta_pago = (
                CuentaContable.objects
                .filter(
                    id=cuenta_pago_id,
                    activo=True,
                    acepta_movimientos=True,
                    codigo__in=[
                        "10101",
                        "10401",
                    ],
                )
                .first()
            )

            if not cuenta_pago:

                errores.append(
                    "La cuenta de pago seleccionada "
                    "no es válida."
                )

        # ====================================================
        # PERÍODO
        # ====================================================

        periodo_pago = None

        if fecha_pago:

            periodo_pago = (
                PeriodoContable.objects
                .filter(
                    fecha_inicio__lte=fecha_pago,
                    fecha_fin__gte=fecha_pago,
                )
                .first()
            )

            if not periodo_pago:

                errores.append(
                    "No existe un período contable "
                    "para la fecha del pago."
                )

            elif (
                periodo_pago.estado
                == PeriodoContable.Estado.CERRADO
            ):

                errores.append(
                    f"El período {periodo_pago} "
                    "se encuentra cerrado."
                )

        # ====================================================
        # CREAR Y CONTABILIZAR
        # ====================================================

        if not errores:

            try:

                with transaction.atomic():

                    pago = PagoOperacionContable(
                        operacion=operacion,
                        fecha_pago=fecha_pago,
                        monto=monto,
                        cuenta_pago=cuenta_pago,
                        observacion=observacion,
                        estado=(
                            PagoOperacionContable
                            .Estado
                            .REGISTRADO
                        ),
                    )

                    pago.full_clean()

                    pago.save()

                    asiento = (
                        contabilizar_pago_operacion_contable(
                            pago
                        )
                    )

                messages.success(
                    request,
                    (
                        "Pago registrado y contabilizado "
                        "correctamente. "
                        f"Asiento N.° {asiento.numero} "
                        f"del período {asiento.periodo}."
                    )
                )

                url = reverse(
                    "contabilidad:pendientes_contables"
                )

                return redirect(
                    f"{url}?periodo={periodo_pago.id}"
                )

            except ValidationError as exc:

                if hasattr(
                    exc,
                    "message_dict",
                ):

                    for campo, mensajes_error in (
                        exc.message_dict.items()
                    ):

                        for mensaje in mensajes_error:

                            errores.append(
                                mensaje
                            )

                else:

                    for mensaje in exc.messages:

                        errores.append(
                            mensaje
                        )

            except Exception as exc:

                errores.append(
                    "No fue posible registrar el pago. "
                    f"Detalle: {exc}"
                )

        # ====================================================
        # MENSAJES
        # ====================================================

        for error in errores:

            messages.error(
                request,
                error,
            )

    # ========================================================
    # 5. HISTORIAL
    # ========================================================

    pagos_anteriores = (
        operacion.pagos_posteriores
        .exclude(
            estado=PagoOperacionContable.Estado.ANULADO
        )
        .select_related(
            "cuenta_pago",
            "asiento",
        )
        .order_by(
            "fecha_pago",
            "id",
        )
    )

    context = {

        "operacion":
            operacion,

        "saldo_actual":
            saldo_actual,

        "cuentas_pago":
            cuentas_pago,

        "pagos_anteriores":
            pagos_anteriores,
    }

    return render(
        request,
        "contabilidad/registrar_pago_operacion.html",
        context,
    )



def registrar_gasto_operacion(request):

    # ========================================================
    # CONCEPTOS PERMITIDOS PARA ESTA V1
    #
    # Solo conceptos finales, activos, con cuenta configurada
    # y cuya cuenta tenga naturaleza de débito:
    # ACTIVO, COSTO o GASTO.
    # ========================================================

    conceptos = (
        ConceptoOperacion.objects
        .select_related(
            "cuenta_contable",
            "categoria_gerencial",
            "centro_costo",
            "concepto_padre",
        )
        .filter(
            activo=True,
            es_grupo=False,
            cuenta_contable__isnull=False,
            cuenta_contable__activo=True,
            cuenta_contable__acepta_movimientos=True,
            cuenta_contable__tipo__in=[
                CuentaContable.TipoCuenta.ACTIVO,
                CuentaContable.TipoCuenta.COSTO,
                CuentaContable.TipoCuenta.GASTO,
            ],
        )
        .order_by(
            "orden",
            "nombre",
        )
    )

    # ========================================================
    # CUENTAS DE PAGO
    # ========================================================

    cuentas_pago = (
        CuentaContable.objects
        .filter(
            activo=True,
            acepta_movimientos=True,
            codigo__in=[
                "10101",
                "10401",
                "10402",
            ],
        )
        .order_by("codigo")
    )

    # ========================================================
    # CUENTAS POR PAGAR
    # ========================================================

    cuentas_por_pagar = (
        CuentaContable.objects
        .filter(
            activo=True,
            acepta_movimientos=True,
            codigo__startswith="42",
        )
        .order_by("codigo")
    )

    # ========================================================
    # INFORMACIÓN DE CONCEPTOS PARA LA INTERFAZ
    # ========================================================

    clasificacion_conceptos = {}

    for concepto in conceptos:

        categoria = (
            concepto.categoria_gerencial.nombre
            if concepto.categoria_gerencial
            else "Sin categoría gerencial"
        )

        centro = (
            concepto.centro_costo.nombre
            if concepto.centro_costo
            else "Sin centro de costo"
        )

        cuenta = concepto.cuenta_contable

        clasificacion_conceptos[str(concepto.id)] = {
            "nombre": concepto.nombre,
            "tipo_operacion": concepto.get_tipo_operacion_display(),
            "categoria": categoria,
            "centro": centro,
            "cuenta_codigo": cuenta.codigo,
            "cuenta_nombre": cuenta.nombre,
            "requiere_proveedor": concepto.requiere_proveedor,
            "requiere_cliente": concepto.requiere_cliente,
            "requiere_comprobante": concepto.requiere_comprobante,
        }

    # ========================================================
    # VALORES INICIALES
    # ========================================================

    datos_formulario = {
        "fecha": date.today().isoformat(),
        "concepto": "",
        "descripcion": "",
        "proveedor_nombre": "",
        "cliente_nombre": "",
        "tipo_documento": "",
        "numero_documento": "",
        "importe_total": "",
        "forma_pago": "",
        "monto_pagado": "",
        "fecha_pago": date.today().isoformat(),
        "cuenta_pago": "",
        "cuenta_por_pagar": "",
        "fecha_vencimiento": "",
        "observacion": "",
    }

    # ========================================================
    # POST
    # ========================================================

    if request.method == "POST":

        errores = []

        datos_formulario = {
            "fecha": request.POST.get(
                "fecha",
                "",
            ).strip(),

            "concepto": request.POST.get(
                "concepto",
                "",
            ).strip(),

            "descripcion": request.POST.get(
                "descripcion",
                "",
            ).strip(),

            "proveedor_nombre": request.POST.get(
                "proveedor_nombre",
                "",
            ).strip(),

            "cliente_nombre": request.POST.get(
                "cliente_nombre",
                "",
            ).strip(),

            "tipo_documento": request.POST.get(
                "tipo_documento",
                "",
            ).strip(),

            "numero_documento": request.POST.get(
                "numero_documento",
                "",
            ).strip(),

            "importe_total": request.POST.get(
                "importe_total",
                "",
            ).strip(),

            "forma_pago": request.POST.get(
                "forma_pago",
                "",
            ).strip(),

            "monto_pagado": request.POST.get(
                "monto_pagado",
                "",
            ).strip(),

            "fecha_pago": request.POST.get(
                "fecha_pago",
                "",
            ).strip(),

            "cuenta_pago": request.POST.get(
                "cuenta_pago",
                "",
            ).strip(),

            "cuenta_por_pagar": request.POST.get(
                "cuenta_por_pagar",
                "",
            ).strip(),

            "fecha_vencimiento": request.POST.get(
                "fecha_vencimiento",
                "",
            ).strip(),

            "observacion": request.POST.get(
                "observacion",
                "",
            ).strip(),
        }

        # ====================================================
        # FECHA
        # ====================================================

        fecha_operacion = None

        try:

            fecha_operacion = date.fromisoformat(
                datos_formulario["fecha"]
            )

        except (ValueError, TypeError):

            errores.append(
                "Debe ingresar una fecha válida."
            )

        # ====================================================
        # CONCEPTO
        # ====================================================

        concepto = None

        if datos_formulario["concepto"]:

            concepto = (
                conceptos
                .filter(
                    id=datos_formulario["concepto"]
                )
                .first()
            )

        if not concepto:

            errores.append(
                "Debe seleccionar un concepto válido."
            )

        # ====================================================
        # IMPORTE TOTAL
        # ====================================================

        importe_total = None

        try:

            importe_total = Decimal(
                datos_formulario["importe_total"]
            )

        except (
            InvalidOperation,
            TypeError,
            ValueError,
        ):

            errores.append(
                "El importe total ingresado no es válido."
            )

        # ====================================================
        # FORMA DE PAGO
        # ====================================================

        formas_validas = {
            valor
            for valor, texto
            in OperacionContable.FormaPago.choices
        }

        forma_pago = (
            datos_formulario["forma_pago"]
        )

        if forma_pago not in formas_validas:

            errores.append(
                "Debe seleccionar una forma de pago válida."
            )

        # ====================================================
        # MONTO PAGADO
        # ====================================================

        try:

            monto_pagado = Decimal(
                datos_formulario["monto_pagado"]
                or "0.00"
            )

        except (
            InvalidOperation,
            TypeError,
            ValueError,
        ):

            monto_pagado = Decimal("0.00")

            errores.append(
                "El monto pagado ingresado no es válido."
            )

        # ====================================================
        # FECHA DE PAGO
        # ====================================================

        fecha_pago = None

        if datos_formulario["fecha_pago"]:

            try:

                fecha_pago = date.fromisoformat(
                    datos_formulario["fecha_pago"]
                )

            except (ValueError, TypeError):

                errores.append(
                    "La fecha de pago no es válida."
                )

        # ====================================================
        # FECHA DE VENCIMIENTO
        # ====================================================

        fecha_vencimiento = None

        if datos_formulario["fecha_vencimiento"]:

            try:

                fecha_vencimiento = date.fromisoformat(
                    datos_formulario[
                        "fecha_vencimiento"
                    ]
                )

            except (ValueError, TypeError):

                errores.append(
                    "La fecha de vencimiento no es válida."
                )

        # ====================================================
        # CUENTA DE PAGO
        # ====================================================

        cuenta_pago = None

        if datos_formulario["cuenta_pago"]:

            cuenta_pago = (
                cuentas_pago
                .filter(
                    id=datos_formulario["cuenta_pago"]
                )
                .first()
            )

            if not cuenta_pago:

                errores.append(
                    "La cuenta de pago seleccionada "
                    "no es válida."
                )

        # ====================================================
        # CUENTA POR PAGAR
        # ====================================================

        cuenta_por_pagar = None

        if datos_formulario["cuenta_por_pagar"]:

            cuenta_por_pagar = (
                cuentas_por_pagar
                .filter(
                    id=datos_formulario[
                        "cuenta_por_pagar"
                    ]
                )
                .first()
            )

            if not cuenta_por_pagar:

                errores.append(
                    "La cuenta por pagar seleccionada "
                    "no es válida."
                )

        # ====================================================
        # PERÍODO CONTABLE
        # ====================================================

        if fecha_operacion:

            periodo = (
                PeriodoContable.objects
                .filter(
                    fecha_inicio__lte=fecha_operacion,
                    fecha_fin__gte=fecha_operacion,
                )
                .first()
            )

            if not periodo:

                errores.append(
                    "No existe un período contable "
                    "para la fecha seleccionada."
                )

            elif (
                periodo.estado
                == PeriodoContable.Estado.CERRADO
            ):

                errores.append(
                    "El período correspondiente "
                    "a esta fecha está cerrado."
                )

        # ====================================================
        # CREAR Y CONTABILIZAR
        # ====================================================

        if not errores:

            try:

                with transaction.atomic():

                    operacion = OperacionContable(
                        fecha=fecha_operacion,
                        concepto=concepto,

                        descripcion=datos_formulario[
                            "descripcion"
                        ],

                        proveedor_nombre=datos_formulario[
                            "proveedor_nombre"
                        ],

                        cliente_nombre=datos_formulario[
                            "cliente_nombre"
                        ],

                        tipo_documento=datos_formulario[
                            "tipo_documento"
                        ],

                        numero_documento=datos_formulario[
                            "numero_documento"
                        ],

                        importe_total=importe_total,

                        forma_pago=forma_pago,

                        monto_pagado=monto_pagado,

                        fecha_pago=fecha_pago,

                        cuenta_pago=cuenta_pago,

                        cuenta_por_pagar=cuenta_por_pagar,

                        fecha_vencimiento=fecha_vencimiento,

                        observacion=datos_formulario[
                            "observacion"
                        ],

                        estado=(
                            OperacionContable
                            .Estado
                            .BORRADOR
                        ),
                    )

                    operacion.full_clean()
                    operacion.save()

                    asiento = (
                        contabilizar_operacion_contable(
                            operacion
                        )
                    )

                messages.success(
                    request,
                    (
                        "Operación registrada y "
                        "contabilizada correctamente. "
                        f"Asiento N.° {asiento.numero}."
                    )
                )

                return redirect(
                    "contabilidad:registrar_gasto_operacion"
                )

            except ValidationError as exc:

                if hasattr(
                    exc,
                    "message_dict",
                ):

                    for campo, mensajes_error in (
                        exc.message_dict.items()
                    ):

                        for mensaje in mensajes_error:

                            errores.append(
                                mensaje
                            )

                else:

                    errores.extend(
                        exc.messages
                    )

            except Exception as exc:

                errores.append(
                    "No fue posible registrar "
                    f"la operación. Detalle: {exc}"
                )

        # ====================================================
        # MENSAJES
        # ====================================================

        for error in errores:

            messages.error(
                request,
                error,
            )

    # ========================================================
    # CONTEXTO
    # ========================================================

    context = {
        "conceptos": conceptos,
        "cuentas_pago": cuentas_pago,
        "cuentas_por_pagar": cuentas_por_pagar,
        "formas_pago": OperacionContable.FormaPago.choices,
        "datos": datos_formulario,
        "clasificacion_conceptos": clasificacion_conceptos,
    }

    return render(
        request,
        "contabilidad/registrar_gasto_operacion.html",
        context,
    )

def registrar_nota_credito(request):

    from decimal import Decimal, InvalidOperation
    from datetime import date

    from django.db import transaction
    from django.db.models import Max, Q
    from django.core.exceptions import ValidationError
    from django.contrib import messages
    from django.shortcuts import render, redirect, get_object_or_404

    from core.models import TicketVenta

    ticket = None
    numero_buscado = ""

    # ========================================================
    # CUENTAS DISPONIBLES PARA DEVOLUCIÓN DE DINERO
    # ========================================================

    cuentas_devolucion = (
        CuentaContable.objects
        .filter(
            activo=True,
            acepta_movimientos=True,
        )
        .filter(
            Q(codigo__startswith="101")
            |
            Q(codigo__startswith="104")
        )
        .order_by("codigo")
    )

    # ========================================================
    # BÚSQUEDA DEL TICKET
    # ========================================================

    if request.method == "GET":

        numero_buscado = (
            request.GET.get("ticket", "")
            .strip()
        )

        if numero_buscado:

            try:

                numero_int = int(numero_buscado)

                ticket = (
                    TicketVenta.objects
                    .filter(numero=numero_int)
                    .select_related("cliente")
                    .prefetch_related(
                        "detalles",
                        "detalles__producto",
                    )
                    .order_by("-id")
                    .first()
                )

                if not ticket:

                    messages.error(
                        request,
                        "No se encontró el ticket indicado."
                    )

            except ValueError:

                messages.error(
                    request,
                    "Ingrese un número de ticket válido."
                )

    # ========================================================
    # REGISTRAR NOTA DE CRÉDITO
    # ========================================================

    if request.method == "POST":

        ticket_id = request.POST.get(
            "ticket_id"
        )

        ticket = get_object_or_404(
            TicketVenta.objects
            .select_related("cliente")
            .prefetch_related(
                "detalles",
                "detalles__producto",
            ),
            id=ticket_id,
        )

        numero_buscado = str(
            ticket.numero
        )

        fecha_emision = (
            request.POST.get(
                "fecha_emision",
                ""
            )
            .strip()
        )

        motivo = (
            request.POST.get(
                "motivo",
                ""
            )
            .strip()
        )

        descripcion = (
            request.POST.get(
                "descripcion",
                ""
            )
            .strip()
        )

        observacion = (
            request.POST.get(
                "observacion",
                ""
            )
            .strip()
        )

        cuenta_devolucion_id = (
            request.POST.get(
                "cuenta_devolucion"
            )
        )

        try:

            monto_total = Decimal(
                request.POST.get(
                    "monto_total",
                    "0"
                )
                or "0"
            )

            monto_aplicado_saldo = Decimal(
                request.POST.get(
                    "monto_aplicado_saldo",
                    "0"
                )
                or "0"
            )

            monto_devuelto = Decimal(
                request.POST.get(
                    "monto_devuelto",
                    "0"
                )
                or "0"
            )

        except (
            InvalidOperation,
            TypeError,
            ValueError,
        ):

            messages.error(
                request,
                "Los importes ingresados no son válidos."
            )

            return render(
                request,
                "contabilidad/registrar_nota_credito.html",
                {
                    "ticket": ticket,
                    "numero_buscado": numero_buscado,
                    "motivos": NotaCredito.Motivo.choices,
                    "cuentas_devolucion": cuentas_devolucion,
                    "datos": request.POST,
                },
            )

        # ====================================================
        # FECHA
        # ====================================================

        try:

            fecha = date.fromisoformat(
                fecha_emision
            )

        except ValueError:

            messages.error(
                request,
                "La fecha de emisión no es válida."
            )

            return render(
                request,
                "contabilidad/registrar_nota_credito.html",
                {
                    "ticket": ticket,
                    "numero_buscado": numero_buscado,
                    "motivos": NotaCredito.Motivo.choices,
                    "cuentas_devolucion": cuentas_devolucion,
                    "datos": request.POST,
                },
            )

        if fecha < ticket.fecha_emision:

            messages.error(
                request,
                "La nota de crédito no puede tener una "
                "fecha anterior al ticket original."
            )

            return render(
                request,
                "contabilidad/registrar_nota_credito.html",
                {
                    "ticket": ticket,
                    "numero_buscado": numero_buscado,
                    "motivos": NotaCredito.Motivo.choices,
                    "cuentas_devolucion": cuentas_devolucion,
                    "datos": request.POST,
                },
            )

        # ====================================================
        # CUENTA DE DEVOLUCIÓN
        # ====================================================

        cuenta_devolucion = None

        if cuenta_devolucion_id:

            cuenta_devolucion = get_object_or_404(
                CuentaContable,
                id=cuenta_devolucion_id,
                activo=True,
                acepta_movimientos=True,
            )

        # ====================================================
        # DETALLES SELECCIONADOS
        # ====================================================

        detalles_preparados = []

        suma_detalles = Decimal(
            "0.00"
        )

        for detalle_ticket in ticket.detalles.all():

            cantidad_raw = (
                request.POST.get(
                    f"cantidad_{detalle_ticket.id}",
                    ""
                )
                .strip()
            )

            importe_raw = (
                request.POST.get(
                    f"importe_{detalle_ticket.id}",
                    ""
                )
                .strip()
            )

            devuelve_stock = (
                request.POST.get(
                    f"devuelve_stock_{detalle_ticket.id}"
                )
                == "on"
            )

            if (
                not cantidad_raw
                and not importe_raw
            ):
                continue

            try:

                cantidad = Decimal(
                    cantidad_raw or "0"
                )

                importe = Decimal(
                    importe_raw or "0"
                )

            except (
                InvalidOperation,
                TypeError,
                ValueError,
            ):

                messages.error(
                    request,
                    (
                        "Cantidad o importe inválido en: "
                        f"{detalle_ticket.descripcion}"
                    ),
                )

                return render(
                    request,
                    "contabilidad/registrar_nota_credito.html",
                    {
                        "ticket": ticket,
                        "numero_buscado": numero_buscado,
                        "motivos": NotaCredito.Motivo.choices,
                        "cuentas_devolucion": cuentas_devolucion,
                        "datos": request.POST,
                    },
                )

            if (
                cantidad <= Decimal("0.00")
                or importe <= Decimal("0.00")
            ):

                messages.error(
                    request,
                    (
                        "La cantidad y el importe deben ser "
                        "mayores que cero en: "
                        f"{detalle_ticket.descripcion}"
                    ),
                )

                return render(
                    request,
                    "contabilidad/registrar_nota_credito.html",
                    {
                        "ticket": ticket,
                        "numero_buscado": numero_buscado,
                        "motivos": NotaCredito.Motivo.choices,
                        "cuentas_devolucion": cuentas_devolucion,
                        "datos": request.POST,
                    },
                )

            detalles_preparados.append({
                "detalle_ticket":
                    detalle_ticket,
                "cantidad":
                    cantidad,
                "importe":
                    importe,
                "devuelve_stock":
                    devuelve_stock,
            })

            suma_detalles += importe

        # ====================================================
        # VALIDACIONES
        # ====================================================

        if not detalles_preparados:

            messages.error(
                request,
                "Debe seleccionar al menos un producto "
                "o concepto del ticket."
            )

            return render(
                request,
                "contabilidad/registrar_nota_credito.html",
                {
                    "ticket": ticket,
                    "numero_buscado": numero_buscado,
                    "motivos": NotaCredito.Motivo.choices,
                    "cuentas_devolucion": cuentas_devolucion,
                    "datos": request.POST,
                },
            )

        if suma_detalles != monto_total:

            messages.error(
                request,
                (
                    "La suma de los importes de los detalles "
                    f"(S/ {suma_detalles:.2f}) debe ser igual "
                    f"al total de la nota "
                    f"(S/ {monto_total:.2f})."
                ),
            )

            return render(
                request,
                "contabilidad/registrar_nota_credito.html",
                {
                    "ticket": ticket,
                    "numero_buscado": numero_buscado,
                    "motivos": NotaCredito.Motivo.choices,
                    "cuentas_devolucion": cuentas_devolucion,
                    "datos": request.POST,
                },
            )

        # ====================================================
        # GUARDAR
        # ====================================================

        try:

            with transaction.atomic():

                ultimo_numero = (
                    NotaCredito.objects
                    .aggregate(
                        maximo=Max("numero")
                    )
                    .get("maximo")
                    or 0
                )

                nota = NotaCredito(
                    numero=ultimo_numero + 1,
                    ticket=ticket,
                    fecha_emision=fecha,
                    motivo=motivo,
                    descripcion=descripcion,
                    monto_total=monto_total,
                    monto_aplicado_saldo=monto_aplicado_saldo,
                    monto_devuelto=monto_devuelto,
                    cuenta_devolucion=cuenta_devolucion,
                    observacion=observacion,
                    estado=NotaCredito.Estado.BORRADOR,
                )

                nota.full_clean()

                nota.save()

                for item in detalles_preparados:

                    detalle_nc = DetalleNotaCredito(
                        nota_credito=nota,
                        detalle_ticket=item[
                            "detalle_ticket"
                        ],
                        cantidad=item[
                            "cantidad"
                        ],
                        importe=item[
                            "importe"
                        ],
                        devuelve_stock=item[
                            "devuelve_stock"
                        ],
                    )

                    detalle_nc.full_clean()

                    detalle_nc.save()

        except ValidationError as error:

            if hasattr(
                error,
                "message_dict"
            ):

                mensajes_error = []

                for errores in (
                    error.message_dict.values()
                ):

                    mensajes_error.extend(
                        errores
                    )

                mensaje_error = " ".join(
                    mensajes_error
                )

            else:

                mensaje_error = " ".join(
                    error.messages
                )

            messages.error(
                request,
                mensaje_error
            )

            return render(
                request,
                "contabilidad/registrar_nota_credito.html",
                {
                    "ticket": ticket,
                    "numero_buscado": numero_buscado,
                    "motivos": NotaCredito.Motivo.choices,
                    "cuentas_devolucion": cuentas_devolucion,
                    "datos": request.POST,
                },
            )

        messages.success(
            request,
            (
                f"Nota de crédito N.º "
                f"{nota.numero:06d} registrada "
                f"correctamente en borrador."
            ),
        )

        return redirect(
            f"{request.path}?ticket={ticket.numero}"
        )

    # ========================================================
    # GET
    # ========================================================

    return render(
        request,
        "contabilidad/registrar_nota_credito.html",
        {
            "ticket": ticket,
            "numero_buscado": numero_buscado,
            "motivos": NotaCredito.Motivo.choices,
            "cuentas_devolucion": cuentas_devolucion,
            "datos": {},
        },
    )

def lista_notas_credito(request):

    notas = (
        NotaCredito.objects
        .select_related(
            "ticket",
            "ticket__cliente",
            "cuenta_devolucion",
            "asiento",
        )
        .prefetch_related(
            "detalles",
            "detalles__detalle_ticket",
        )
        .order_by(
            "-fecha_emision",
            "-numero",
        )
    )

    return render(
        request,
        "contabilidad/lista_notas_credito.html",
        {
            "notas": notas,
        },
    )


def contabilizar_nota_credito_view(
    request,
    nota_id,
):

    if request.method != "POST":

        messages.error(
            request,
            "La contabilización debe realizarse mediante el botón correspondiente."
        )

        return redirect(
            "contabilidad:lista_notas_credito"
        )

    nota = get_object_or_404(
        NotaCredito.objects.select_related(
            "ticket",
            "cuenta_devolucion",
            "asiento",
        ),
        id=nota_id,
    )

    try:

        asiento = contabilizar_nota_credito(
            nota
        )

    except ValidationError as error:

        if hasattr(
            error,
            "message_dict"
        ):

            errores = []

            for lista in (
                error.message_dict.values()
            ):

                errores.extend(
                    lista
                )

            mensaje = " ".join(
                errores
            )

        else:

            mensaje = " ".join(
                error.messages
            )

        messages.error(
            request,
            mensaje,
        )

        return redirect(
            "contabilidad:lista_notas_credito"
        )

    messages.success(
        request,
        (
            f"Nota de crédito N.º "
            f"{nota.numero:06d} contabilizada correctamente. "
            f"Asiento N.º {asiento.numero}."
        ),
    )

    return redirect(
        "contabilidad:lista_notas_credito"
    )


def anular_nota_credito(request, nota_id):

    nota = get_object_or_404(
        NotaCredito,
        id=nota_id,
    )

    if request.method != "POST":

        messages.error(
            request,
            "La anulación de una nota de crédito debe realizarse mediante POST."
        )

        return redirect(
            "contabilidad:lista_notas_credito"
        )

    # Solo se pueden anular notas que todavía están en borrador.
    if nota.estado != NotaCredito.Estado.BORRADOR:

        messages.error(
            request,
            "Solo se pueden anular notas de crédito que se encuentren en borrador."
        )

        return redirect(
            "contabilidad:lista_notas_credito"
        )

    with transaction.atomic():

        nota.estado = NotaCredito.Estado.ANULADA

        nota.save(
            update_fields=[
                "estado",
            ]
        )

    messages.success(
        request,
        f"Nota de crédito N.º {nota.numero:06d} anulada correctamente."
    )

    return redirect(
        "contabilidad:lista_notas_credito"
    )

# ============================================================
# CRUD DE CONCEPTOS CONTABLES
# ============================================================

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Q
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.views.decorators.http import require_POST

from .models import ConceptoOperacion
from .forms import ConceptoOperacionForm


def es_administrador_contable(user):
    return user.is_authenticated and user.is_superuser


# ============================================================
# 1. LISTAR Y BUSCAR CONCEPTOS
# ============================================================

@user_passes_test(es_administrador_contable)
def lista_conceptos_contables(request):

    busqueda = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "TODOS")

    conceptos = (
        ConceptoOperacion.objects
        .select_related(
            "concepto_padre",
            "cuenta_contable",
            "categoria_gerencial",
            "centro_costo",
        )
        .all()
    )

    if busqueda:
        conceptos = conceptos.filter(
            Q(codigo__icontains=busqueda)
            | Q(nombre__icontains=busqueda)
            | Q(palabras_clave__icontains=busqueda)
            | Q(sinonimos__icontains=busqueda)
            | Q(cuenta_contable__codigo__icontains=busqueda)
        )

    if estado == "ACTIVOS":
        conceptos = conceptos.filter(activo=True)

    elif estado == "INACTIVOS":
        conceptos = conceptos.filter(activo=False)

    conceptos = conceptos.order_by(
        "orden",
        "codigo",
        "nombre",
    )

    return render(
        request,
        "contabilidad/lista_conceptos_contables.html",
        {
            "conceptos": conceptos,
            "busqueda": busqueda,
            "estado": estado,
        },
    )


# ============================================================
# 2. CREAR CONCEPTO
# ============================================================

@user_passes_test(es_administrador_contable)
def crear_concepto_contable(request):

    if request.method == "POST":

        form = ConceptoOperacionForm(request.POST)

        if form.is_valid():

            concepto = form.save()

            messages.success(
                request,
                f"Concepto '{concepto.nombre}' creado correctamente.",
            )

            return redirect(
                "contabilidad:lista_conceptos_contables"
            )

    else:
        form = ConceptoOperacionForm()

    return render(
        request,
        "contabilidad/form_concepto_contable.html",
        {
            "form": form,
            "titulo": "Nuevo concepto contable",
            "modo": "CREAR",
        },
    )


# ============================================================
# 3. EDITAR CONCEPTO
# ============================================================

@user_passes_test(es_administrador_contable)
def editar_concepto_contable(request, concepto_id):

    concepto = get_object_or_404(
        ConceptoOperacion,
        pk=concepto_id,
    )

    if request.method == "POST":

        form = ConceptoOperacionForm(
            request.POST,
            instance=concepto,
        )

        if form.is_valid():

            concepto = form.save()

            messages.success(
                request,
                f"Concepto '{concepto.nombre}' actualizado correctamente.",
            )

            return redirect(
                "contabilidad:lista_conceptos_contables"
            )

    else:

        form = ConceptoOperacionForm(
            instance=concepto
        )

    return render(
        request,
        "contabilidad/form_concepto_contable.html",
        {
            "form": form,
            "concepto": concepto,
            "titulo": f"Editar concepto: {concepto.nombre}",
            "modo": "EDITAR",
        },
    )


# ============================================================
# 4. ACTIVAR / DESACTIVAR CONCEPTO
# ============================================================

@user_passes_test(es_administrador_contable)
@require_POST
def cambiar_estado_concepto_contable(request, concepto_id):

    concepto = get_object_or_404(
        ConceptoOperacion,
        pk=concepto_id,
    )

    concepto.activo = not concepto.activo

    concepto.save(
        update_fields=["activo"]
    )

    if concepto.activo:

        messages.success(
            request,
            f"Concepto '{concepto.nombre}' activado correctamente.",
        )

    else:

        messages.success(
            request,
            f"Concepto '{concepto.nombre}' desactivado correctamente.",
        )

    return redirect(
        "contabilidad:lista_conceptos_contables"
    )