from decimal import Decimal

from django.core.exceptions import ValidationError
from core.models import KardexMovimiento
from django.db import transaction
from django.utils import timezone
from .models import (
    AsientoContable,
    PeriodoContable,
    PropuestaCostoVenta,
    DetallePropuestaCostoVenta,
    CompraDirectaVenta,
    ServicioTerceroVenta,
    CuentaContable,
    CategoriaGerencial,
    CentroCosto,
    DetalleAsiento,
    PagoProveedor,
    OperacionContable,
    PagoOperacionContable,
    NotaCredito,
)


from decimal import Decimal, ROUND_HALF_UP




@transaction.atomic
def contabilizar_asiento(asiento: AsientoContable) -> AsientoContable:
    """
    Valida un asiento y, si cumple todas las reglas contables,
    cambia su estado de BORRADOR a CONTABILIZADO.
    """

    # ========================================================
    # 1. VALIDAR ESTADO DEL ASIENTO
    # ========================================================

    if asiento.estado == AsientoContable.Estado.ANULADO:
        raise ValidationError(
            "No se puede contabilizar un asiento anulado."
        )

    if asiento.estado == AsientoContable.Estado.CONTABILIZADO:
        raise ValidationError(
            "El asiento ya se encuentra contabilizado."
        )

    # ========================================================
    # 2. VALIDAR PERIODO
    # ========================================================

    if asiento.periodo.estado == PeriodoContable.Estado.CERRADO:
        raise ValidationError(
            "No se puede contabilizar un asiento "
            "en un periodo cerrado."
        )

    if not (
        asiento.periodo.fecha_inicio
        <= asiento.fecha
        <= asiento.periodo.fecha_fin
    ):
        raise ValidationError(
            "La fecha del asiento no pertenece "
            "al periodo contable seleccionado."
        )

    # ========================================================
    # 3. OBTENER LAS LÍNEAS DEL ASIENTO
    # ========================================================

    detalles = list(
        asiento.detalles
        .select_related(
            "cuenta",
            "categoria_gerencial",
            "centro_costo",
        )
        .order_by("secuencia")
    )

    if len(detalles) < 2:
        raise ValidationError(
            "El asiento debe contener al menos dos líneas."
        )

    # ========================================================
    # 4. VALIDAR LAS LÍNEAS
    # ========================================================

    total_debe = Decimal("0.00")
    total_haber = Decimal("0.00")

    for detalle in detalles:

        cuenta = detalle.cuenta

        if not cuenta.activo:
            raise ValidationError(
                f"La cuenta {cuenta.codigo} - "
                f"{cuenta.nombre} está inactiva."
            )

        if not cuenta.acepta_movimientos:
            raise ValidationError(
                f"La cuenta {cuenta.codigo} - "
                f"{cuenta.nombre} es agrupadora "
                "y no acepta movimientos."
            )

        if detalle.debe < 0 or detalle.haber < 0:
            raise ValidationError(
                "Debe y Haber no pueden contener "
                "importes negativos."
            )

        if detalle.debe > 0 and detalle.haber > 0:
            raise ValidationError(
                f"La línea {detalle.secuencia} contiene "
                "importe simultáneamente en Debe y Haber."
            )

        if detalle.debe == 0 and detalle.haber == 0:
            raise ValidationError(
                f"La línea {detalle.secuencia} "
                "no contiene ningún importe."
            )

        total_debe += detalle.debe
        total_haber += detalle.haber

    # ========================================================
    # 5. VALIDAR PARTIDA DOBLE
    # ========================================================

    if total_debe <= 0:
        raise ValidationError(
            "El total del Debe debe ser mayor que cero."
        )

    if total_haber <= 0:
        raise ValidationError(
            "El total del Haber debe ser mayor que cero."
        )

    if total_debe != total_haber:
        raise ValidationError(
            f"El asiento está descuadrado. "
            f"Debe: S/ {total_debe:.2f} | "
            f"Haber: S/ {total_haber:.2f}"
        )

    # ========================================================
    # 6. CONTABILIZAR
    # ========================================================

    asiento.estado = AsientoContable.Estado.CONTABILIZADO

    asiento.save(
        update_fields=[
            "estado",
            "actualizado_en",
        ]
    )

    return asiento
@transaction.atomic
def contabilizar_pago_proveedor(
    pago: PagoProveedor,
) -> AsientoContable:
    """
    Contabiliza un pago posterior realizado a un proveedor.

    Asiento:

        DEBE:
            Cuenta por pagar al proveedor

        HABER:
            Caja / Banco

    Ejemplo:

        42105 Proveedores procesos ópticos     5.00
            10101 Caja                              5.00

    El pago debe existir previamente con estado REGISTRADO.
    """

    # ========================================================
    # 1. VALIDAR ESTADO DEL PAGO
    # ========================================================

    if pago.estado == PagoProveedor.Estado.ANULADO:
        raise ValidationError(
            "No se puede contabilizar un pago anulado."
        )

    if pago.estado == PagoProveedor.Estado.CONTABILIZADO:
        raise ValidationError(
            "El pago ya se encuentra contabilizado."
        )

    if pago.estado != PagoProveedor.Estado.REGISTRADO:
        raise ValidationError(
            "El pago debe encontrarse en estado REGISTRADO."
        )

    # ========================================================
    # 2. OBTENER COMPRA
    # ========================================================

    compra = pago.compra

    if (
        compra.estado
        != CompraDirectaVenta.Estado.CONTABILIZADA
    ):
        raise ValidationError(
            "La compra debe estar contabilizada antes "
            "de contabilizar el pago al proveedor."
        )

    # ========================================================
    # 3. VALIDAR CUENTA POR PAGAR
    # ========================================================

# ====================================================
# VALIDAR CUENTA POR PAGAR
# ====================================================

    if self.cuenta_por_pagar_id:

        if not self.cuenta_por_pagar.activo:
            errores["cuenta_por_pagar"] = (
                "La cuenta por pagar está inactiva."
            )

        elif not self.cuenta_por_pagar.acepta_movimientos:
            errores["cuenta_por_pagar"] = (
                "La cuenta por pagar no acepta movimientos."
            )

        elif (
            self.cuenta_por_pagar.tipo
            != CuentaContable.TipoCuenta.PASIVO
        ):
            errores["cuenta_por_pagar"] = (
                "La cuenta por pagar debe ser una cuenta "
                "de pasivo."
            )

    # ========================================================
    # 4. VALIDAR CUENTA DE PAGO
    # ========================================================

    # ====================================================
    # VALIDAR CUENTA DE PAGO
    # ====================================================

    if self.cuenta_pago_id:

        if not self.cuenta_pago.activo:
            errores["cuenta_pago"] = (
                "La cuenta de pago está inactiva."
            )

        elif not self.cuenta_pago.acepta_movimientos:
            errores["cuenta_pago"] = (
                "La cuenta de pago no acepta movimientos."
            )

        elif (
            self.cuenta_pago.tipo
            != CuentaContable.TipoCuenta.ACTIVO
        ):
            errores["cuenta_pago"] = (
                "La cuenta de pago debe ser una cuenta de activo "
                "correspondiente a Caja o Bancos."
            )
        # ========================================================
        # 5. VALIDAR MONTO
        # ========================================================

        if pago.monto is None:
            raise ValidationError(
                "El pago no tiene un monto informado."
            )

        if pago.monto <= Decimal("0.00"):
            raise ValidationError(
                "El monto del pago debe ser mayor que cero."
            )

        # ========================================================
        # 6. OBTENER PERÍODO CONTABLE DEL PAGO
        # ========================================================

        periodo = (
            PeriodoContable.objects
            .filter(
                fecha_inicio__lte=pago.fecha_pago,
                fecha_fin__gte=pago.fecha_pago,
            )
            .first()
        )

        if not periodo:
            raise ValidationError(
                "No existe un período contable para "
                f"la fecha {pago.fecha_pago:%d/%m/%Y}."
            )

        if periodo.estado == PeriodoContable.Estado.CERRADO:
            raise ValidationError(
                f"El período {periodo} se encuentra cerrado."
            )

        # ========================================================
        # 7. EVITAR DUPLICIDAD DEL ASIENTO
        # ========================================================

        asiento_existente = (
            AsientoContable.objects
            .filter(
                origen="PAGO_PROVEEDOR",
                origen_id=pago.id,
            )
            .exclude(
                estado=AsientoContable.Estado.ANULADO
            )
            .first()
        )

        if asiento_existente:
            raise ValidationError(
                "Ya existe un asiento contable para este "
                "pago al proveedor."
            )

        # ========================================================
        # 8. GENERAR NÚMERO DEL ASIENTO
        # ========================================================

        ultimo_numero = (
            AsientoContable.objects
            .filter(
                periodo=periodo
            )
            .order_by("-numero")
            .values_list(
                "numero",
                flat=True,
            )
            .first()
        )

        numero = (
            ultimo_numero or 0
        ) + 1

        # ========================================================
        # 9. CREAR ASIENTO EN BORRADOR
        # ========================================================

        proveedor = (
            compra.proveedor_nombre.strip()
            if compra.proveedor_nombre
            else "Proveedor"
        )

        documento = ""

        if compra.numero_documento:
            documento = (
                f" - {compra.numero_documento}"
            )

        asiento = AsientoContable.objects.create(
            periodo=periodo,
            numero=numero,
            fecha=pago.fecha_pago,
            glosa=(
                f"Pago a proveedor {proveedor}"
                f"{documento}"
            ),
            estado=AsientoContable.Estado.BORRADOR,
            origen="PAGO_PROVEEDOR",
            origen_id=pago.id,
        )

        # ========================================================
        # 10. DEBE - CUENTA POR PAGAR
        # ========================================================

        DetalleAsiento.objects.create(
            asiento=asiento,
            secuencia=1,
            cuenta=cuenta_proveedor,
            debe=pago.monto,
            haber=Decimal("0.00"),
        )

        # ========================================================
        # 11. HABER - CAJA / BANCO
        # ========================================================

        DetalleAsiento.objects.create(
            asiento=asiento,
            secuencia=2,
            cuenta=cuenta_pago,
            debe=Decimal("0.00"),
            haber=pago.monto,
        )

        # ========================================================
        # 12. CONTABILIZAR ASIENTO
        # ========================================================

        contabilizar_asiento(
            asiento
        )

        # ========================================================
        # 13. ACTUALIZAR PAGO
        # ========================================================

        pago.estado = (
            PagoProveedor.Estado.CONTABILIZADO
        )

        pago.contabilizado_en = timezone.now()

        pago.save(
            update_fields=[
                "estado",
                "contabilizado_en",
            ]
        )

        return asiento


@transaction.atomic
def generar_propuesta_costo_venta(ticket):
    """
    Genera o actualiza la propuesta de costo de venta
    correspondiente a un TicketVenta.

    Prioridad para obtener el costo:
    1. Kardex OUT asociado al ticket y producto.
    2. Costo promedio ponderado del producto.
    3. Si no existe costo, dejarlo vacío para ingreso manual.

    Además:
    - Si la venta contiene lunas o monturas, propone:
        * Medida de vista tercerizada
        * Biselado tercerizado
      ambos inicialmente con costo S/ 0.00.
    """

    # ========================================================
    # 1. CREAR O RECUPERAR LA PROPUESTA
    # ========================================================

    propuesta, creada = PropuestaCostoVenta.objects.get_or_create(
        ticket=ticket,
        defaults={
            "estado": PropuestaCostoVenta.Estado.PENDIENTE,
        },
    )

    # Si ya fue contabilizada, no recalculamos nada.
    if propuesta.estado == PropuestaCostoVenta.Estado.CONTABILIZADA:
        return propuesta

    # ========================================================
    # 2. OBTENER DETALLES DEL TICKET
    # ========================================================

    detalles_ticket = list(
        ticket.detalles
        .select_related("producto")
        .all()
    )

    # Estas variables servirán después para decidir
    # si proponemos servicios de terceros.
    hay_lunas = False
    hay_monturas = False

    # ========================================================
    # 3. RECORRER LOS DETALLES DEL TICKET
    # ========================================================

    for detalle_ticket in detalles_ticket:

        producto = detalle_ticket.producto

        costo_unitario = None

        origen_costo = (
            DetallePropuestaCostoVenta
            .OrigenCosto
            .SIN_COSTO
        )

        observacion = ""

        descripcion_ticket = (
            detalle_ticket.descripcion or ""
        ).strip()

        descripcion_ticket_lower = (
            descripcion_ticket.lower()
        )

        # ====================================================
        # 4. DETECTAR SI EL DETALLE ES LUNA O MONTURA
        # ====================================================

        if producto is None:

            palabras_lunas = (
                "monofocal",
                "bifocal",
                "multifocal",
                "luna",
                "resina",
                "policarbonato",
                "blue",
                "fotocrom",
                "transition",
                "antireflex",
                "antirreflejo",
            )

            if any(
                palabra in descripcion_ticket_lower
                for palabra in palabras_lunas
            ):
                hay_lunas = True

        else:

            tipo_producto = (
                producto.tipo or ""
            ).strip().lower()

            descripcion_producto = (
                producto.descripcion or ""
            ).strip().lower()

            texto_producto = (
                f"{tipo_producto} "
                f"{descripcion_producto}"
            )

            if "montura" in texto_producto:
                hay_monturas = True

        # ====================================================
        # 5. SI EXISTE PRODUCTO, BUSCAR COSTO
        # ====================================================

        if producto:

            # ------------------------------------------------
            # PRIORIDAD 1:
            # KARDEX OUT ASOCIADO A ESA VENTA
            # ------------------------------------------------

            kardex = (
                KardexMovimiento.objects
                .filter(
                    ticket=ticket,
                    producto=producto,
                    tipo="OUT",
                )
                .order_by("-fecha")
                .first()
            )

            if (
                kardex
                and kardex.costo_unitario is not None
                and kardex.costo_unitario > 0
            ):

                costo_unitario = kardex.costo_unitario

                origen_costo = (
                    DetallePropuestaCostoVenta
                    .OrigenCosto
                    .KARDEX
                )

                observacion = (
                    "Costo tomado del Kardex "
                    "de salida asociado a la venta."
                )

            # ------------------------------------------------
            # PRIORIDAD 2:
            # COSTO PROMEDIO PONDERADO
            # ------------------------------------------------

            if costo_unitario is None:

                if (
                    producto.costo_promedio is not None
                    and producto.costo_promedio > 0
                ):

                    costo_unitario = (
                        producto.costo_promedio
                    )

                    origen_costo = (
                        DetallePropuestaCostoVenta
                        .OrigenCosto
                        .PROMEDIO
                    )

                    observacion = (
                        "Costo tomado del costo promedio "
                        "ponderado vigente del producto."
                    )

        # ====================================================
        # 6. SI NO HAY COSTO, QUEDA PENDIENTE
        # ====================================================

        if costo_unitario is None:

            origen_costo = (
                DetallePropuestaCostoVenta
                .OrigenCosto
                .SIN_COSTO
            )

            if producto:

                observacion = (
                    "No se encontró costo en Kardex ni "
                    "costo promedio. Requiere ingreso manual."
                )

            else:

                observacion = (
                    "El detalle del ticket no está asociado "
                    "a un producto. Revisar si requiere "
                    "costo manual."
                )

        # ====================================================
        # 7. CREAR O ACTUALIZAR EL DETALLE DE COSTO
        # ====================================================

        DetallePropuestaCostoVenta.objects.update_or_create(
            detalle_ticket=detalle_ticket,
            defaults={
                "propuesta": propuesta,
                "producto": producto,
                "cantidad": detalle_ticket.cantidad,
                "costo_unitario": costo_unitario,
                "origen_costo": origen_costo,
                "validado": False,
                "observacion": observacion,
            },
        )

    # ========================================================
    # 8. PROPUESTAS AUTOMÁTICAS DE SERVICIOS DE TERCEROS
    # ========================================================

    if hay_lunas or hay_monturas:

        # ----------------------------------------------------
        # MEDIDA DE VISTA TERCERIZADA
        # ----------------------------------------------------

        ServicioTerceroVenta.objects.get_or_create(
            propuesta=propuesta,
            tipo_servicio=(
                ServicioTerceroVenta
                .TipoServicio
                .MEDIDA_VISTA
            ),
            defaults={
                "descripcion": (
                    "Medida de vista tercerizada"
                ),
                "costo": Decimal("0.00"),
                "estado": (
                    ServicioTerceroVenta
                    .Estado
                    .PROPUESTO
                ),
                "creado_automaticamente": True,
            },
        )

        # ----------------------------------------------------
        # BISELADO TERCERIZADO
        # ----------------------------------------------------

        ServicioTerceroVenta.objects.get_or_create(
            propuesta=propuesta,
            tipo_servicio=(
                ServicioTerceroVenta
                .TipoServicio
                .BISELADO
            ),
            defaults={
                "descripcion": (
                    "Biselado tercerizado"
                ),
                "costo": Decimal("0.00"),
                "estado": (
                    ServicioTerceroVenta
                    .Estado
                    .PROPUESTO
                ),
                "creado_automaticamente": True,
            },
        )

    # ========================================================
    # 9. MANTENER PROPUESTA PENDIENTE
    # ========================================================

    propuesta.estado = (
        PropuestaCostoVenta.Estado.PENDIENTE
    )

    propuesta.save(
        update_fields=[
            "estado",
        ]
    )

    return propuesta

@transaction.atomic
def contabilizar_costo_venta(propuesta):
    """
    Genera y contabiliza el asiento correspondiente
    al costo asociado a una venta validada.

    Incluye:

    1. Costos provenientes de inventario:
       Debe  -> Costo de ventas
       Haber -> Inventario

    2. Compras directas para la venta:
       - Pagada:
         Debe  -> Costo de ventas
         Haber -> Caja / Banco

       - Crédito:
         Debe  -> Costo de ventas
         Haber -> Proveedor

       - Parcial:
         Debe  -> Costo de ventas
         Haber -> Caja / Banco por lo pagado
         Haber -> Proveedor por el saldo

    3. Servicios de terceros confirmados:
       Debe  -> Procesos ópticos tercerizados
       Haber -> Caja / Banco / Proveedor

    La propuesta solo puede contabilizarse una vez.
    """

    # ========================================================
    # 1. BLOQUEAR Y RECUPERAR PROPUESTA
    # ========================================================

    propuesta = (
        PropuestaCostoVenta.objects
        .select_for_update()
        .select_related("ticket")
        .get(pk=propuesta.pk)
    )

    # ========================================================
    # 2. VALIDACIONES GENERALES
    # ========================================================

    if (
        propuesta.estado
        == PropuestaCostoVenta.Estado.CONTABILIZADA
    ):
        raise ValidationError(
            "Esta propuesta de costo ya fue contabilizada."
        )

    if (
        propuesta.estado
        != PropuestaCostoVenta.Estado.VALIDADA
    ):
        raise ValidationError(
            "La propuesta debe estar validada "
            "antes de contabilizarse."
        )

    detalles = list(
        propuesta.detalles
        .select_related(
            "producto",
            "detalle_ticket",
        )
        .order_by("id")
    )

    if not detalles:
        raise ValidationError(
            "La propuesta no tiene detalles de costo."
        )

    for detalle in detalles:

        if detalle.costo_unitario is None:
            raise ValidationError(
                f"El detalle "
                f"'{detalle.detalle_ticket.descripcion}' "
                "no tiene costo unitario."
            )

        if not detalle.validado:
            raise ValidationError(
                f"El detalle "
                f"'{detalle.detalle_ticket.descripcion}' "
                "no ha sido validado."
            )

    # ========================================================
    # 3. OBTENER TICKET Y PERIODO
    # ========================================================

    ticket = propuesta.ticket
    fecha = ticket.fecha_emision

    periodo = (
        PeriodoContable.objects
        .filter(
            anio=fecha.year,
            mes=fecha.month,
        )
        .first()
    )

    if not periodo:
        raise ValidationError(
            f"No existe periodo contable para "
            f"{fecha.month:02d}/{fecha.year}."
        )

    if (
        periodo.estado
        == PeriodoContable.Estado.CERRADO
    ):
        raise ValidationError(
            "El periodo contable de la venta está cerrado."
        )

    # ========================================================
    # 4. EVITAR DUPLICIDAD
    # ========================================================

    asiento_existente = (
        AsientoContable.objects
        .filter(
            origen="COSTO_VENTA",
            origen_id=ticket.id,
        )
        .exclude(
            estado=AsientoContable.Estado.ANULADO
        )
        .first()
    )

    if asiento_existente:
        raise ValidationError(
            f"El ticket {ticket.numero} ya tiene "
            "un asiento de costo de venta asociado."
        )

    # ========================================================
    # 5. SIGUIENTE NÚMERO DE ASIENTO
    # ========================================================

    ultimo_numero = (
        AsientoContable.objects
        .filter(periodo=periodo)
        .order_by("-numero")
        .values_list(
            "numero",
            flat=True,
        )
        .first()
    )

    numero_asiento = (
        (ultimo_numero or 0) + 1
    )

    # ========================================================
    # 6. CREAR ENCABEZADO DEL ASIENTO
    # ========================================================

    asiento = AsientoContable.objects.create(
        numero=numero_asiento,
        fecha=fecha,
        periodo=periodo,
        tipo=AsientoContable.TipoAsiento.AUTOMATICO,
        glosa=(
            f"Costo asociado a venta - "
            f"Ticket {ticket.numero:06d}"
        ),
        estado=AsientoContable.Estado.BORRADOR,
        origen="COSTO_VENTA",
        origen_id=ticket.id,
    )

    secuencia = 1

    # ========================================================
    # 7. FUNCIONES AUXILIARES
    # ========================================================

    def cuenta_costo_venta(detalle):

        producto = detalle.producto

        if producto:

            tipo = (
                producto.tipo or ""
            ).strip().lower()

            descripcion = (
                producto.descripcion or ""
            ).strip().lower()

            texto = (
                f"{tipo} {descripcion}"
            )

            if "montura" in texto:
                return CuentaContable.objects.get(
                    codigo="69101"
                )

            if "contacto" in texto:
                return CuentaContable.objects.get(
                    codigo="69103"
                )

            if (
                "líquido" in texto
                or "liquido" in texto
            ):
                return CuentaContable.objects.get(
                    codigo="69107"
                )

            if "accesorio" in texto:
                return CuentaContable.objects.get(
                    codigo="69106"
                )

        # Sin producto:
        # normalmente lunas compradas específicamente
        # para esa venta.
        return CuentaContable.objects.get(
            codigo="69102"
        )


    def cuenta_inventario(detalle):

        producto = detalle.producto

        if not producto:
            return None

        tipo = (
            producto.tipo or ""
        ).strip().lower()

        descripcion = (
            producto.descripcion or ""
        ).strip().lower()

        texto = (
            f"{tipo} {descripcion}"
        )

        if "montura" in texto:
            return CuentaContable.objects.get(
                codigo="20101"
            )

        if "contacto" in texto:
            return CuentaContable.objects.get(
                codigo="20103"
            )

        if (
            "líquido" in texto
            or "liquido" in texto
        ):
            return CuentaContable.objects.get(
                codigo="20107"
            )

        if "accesorio" in texto:
            return CuentaContable.objects.get(
                codigo="20106"
            )

        return None

    # ========================================================
    # 8. COSTOS DE MERCADERÍA / COMPONENTES
    # ========================================================

    for detalle in detalles:

        costo_total = detalle.costo_total

        if costo_total <= 0:
            continue

        cuenta_costo = (
            cuenta_costo_venta(detalle)
        )

        descripcion = (
            detalle.detalle_ticket.descripcion
        )

        # ----------------------------------------------------
        # DEBE: COSTO DE VENTA
        # ----------------------------------------------------

        DetalleAsiento.objects.create(
            asiento=asiento,
            secuencia=secuencia,
            cuenta=cuenta_costo,
            descripcion=descripcion,
            debe=costo_total,
            haber=Decimal("0.00"),
            referencia=(
                f"Ticket {ticket.numero:06d}"
            ),
        )

        secuencia += 1

        # ----------------------------------------------------
        # A. COMPRA DIRECTA
        # ----------------------------------------------------

        compra_directa = getattr(
            detalle,
            "compra_directa",
            None,
        )

        if compra_directa:

            if (
                compra_directa.estado
                == CompraDirectaVenta.Estado.CONTABILIZADA
            ):
                raise ValidationError(
                    f"La compra directa de "
                    f"'{descripcion}' "
                    "ya fue contabilizada."
                )

            # ================================================
            # A.1 COMPRA AL CRÉDITO
            # ================================================

            if (
                compra_directa.forma_pago
                == CompraDirectaVenta.FormaPago.CREDITO
            ):

                cuenta_proveedor = (
                    compra_directa.cuenta_proveedor
                )

                if not cuenta_proveedor:
                    raise ValidationError(
                        f"La compra directa de "
                        f"'{descripcion}' "
                        "no tiene cuenta por pagar."
                    )

                DetalleAsiento.objects.create(
                    asiento=asiento,
                    secuencia=secuencia,
                    cuenta=cuenta_proveedor,
                    descripcion=descripcion,
                    debe=Decimal("0.00"),
                    haber=costo_total,
                    referencia=(
                        compra_directa.numero_documento
                        or f"Ticket {ticket.numero:06d}"
                    ),
                )

                secuencia += 1

                continue

            # ================================================
            # A.2 COMPRA CON PAGO PARCIAL
            # ================================================

            if (
                compra_directa.forma_pago
                == CompraDirectaVenta.FormaPago.PARCIAL
            ):

                monto_pagado = (
                    compra_directa.monto_pagado
                    or Decimal("0.00")
                )

                saldo_pendiente = (
                    costo_total - monto_pagado
                )

                if monto_pagado <= Decimal("0.00"):
                    raise ValidationError(
                        f"La compra directa de "
                        f"'{descripcion}' "
                        "está marcada como pago parcial, "
                        "pero no tiene monto pagado."
                    )

                if monto_pagado >= costo_total:
                    raise ValidationError(
                        f"El pago parcial de "
                        f"'{descripcion}' "
                        "debe ser menor que el costo total."
                    )

                if saldo_pendiente <= Decimal("0.00"):
                    raise ValidationError(
                        f"La compra directa de "
                        f"'{descripcion}' "
                        "no tiene saldo pendiente válido."
                    )

                cuenta_pago = (
                    compra_directa.cuenta_pago
                )

                cuenta_proveedor = (
                    compra_directa.cuenta_proveedor
                )

                if not cuenta_pago:
                    raise ValidationError(
                        f"La compra directa de "
                        f"'{descripcion}' "
                        "no tiene cuenta de pago."
                    )

                if not cuenta_proveedor:
                    raise ValidationError(
                        f"La compra directa de "
                        f"'{descripcion}' "
                        "no tiene cuenta por pagar."
                    )

                # HABER: PARTE PAGADA

                DetalleAsiento.objects.create(
                    asiento=asiento,
                    secuencia=secuencia,
                    cuenta=cuenta_pago,
                    descripcion=(
                        f"{descripcion} - "
                        "Pago inicial"
                    ),
                    debe=Decimal("0.00"),
                    haber=monto_pagado,
                    referencia=(
                        compra_directa.numero_documento
                        or f"Ticket {ticket.numero:06d}"
                    ),
                )

                secuencia += 1

                # HABER: SALDO POR PAGAR

                DetalleAsiento.objects.create(
                    asiento=asiento,
                    secuencia=secuencia,
                    cuenta=cuenta_proveedor,
                    descripcion=(
                        f"{descripcion} - "
                        "Saldo por pagar"
                    ),
                    debe=Decimal("0.00"),
                    haber=saldo_pendiente,
                    referencia=(
                        compra_directa.numero_documento
                        or f"Ticket {ticket.numero:06d}"
                    ),
                )

                secuencia += 1

                continue

            # ================================================
            # A.3 COMPRA PAGADA TOTALMENTE
            # EFECTIVO / BANCO / OTRO
            # ================================================

            cuenta_pago = (
                compra_directa.cuenta_pago
            )

            if not cuenta_pago:
                raise ValidationError(
                    f"La compra directa de "
                    f"'{descripcion}' "
                    "no tiene cuenta de pago."
                )

            DetalleAsiento.objects.create(
                asiento=asiento,
                secuencia=secuencia,
                cuenta=cuenta_pago,
                descripcion=descripcion,
                debe=Decimal("0.00"),
                haber=costo_total,
                referencia=(
                    compra_directa.numero_documento
                    or f"Ticket {ticket.numero:06d}"
                ),
            )

            secuencia += 1

            continue

        # ----------------------------------------------------
        # B. KARDEX / PROMEDIO
        # ----------------------------------------------------

        if detalle.origen_costo in (
            DetallePropuestaCostoVenta
            .OrigenCosto
            .KARDEX,

            DetallePropuestaCostoVenta
            .OrigenCosto
            .PROMEDIO,
        ):

            cuenta_inv = (
                cuenta_inventario(detalle)
            )

            if not cuenta_inv:
                raise ValidationError(
                    f"No se pudo determinar la cuenta "
                    f"de inventario para "
                    f"'{descripcion}'."
                )

            DetalleAsiento.objects.create(
                asiento=asiento,
                secuencia=secuencia,
                cuenta=cuenta_inv,
                descripcion=descripcion,
                debe=Decimal("0.00"),
                haber=costo_total,
                referencia=(
                    f"Ticket {ticket.numero:06d}"
                ),
            )

            secuencia += 1

            continue

        # ----------------------------------------------------
        # C. MANUAL SIN COMPRA DIRECTA
        # ----------------------------------------------------

        raise ValidationError(
            f"El detalle '{descripcion}' "
            "tiene costo manual pero no tiene "
            "una compra directa registrada."
        )

    # ========================================================
    # 9. SERVICIOS DE TERCEROS CONFIRMADOS
    # ========================================================

    servicios = list(
        propuesta.servicios_terceros
        .select_related(
            "cuenta_pago",
            "cuenta_proveedor",
        )
        .filter(
            estado=(
                ServicioTerceroVenta
                .Estado
                .CONFIRMADO
            )
        )
        .order_by("id")
    )

    categoria_biselado = (
        CategoriaGerencial.objects.get(
            codigo="91301"
        )
    )

    categoria_medida_vista = (
        CategoriaGerencial.objects.get(
            codigo="91305"
        )
    )

    centro_taller = (
        CentroCosto.objects.get(
            codigo="TAL"
        )
    )

    centro_optometria = (
        CentroCosto.objects.get(
            codigo="OPT"
        )
    )

    for servicio in servicios:

        if servicio.costo <= 0:
            continue

        # ----------------------------------------------------
        # CLASIFICACIÓN CONTABLE Y GERENCIAL
        # ----------------------------------------------------

        categoria = None
        centro = None
        cuenta_servicio = None

        if (
            servicio.tipo_servicio
            == ServicioTerceroVenta
            .TipoServicio
            .BISELADO
        ):

            cuenta_servicio = (
                CuentaContable.objects.get(
                    codigo="63301"
                )
            )

            categoria = categoria_biselado
            centro = centro_taller

        elif (
            servicio.tipo_servicio
            == ServicioTerceroVenta
            .TipoServicio
            .MEDIDA_VISTA
        ):

            cuenta_servicio = (
                CuentaContable.objects.get(
                    codigo="63901"
                )
            )

            categoria = categoria_medida_vista
            centro = centro_optometria

        elif (
            servicio.tipo_servicio
            == ServicioTerceroVenta
            .TipoServicio
            .COLOREADO
        ):

            cuenta_servicio = (
                CuentaContable.objects.get(
                    codigo="63302"
                )
            )

        elif (
            servicio.tipo_servicio
            == ServicioTerceroVenta
            .TipoServicio
            .FLEX
        ):

            cuenta_servicio = (
                CuentaContable.objects.get(
                    codigo="63304"
                )
            )

        else:

            cuenta_servicio = (
                CuentaContable.objects.get(
                    codigo="63309"
                )
            )

        # ----------------------------------------------------
        # DEBE: SERVICIO TERCERIZADO
        # ----------------------------------------------------

        DetalleAsiento.objects.create(
            asiento=asiento,
            secuencia=secuencia,
            cuenta=cuenta_servicio,
            descripcion=servicio.descripcion,
            debe=servicio.costo,
            haber=Decimal("0.00"),
            categoria_gerencial=categoria,
            centro_costo=centro,
            referencia=(
                f"Ticket {ticket.numero:06d}"
            ),
        )

        secuencia += 1

        # ----------------------------------------------------
        # DETERMINAR CONTRAPARTIDA
        # ----------------------------------------------------

        if (
            servicio.forma_pago
            == ServicioTerceroVenta
            .FormaPago
            .CREDITO
        ):

            cuenta_contrapartida = (
                servicio.cuenta_proveedor
            )

            if not cuenta_contrapartida:
                raise ValidationError(
                    f"El servicio "
                    f"'{servicio.descripcion}' "
                    "no tiene cuenta por pagar."
                )

        else:

            cuenta_contrapartida = (
                servicio.cuenta_pago
            )

            if not cuenta_contrapartida:
                raise ValidationError(
                    f"El servicio "
                    f"'{servicio.descripcion}' "
                    "no tiene cuenta de pago."
                )

        # ----------------------------------------------------
        # HABER
        # ----------------------------------------------------

        DetalleAsiento.objects.create(
            asiento=asiento,
            secuencia=secuencia,
            cuenta=cuenta_contrapartida,
            descripcion=servicio.descripcion,
            debe=Decimal("0.00"),
            haber=servicio.costo,
            referencia=(
                f"Ticket {ticket.numero:06d}"
            ),
        )

        secuencia += 1

    # ========================================================
    # 10. CONTABILIZAR ASIENTO
    # ========================================================

    contabilizar_asiento(asiento)

    # ========================================================
    # 11. ACTUALIZAR COMPRAS DIRECTAS
    # ========================================================

    for detalle in detalles:

        compra_directa = getattr(
            detalle,
            "compra_directa",
            None,
        )

        if compra_directa:

            compra_directa.estado = (
                CompraDirectaVenta
                .Estado
                .CONTABILIZADA
            )

            compra_directa.contabilizado_en = (
                timezone.now()
            )

            compra_directa.save(
                update_fields=[
                    "estado",
                    "contabilizado_en",
                ]
            )

    # ========================================================
    # 12. ACTUALIZAR SERVICIOS DE TERCEROS
    # ========================================================

    for servicio in servicios:

        servicio.estado = (
            ServicioTerceroVenta
            .Estado
            .CONTABILIZADO
        )

        servicio.contabilizado_en = (
            timezone.now()
        )

        servicio.save(
            update_fields=[
                "estado",
                "contabilizado_en",
            ]
        )

    # ========================================================
    # 13. ACTUALIZAR PROPUESTA
    # ========================================================

    propuesta.estado = (
        PropuestaCostoVenta
        .Estado
        .CONTABILIZADA
    )

    propuesta.contabilizado_en = (
        timezone.now()
    )

    propuesta.save(
        update_fields=[
            "estado",
            "contabilizado_en",
        ]
    )

    return asiento



@transaction.atomic
def contabilizar_ingreso_venta(ticket):
    """
    Genera y contabiliza el asiento correspondiente
    al ingreso de una venta.

    Tratamiento:

    DEBE
        12101 Clientes - Ventas de óptica

    HABER
        701xx / 704xx Ingresos por ventas o servicios
        40111 IGV por pagar

    Supuesto inicial:
    - ticket.total incluye IGV.
    - Tasa IGV = 18%.
    - El cobro se contabilizará posteriormente mediante
      los registros de pago del ticket.
    """

    # ========================================================
    # 1. VALIDACIONES BÁSICAS
    # ========================================================

    if ticket.total is None or ticket.total <= 0:
        raise ValidationError(
            "El ticket debe tener un total mayor que cero."
        )

    detalles = list(
        ticket.detalles
        .select_related("producto")
        .all()
    )

    if not detalles:
        raise ValidationError(
            "El ticket no tiene detalles de venta."
        )

    # ========================================================
    # 2. PERIODO CONTABLE
    # ========================================================

    fecha = ticket.fecha_emision

    periodo = (
        PeriodoContable.objects
        .filter(
            anio=fecha.year,
            mes=fecha.month,
        )
        .first()
    )

    if not periodo:
        raise ValidationError(
            f"No existe periodo contable para "
            f"{fecha.month:02d}/{fecha.year}."
        )

    if (
        periodo.estado
        == PeriodoContable.Estado.CERRADO
    ):
        raise ValidationError(
            "El periodo contable de la venta está cerrado."
        )

    # ========================================================
    # 3. EVITAR DUPLICAR EL INGRESO DE UNA VENTA
    # ========================================================

    asiento_existente = (
        AsientoContable.objects
        .filter(
            origen="VENTA",
            origen_id=ticket.id,
        )
        .exclude(
            estado=AsientoContable.Estado.ANULADO
        )
        .first()
    )

    if asiento_existente:
        raise ValidationError(
            f"El ticket {ticket.numero} ya tiene "
            "un asiento de ingreso por venta."
        )

    # ========================================================
    # 4. COMPROBAR TOTAL DE LOS DETALLES
    # ========================================================

    total_detalles = sum(
        (
            Decimal(str(detalle.cantidad))
            * detalle.precio
            for detalle in detalles
        ),
        Decimal("0.00"),
    )

    total_ticket = Decimal(ticket.total)

    diferencia = abs(
        total_detalles - total_ticket
    )

    # Por ahora exigimos consistencia.
    # Más adelante podemos incorporar descuentos,
    # redondeos y promociones explícitamente.
    if diferencia > Decimal("0.02"):
        raise ValidationError(
            (
                f"El total de los detalles "
                f"(S/ {total_detalles:.2f}) no coincide "
                f"con el total del ticket "
                f"(S/ {total_ticket:.2f})."
            )
        )

    # ========================================================
    # 5. FUNCIÓN PARA DETERMINAR CUENTA DE INGRESO
    # ========================================================

    def cuenta_ingreso(detalle):

        producto = detalle.producto

        descripcion = (
            detalle.descripcion or ""
        ).strip().lower()

        # ----------------------------------------------------
        # PRODUCTOS INVENTARIABLES
        # ----------------------------------------------------

        if producto:

            tipo = (
                producto.tipo or ""
            ).strip().lower()

            descripcion_producto = (
                producto.descripcion or ""
            ).strip().lower()

            texto = (
                f"{tipo} "
                f"{descripcion_producto} "
                f"{descripcion}"
            )

            # MONTURAS

            if "montura" in texto:
                return CuentaContable.objects.get(
                    codigo="70101"
                )

            # LENTES DE CONTACTO

            if "contacto" in texto:
                return CuentaContable.objects.get(
                    codigo="70103"
                )

            # LÍQUIDOS

            if (
                "líquido" in texto
                or "liquido" in texto
            ):
                return CuentaContable.objects.get(
                    codigo="70104"
                )

            # ACCESORIOS

            if "accesorio" in texto:
                return CuentaContable.objects.get(
                    codigo="70105"
                )

        # ----------------------------------------------------
        # DETALLES SIN PRODUCTO
        # ----------------------------------------------------

        palabras_lunas = (
            "monofocal",
            "bifocal",
            "multifocal",
            "luna",
            "resina",
            "policarbonato",
            "blue",
            "fotocrom",
            "transition",
            "antireflex",
            "antirreflejo",
        )

        if any(
            palabra in descripcion
            for palabra in palabras_lunas
        ):
            return CuentaContable.objects.get(
                codigo="70102"
            )

        # SERVICIO DE BISELADO VENDIDO A TERCEROS

        if "bisel" in descripcion:
            return CuentaContable.objects.get(
                codigo="70401"
            )

        # OTROS SERVICIOS

        return CuentaContable.objects.get(
            codigo="70403"
        )

    # ========================================================
    # 6. CALCULAR IGV
    # ========================================================

    tasa_igv = Decimal("0.18")
    factor_igv = Decimal("1.18")

    base_imponible_total = (
        total_ticket / factor_igv
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    igv_total = (
        total_ticket
        - base_imponible_total
    )

    # ========================================================
    # 7. SIGUIENTE NÚMERO DE ASIENTO
    # ========================================================

    ultimo_numero = (
        AsientoContable.objects
        .filter(periodo=periodo)
        .order_by("-numero")
        .values_list(
            "numero",
            flat=True,
        )
        .first()
    )

    numero_asiento = (
        (ultimo_numero or 0) + 1
    )

    # ========================================================
    # 8. CREAR ASIENTO
    # ========================================================

    asiento = AsientoContable.objects.create(
        numero=numero_asiento,
        fecha=fecha,
        periodo=periodo,
        tipo=(
            AsientoContable
            .TipoAsiento
            .AUTOMATICO
        ),
        glosa=(
            f"Venta - Ticket "
            f"{ticket.numero:06d}"
        ),
        estado=(
            AsientoContable
            .Estado
            .BORRADOR
        ),
        origen="VENTA",
        origen_id=ticket.id,
    )

    secuencia = 1

    # ========================================================
    # 9. DEBE: CLIENTES
    # ========================================================

    cuenta_clientes = (
        CuentaContable.objects.get(
            codigo="12101"
        )
    )

    DetalleAsiento.objects.create(
        asiento=asiento,
        secuencia=secuencia,
        cuenta=cuenta_clientes,
        descripcion=(
            f"Venta Ticket "
            f"{ticket.numero:06d}"
        ),
        debe=total_ticket,
        haber=Decimal("0.00"),
        referencia=(
            f"Ticket {ticket.numero:06d}"
        ),
    )

    secuencia += 1

    # ========================================================
    # 10. DISTRIBUIR INGRESOS POR TIPO
    # ========================================================
    #
    # Agrupamos para evitar una línea contable por cada
    # detalle si varios corresponden a la misma cuenta.
    # ========================================================

    ingresos_por_cuenta = {}

    base_acumulada = Decimal("0.00")

    for indice, detalle in enumerate(
        detalles,
        start=1,
    ):

        bruto_detalle = (
            Decimal(str(detalle.cantidad))
            * detalle.precio
        )

        # Para todas las líneas excepto la última,
        # calculamos la base normalmente.
        if indice < len(detalles):

            base_detalle = (
                bruto_detalle
                / factor_igv
            ).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

            base_acumulada += base_detalle

        else:
            # La última línea absorbe cualquier diferencia
            # de redondeo para que cuadre exactamente.
            base_detalle = (
                base_imponible_total
                - base_acumulada
            )

        cuenta = cuenta_ingreso(detalle)

        if cuenta.id not in ingresos_por_cuenta:

            ingresos_por_cuenta[cuenta.id] = {
                "cuenta": cuenta,
                "importe": Decimal("0.00"),
            }

        ingresos_por_cuenta[
            cuenta.id
        ]["importe"] += base_detalle

    # ========================================================
    # 11. HABER: INGRESOS
    # ========================================================

    for item in ingresos_por_cuenta.values():

        cuenta = item["cuenta"]
        importe = item["importe"]

        if importe <= 0:
            continue

        DetalleAsiento.objects.create(
            asiento=asiento,
            secuencia=secuencia,
            cuenta=cuenta,
            descripcion=cuenta.nombre,
            debe=Decimal("0.00"),
            haber=importe,
            referencia=(
                f"Ticket {ticket.numero:06d}"
            ),
        )

        secuencia += 1

    # ========================================================
    # 12. HABER: IGV
    # ========================================================

    cuenta_igv = (
        CuentaContable.objects.get(
            codigo="40111"
        )
    )

    if igv_total > 0:

        DetalleAsiento.objects.create(
            asiento=asiento,
            secuencia=secuencia,
            cuenta=cuenta_igv,
            descripcion=(
                "IGV de venta"
            ),
            debe=Decimal("0.00"),
            haber=igv_total,
            referencia=(
                f"Ticket {ticket.numero:06d}"
            ),
        )

        secuencia += 1

    # ========================================================
    # 13. CONTABILIZAR
    # ========================================================

    contabilizar_asiento(asiento)

    return asiento


@transaction.atomic
def contabilizar_cobros_ticket(ticket):
    """
    Contabiliza todos los PagoTicket de una venta
    que todavía no hayan sido contabilizados.

    Por cada PagoTicket genera un asiento:

        DEBE
            Caja / Banco / medio correspondiente

        HABER
            12101 Clientes - Ventas de óptica

    Cada PagoTicket se contabiliza una sola vez.
    """

    pagos = (
        ticket.pagos
        .all()
        .order_by("fecha_hora", "id")
    )

    if not pagos.exists():
        raise ValidationError(
            f"El ticket {ticket.numero} no tiene pagos registrados."
        )

    cuenta_clientes = CuentaContable.objects.get(
        codigo="12101"
    )

    asientos_creados = []
    pagos_omitidos = []

    # ========================================================
    # FUNCIÓN AUXILIAR:
    # CUENTA SEGÚN MEDIO DE PAGO
    # ========================================================

    def cuenta_medio_pago(pago):

        if pago.medio_pago == "EFECTIVO":
            return CuentaContable.objects.get(
                codigo="10101"
            )

        if pago.medio_pago == "YAPE":
            return CuentaContable.objects.get(
                codigo="10401"
            )

        if pago.medio_pago == "TRANSFERENCIA":
            return CuentaContable.objects.get(
                codigo="10401"
            )

        if pago.medio_pago == "TARJETA":
            return CuentaContable.objects.get(
                codigo="10402"
            )

        raise ValidationError(
            f"No existe configuración contable para "
            f"el medio de pago '{pago.medio_pago}'."
        )

    # ========================================================
    # RECORRER LOS PAGOS
    # ========================================================

    for pago in pagos:

        if pago.monto is None or pago.monto <= 0:
            raise ValidationError(
                f"El PagoTicket {pago.id} tiene "
                "un monto inválido."
            )

        # ----------------------------------------------------
        # EVITAR CONTABILIZAR EL MISMO PAGO DOS VECES
        # ----------------------------------------------------

        asiento_existente = (
            AsientoContable.objects
            .filter(
                origen="COBRO_TICKET",
                origen_id=pago.id,
            )
            .exclude(
                estado=AsientoContable.Estado.ANULADO
            )
            .first()
        )

        if asiento_existente:
            pagos_omitidos.append(pago.id)
            continue

        # ----------------------------------------------------
        # FECHA REAL DEL COBRO
        # ----------------------------------------------------

        fecha_pago = timezone.localtime(pago.fecha_hora).date()

        periodo = (
            PeriodoContable.objects
            .filter(
                anio=fecha_pago.year,
                mes=fecha_pago.month,
            )
            .first()
        )

        if not periodo:
            raise ValidationError(
                f"No existe periodo contable para "
                f"{fecha_pago.month:02d}/{fecha_pago.year} "
                f"correspondiente al PagoTicket {pago.id}."
            )

        if (
            periodo.estado
            == PeriodoContable.Estado.CERRADO
        ):
            raise ValidationError(
                f"El periodo "
                f"{fecha_pago.month:02d}/{fecha_pago.year} "
                "está cerrado."
            )

        # ----------------------------------------------------
        # SIGUIENTE NÚMERO DE ASIENTO DEL PERIODO
        # ----------------------------------------------------

        ultimo_numero = (
            AsientoContable.objects
            .filter(periodo=periodo)
            .order_by("-numero")
            .values_list(
                "numero",
                flat=True,
            )
            .first()
        )

        numero_asiento = (
            (ultimo_numero or 0) + 1
        )

        # ----------------------------------------------------
        # CUENTA DEL MEDIO DE PAGO
        # ----------------------------------------------------

        cuenta_cobro = cuenta_medio_pago(
            pago
        )

        # ----------------------------------------------------
        # CREAR ASIENTO
        # ----------------------------------------------------

        asiento = AsientoContable.objects.create(
            numero=numero_asiento,
            fecha=fecha_pago,
            periodo=periodo,
            tipo=(
                AsientoContable
                .TipoAsiento
                .AUTOMATICO
            ),
            glosa=(
                f"Cobro Ticket "
                f"{ticket.numero:06d} - "
                f"{pago.get_medio_pago_display()}"
            ),
            estado=(
                AsientoContable
                .Estado
                .BORRADOR
            ),
            origen="COBRO_TICKET",
            origen_id=pago.id,
        )

        # ====================================================
        # DEBE: DINERO RECIBIDO
        # ====================================================

        DetalleAsiento.objects.create(
            asiento=asiento,
            secuencia=1,
            cuenta=cuenta_cobro,
            descripcion=(
                f"Cobro Ticket "
                f"{ticket.numero:06d} - "
                f"{pago.get_medio_pago_display()}"
            ),
            debe=pago.monto,
            haber=Decimal("0.00"),
            referencia=(
                f"PagoTicket {pago.id}"
            ),
        )

        # ====================================================
        # HABER: CANCELACIÓN DE CUENTA POR COBRAR
        # ====================================================

        DetalleAsiento.objects.create(
            asiento=asiento,
            secuencia=2,
            cuenta=cuenta_clientes,
            descripcion=(
                f"Cancelación cuenta por cobrar "
                f"Ticket {ticket.numero:06d}"
            ),
            debe=Decimal("0.00"),
            haber=pago.monto,
            referencia=(
                f"PagoTicket {pago.id}"
            ),
        )

        # ====================================================
        # VALIDAR Y CONTABILIZAR
        # ====================================================

        contabilizar_asiento(
            asiento
        )

        asientos_creados.append(
            asiento
        )

    return {
        "asientos_creados": asientos_creados,
        "pagos_omitidos": pagos_omitidos,
    }

@transaction.atomic
def procesar_venta_contablemente(ticket):
    """
    Procesa contablemente una ventexita.

    1. Genera el asiento de ingreso si todavía no existe.
    2. Genera la propuesta de costo de venta.
    3. Contabiliza los PagoTicket existentes que aún no
       hayan sido contabilizados.

    El costo de venta NO se contabiliza automáticamente,
    porque puede requerir validación manual.
    """

    resultado = {
        "asiento_venta": None,
        "propuesta_costo": None,
        "asientos_cobro": [],
        "pagos_omitidos": [],
    }

    # ========================================================
    # 1. ASIENTO DE INGRESO POR VENTA
    # ========================================================

    asiento_venta = (
        AsientoContable.objects
        .filter(
            origen="VENTA",
            origen_id=ticket.id,
        )
        .exclude(
            estado=AsientoContable.Estado.ANULADO
        )
        .first()
    )

    if not asiento_venta:
        asiento_venta = contabilizar_ingreso_venta(ticket)

    resultado["asiento_venta"] = asiento_venta

    # ========================================================
    # 2. PROPUESTA DE COSTO
    # ========================================================

    propuesta = generar_propuesta_costo_venta(ticket)

    resultado["propuesta_costo"] = propuesta

    # ========================================================
    # 3. COBROS
    # ========================================================

    if ticket.pagos.exists():

        resultado_cobros = contabilizar_cobros_ticket(
            ticket
        )

        resultado["asientos_cobro"] = (
            resultado_cobros["asientos_creados"]
        )

        resultado["pagos_omitidos"] = (
            resultado_cobros["pagos_omitidos"]
        )

    return resultado


@transaction.atomic
def procesar_venta_contablemente(ticket):
    """
    Procesa contablemente una venta.

    1. Genera el asiento de ingreso si todavía no existe.
    2. Genera la propuesta de costo de venta.
    3. Contabiliza los PagoTicket existentes que aún no
       hayan sido contabilizados.

    El costo de venta NO se contabiliza automáticamente,
    porque puede requerir validación manual.
    """

    resultado = {
        "asiento_venta": None,
        "propuesta_costo": None,
        "asientos_cobro": [],
        "pagos_omitidos": [],
    }

    # ========================================================
    # 1. ASIENTO DE INGRESO POR VENTA
    # ========================================================

    asiento_venta = (
        AsientoContable.objects
        .filter(
            origen="VENTA",
            origen_id=ticket.id,
        )
        .exclude(
            estado=AsientoContable.Estado.ANULADO
        )
        .first()
    )

    if not asiento_venta:
        asiento_venta = contabilizar_ingreso_venta(ticket)

    resultado["asiento_venta"] = asiento_venta

    # ========================================================
    # 2. PROPUESTA DE COSTO
    # ========================================================

    propuesta = generar_propuesta_costo_venta(ticket)

    resultado["propuesta_costo"] = propuesta

    # ========================================================
    # 3. COBROS
    # ========================================================

    if ticket.pagos.exists():

        resultado_cobros = contabilizar_cobros_ticket(
            ticket
        )

        resultado["asientos_cobro"] = (
            resultado_cobros["asientos_creados"]
        )

        resultado["pagos_omitidos"] = (
            resultado_cobros["pagos_omitidos"]
        )

    return resultado

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum


@transaction.atomic
def generar_cierre_anual(anio):

    # ========================================================
    # 1. VALIDAR LOS 12 PERIODOS
    # ========================================================

    periodos = PeriodoContable.objects.filter(
        anio=anio
    )

    if periodos.count() != 12:
        raise ValidationError(
            f"El ejercicio {anio} no tiene los 12 períodos contables."
        )

    # Enero - noviembre deben estar cerrados
    abiertos_enero_noviembre = periodos.filter(
        mes__lte=11,
        estado=PeriodoContable.Estado.ABIERTO,
    )

    if abiertos_enero_noviembre.exists():
        raise ValidationError(
            "Enero a noviembre deben estar cerrados "
            "antes de ejecutar el cierre anual."
        )

    # ========================================================
    # 2. DICIEMBRE DEBE ESTAR ABIERTO
    # ========================================================

    diciembre = periodos.get(mes=12)

    if diciembre.estado != PeriodoContable.Estado.ABIERTO:
        raise ValidationError(
            "Diciembre debe permanecer abierto "
            "para registrar el asiento de cierre anual."
        )

    # ========================================================
    # 3. EVITAR DUPLICIDAD
    # ========================================================

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

    if cierre_existente:
        raise ValidationError(
            f"El ejercicio {anio} ya tiene un cierre anual."
        )

    # ========================================================
    # 4. OBTENER MOVIMIENTOS DE CUENTAS DE RESULTADO
    # ========================================================

    movimientos = (
        DetalleAsiento.objects
        .filter(
            asiento__periodo__anio=anio,
            asiento__estado=AsientoContable.Estado.CONTABILIZADO,
            cuenta__tipo__in=[
                CuentaContable.TipoCuenta.INGRESO,
                CuentaContable.TipoCuenta.COSTO,
                CuentaContable.TipoCuenta.GASTO,
            ],
        )
        .values(
            "cuenta_id",
            "cuenta__codigo",
            "cuenta__nombre",
        )
        .annotate(
            total_debe=Sum("debe"),
            total_haber=Sum("haber"),
        )
        .order_by("cuenta__codigo")
    )

    movimientos = list(movimientos)

    if not movimientos:
        raise ValidationError(
            f"No existen cuentas de resultados con movimientos en {anio}."
        )

    # ========================================================
    # 5. CUENTA RESULTADO DEL EJERCICIO
    # ========================================================

    cuenta_resultado = CuentaContable.objects.get(
        codigo="59901"
    )

    # ========================================================
    # 6. SIGUIENTE NÚMERO DE ASIENTO DE DICIEMBRE
    # ========================================================

    ultimo_numero = (
        AsientoContable.objects
        .filter(periodo=diciembre)
        .order_by("-numero")
        .values_list("numero", flat=True)
        .first()
    )

    numero = (ultimo_numero or 0) + 1

    # ========================================================
    # 7. CREAR CABECERA
    # ========================================================

    asiento = AsientoContable.objects.create(
        periodo=diciembre,
        numero=numero,
        fecha=diciembre.fecha_fin,
        glosa=f"Cierre de cuentas de resultados - Ejercicio {anio}",
        estado=AsientoContable.Estado.BORRADOR,
        origen="CIERRE_ANUAL",
        origen_id=anio,
    )

    # ========================================================
    # 8. CERRAR CADA CUENTA DE RESULTADO
    # ========================================================

    secuencia = 1

    total_debe_cierre = Decimal("0.00")
    total_haber_cierre = Decimal("0.00")

    for movimiento in movimientos:

        debe = movimiento["total_debe"] or Decimal("0.00")
        haber = movimiento["total_haber"] or Decimal("0.00")

        saldo = debe - haber

        if saldo == 0:
            continue

        cuenta = CuentaContable.objects.get(
            id=movimiento["cuenta_id"]
        )

        # Saldo deudor -> se cierra por el Haber
        if saldo > 0:

            DetalleAsiento.objects.create(
                asiento=asiento,
                secuencia=secuencia,
                cuenta=cuenta,
                debe=Decimal("0.00"),
                haber=saldo,
            )

            total_haber_cierre += saldo

        # Saldo acreedor -> se cierra por el Debe
        else:

            importe = abs(saldo)

            DetalleAsiento.objects.create(
                asiento=asiento,
                secuencia=secuencia,
                cuenta=cuenta,
                debe=importe,
                haber=Decimal("0.00"),
            )

            total_debe_cierre += importe

        secuencia += 1

    # ========================================================
    # 9. DETERMINAR RESULTADO DEL EJERCICIO
    # ========================================================

    diferencia = total_debe_cierre - total_haber_cierre

    if diferencia > 0:

        # UTILIDAD
        # Resultado del ejercicio queda acreedor

        DetalleAsiento.objects.create(
            asiento=asiento,
            secuencia=secuencia,
            cuenta=cuenta_resultado,
            debe=Decimal("0.00"),
            haber=diferencia,
        )

    elif diferencia < 0:

        # PÉRDIDA
        # Resultado del ejercicio queda deudor

        DetalleAsiento.objects.create(
            asiento=asiento,
            secuencia=secuencia,
            cuenta=cuenta_resultado,
            debe=abs(diferencia),
            haber=Decimal("0.00"),
        )

    else:

        raise ValidationError(
            "El ejercicio tiene resultado cero. "
            "Debe definirse el tratamiento del cierre sin resultado."
        )

    # ========================================================
    # 10. CONTABILIZAR
    # ========================================================

    contabilizar_asiento(asiento)

    return asiento

# ============================================================
# CONTABILIZAR OPERACIÓN CONTABLE
# ============================================================
@transaction.atomic
def contabilizar_operacion_contable(operacion):

    # --------------------------------------------------------
    # VALIDACIONES GENERALES
    # --------------------------------------------------------

    if operacion.estado == OperacionContable.Estado.ANULADA:
        raise ValidationError(
            "No se puede contabilizar una operación anulada."
        )

    if operacion.estado == OperacionContable.Estado.CONTABILIZADA:
        raise ValidationError(
            "La operación ya se encuentra contabilizada."
        )

    if operacion.asiento_id:
        raise ValidationError(
            "La operación ya tiene un asiento asociado."
        )

    operacion.full_clean()

    # --------------------------------------------------------
    # CONCEPTO Y CUENTA PRINCIPAL
    # --------------------------------------------------------

    concepto = operacion.concepto
    cuenta_principal = concepto.cuenta_contable

    if not cuenta_principal:
        raise ValidationError(
            "El concepto seleccionado no tiene "
            "una cuenta contable configurada."
        )

    if not cuenta_principal.activo:
        raise ValidationError(
            "La cuenta contable principal se encuentra inactiva."
        )

    if not cuenta_principal.acepta_movimientos:
        raise ValidationError(
            "La cuenta contable principal no acepta movimientos."
        )

    # --------------------------------------------------------
    # PERÍODO
    # --------------------------------------------------------

    periodo = (
        PeriodoContable.objects
        .filter(
            fecha_inicio__lte=operacion.fecha,
            fecha_fin__gte=operacion.fecha,
        )
        .first()
    )

    if not periodo:
        raise ValidationError(
            "No existe un período contable "
            "para la fecha de la operación."
        )

    if periodo.estado == PeriodoContable.Estado.CERRADO:
        raise ValidationError(
            "No se puede contabilizar la operación "
            "porque el período contable está cerrado."
        )

    # --------------------------------------------------------
    # PROTEGER DUPLICADOS
    # --------------------------------------------------------

    asiento_existente = (
        AsientoContable.objects
        .filter(
            origen="OPERACION_CONTABLE",
            origen_id=operacion.id,
        )
        .exclude(
            estado=AsientoContable.Estado.ANULADO
        )
        .first()
    )

    if asiento_existente:
        raise ValidationError(
            "Ya existe un asiento contable para esta operación."
        )

    # --------------------------------------------------------
    # NÚMERO DEL ASIENTO
    # --------------------------------------------------------

    ultimo_numero = (
        AsientoContable.objects
        .filter(periodo=periodo)
        .order_by("-numero")
        .values_list("numero", flat=True)
        .first()
    )

    numero = (ultimo_numero or 0) + 1

    # --------------------------------------------------------
    # GLOSA
    # --------------------------------------------------------

    glosa = concepto.nombre

    if operacion.descripcion:
        glosa += f" - {operacion.descripcion}"

    # --------------------------------------------------------
    # CREAR ASIENTO
    # --------------------------------------------------------

    asiento = AsientoContable(
        numero=numero,
        fecha=operacion.fecha,
        periodo=periodo,
        tipo=AsientoContable.TipoAsiento.AUTOMATICO,
        glosa=glosa[:500],
        estado=AsientoContable.Estado.BORRADOR,
        origen="OPERACION_CONTABLE",
        origen_id=operacion.id,
    )

    asiento.full_clean()
    asiento.save()

    secuencia = 1

    # --------------------------------------------------------
    # REFERENCIA
    # --------------------------------------------------------

    referencia = ""

    if operacion.tipo_documento:
        referencia = operacion.tipo_documento

    if operacion.numero_documento:
        if referencia:
            referencia += " "

        referencia += operacion.numero_documento

    # ========================================================
    # 1. DÉBITO: CUENTA PRINCIPAL
    # ========================================================

    detalle_debe = DetalleAsiento(
        asiento=asiento,
        secuencia=secuencia,
        cuenta=cuenta_principal,
        descripcion=concepto.nombre,
        debe=operacion.importe_total,
        haber=Decimal("0.00"),
        categoria_gerencial=concepto.categoria_gerencial,
        centro_costo=concepto.centro_costo,
        referencia=referencia,
    )

    detalle_debe.full_clean()
    detalle_debe.save()

    secuencia += 1

    # ========================================================
    # 2. PAGO TOTAL
    # ========================================================

    if operacion.forma_pago in [
        OperacionContable.FormaPago.EFECTIVO,
        OperacionContable.FormaPago.BANCO,
        OperacionContable.FormaPago.OTRO,
    ]:

        if not operacion.cuenta_pago_id:
            raise ValidationError(
                "Debe seleccionar la cuenta de pago."
            )

        detalle_pago = DetalleAsiento(
            asiento=asiento,
            secuencia=secuencia,
            cuenta=operacion.cuenta_pago,
            descripcion="Pago de la operación",
            debe=Decimal("0.00"),
            haber=operacion.importe_total,
            referencia=referencia,
        )

        detalle_pago.full_clean()
        detalle_pago.save()

    # ========================================================
    # 3. OPERACIÓN AL CRÉDITO
    # ========================================================

    elif operacion.forma_pago == OperacionContable.FormaPago.CREDITO:

        if not operacion.cuenta_por_pagar_id:
            raise ValidationError(
                "Debe seleccionar la cuenta por pagar."
            )

        detalle_credito = DetalleAsiento(
            asiento=asiento,
            secuencia=secuencia,
            cuenta=operacion.cuenta_por_pagar,
            descripcion="Obligación pendiente de pago",
            debe=Decimal("0.00"),
            haber=operacion.importe_total,
            referencia=referencia,
        )

        detalle_credito.full_clean()
        detalle_credito.save()

    # ========================================================
    # 4. PAGO PARCIAL
    # ========================================================

    elif operacion.forma_pago == OperacionContable.FormaPago.PARCIAL:

        if not operacion.cuenta_pago_id:
            raise ValidationError(
                "Debe seleccionar la cuenta del pago inicial."
            )

        if not operacion.cuenta_por_pagar_id:
            raise ValidationError(
                "Debe seleccionar la cuenta por pagar "
                "del saldo pendiente."
            )

        # Pago inicial

        detalle_pago = DetalleAsiento(
            asiento=asiento,
            secuencia=secuencia,
            cuenta=operacion.cuenta_pago,
            descripcion="Pago inicial",
            debe=Decimal("0.00"),
            haber=operacion.monto_pagado,
            referencia=referencia,
        )

        detalle_pago.full_clean()
        detalle_pago.save()

        secuencia += 1

        # Saldo pendiente

        saldo = (
            operacion.importe_total
            - operacion.monto_pagado
        )

        detalle_credito = DetalleAsiento(
            asiento=asiento,
            secuencia=secuencia,
            cuenta=operacion.cuenta_por_pagar,
            descripcion="Saldo pendiente de pago",
            debe=Decimal("0.00"),
            haber=saldo,
            referencia=referencia,
        )

        detalle_credito.full_clean()
        detalle_credito.save()

    else:
        raise ValidationError(
            "La forma de pago seleccionada no es válida."
        )

    # ========================================================
    # CONTABILIZAR ASIENTO
    # ========================================================

    contabilizar_asiento(asiento)

    # ========================================================
    # ACTUALIZAR OPERACIÓN
    # ========================================================

    operacion.asiento = asiento
    operacion.estado = OperacionContable.Estado.CONTABILIZADA
    operacion.contabilizado_en = timezone.now()

    operacion.save(
        update_fields=[
            "asiento",
            "estado",
            "contabilizado_en",
            "actualizado_en",
        ]
    )

    return asiento

@transaction.atomic
def contabilizar_pago_operacion_contable(pago):

    # ========================================================
    # 1. VALIDACIONES GENERALES
    # ========================================================

    if pago.estado == PagoOperacionContable.Estado.ANULADO:
        raise ValidationError(
            "No se puede contabilizar un pago anulado."
        )

    if pago.estado == PagoOperacionContable.Estado.CONTABILIZADO:
        raise ValidationError(
            "El pago ya se encuentra contabilizado."
        )

    if pago.asiento_id:
        raise ValidationError(
            "El pago ya tiene un asiento contable asociado."
        )

    if pago.estado != PagoOperacionContable.Estado.REGISTRADO:
        raise ValidationError(
            "El pago debe encontrarse en estado REGISTRADO."
        )

    pago.full_clean()

    # ========================================================
    # 2. OPERACIÓN
    # ========================================================

    operacion = pago.operacion

    if operacion.estado != OperacionContable.Estado.CONTABILIZADA:
        raise ValidationError(
            "La operación debe encontrarse contabilizada."
        )

    if not operacion.cuenta_por_pagar_id:
        raise ValidationError(
            "La operación no tiene una cuenta por pagar asociada."
        )

    cuenta_por_pagar = operacion.cuenta_por_pagar
    cuenta_pago = pago.cuenta_pago

    # ========================================================
    # 3. VALIDAR CUENTA POR PAGAR
    # ========================================================

    if not cuenta_por_pagar.activo:
        raise ValidationError(
            "La cuenta por pagar se encuentra inactiva."
        )

    if not cuenta_por_pagar.acepta_movimientos:
        raise ValidationError(
            "La cuenta por pagar no acepta movimientos."
        )

    # ========================================================
    # 4. VALIDAR CUENTA DE PAGO
    # ========================================================

    if not cuenta_pago:
        raise ValidationError(
            "Debe seleccionar la cuenta utilizada para pagar."
        )

    if not cuenta_pago.activo:
        raise ValidationError(
            "La cuenta de pago se encuentra inactiva."
        )

    if not cuenta_pago.acepta_movimientos:
        raise ValidationError(
            "La cuenta de pago no acepta movimientos."
        )

    # ========================================================
    # 5. VALIDAR MONTO
    # ========================================================

    if pago.monto <= Decimal("0.00"):
        raise ValidationError(
            "El monto del pago debe ser mayor que cero."
        )

    # ========================================================
    # 6. PERÍODO CONTABLE
    # ========================================================

    periodo = (
        PeriodoContable.objects
        .filter(
            fecha_inicio__lte=pago.fecha_pago,
            fecha_fin__gte=pago.fecha_pago,
        )
        .first()
    )

    if not periodo:
        raise ValidationError(
            "No existe un período contable "
            "para la fecha del pago."
        )

    if periodo.estado == PeriodoContable.Estado.CERRADO:
        raise ValidationError(
            "No se puede contabilizar el pago "
            "porque el período contable está cerrado."
        )

    # ========================================================
    # 7. PROTEGER DUPLICADOS
    # ========================================================

    asiento_existente = (
        AsientoContable.objects
        .filter(
            origen="PAGO_OPERACION_CONTABLE",
            origen_id=pago.id,
        )
        .exclude(
            estado=AsientoContable.Estado.ANULADO
        )
        .first()
    )

    if asiento_existente:
        raise ValidationError(
            "Ya existe un asiento contable para este pago."
        )

    # ========================================================
    # 8. NÚMERO DEL ASIENTO
    # ========================================================

    ultimo_numero = (
        AsientoContable.objects
        .filter(
            periodo=periodo
        )
        .order_by(
            "-numero"
        )
        .values_list(
            "numero",
            flat=True,
        )
        .first()
    )

    numero = (
        (ultimo_numero or 0)
        + 1
    )

    # ========================================================
    # 9. GLOSA
    # ========================================================

    glosa = (
        f"Pago de {operacion.concepto.nombre}"
    )

    if operacion.proveedor_nombre:
        glosa += (
            f" - {operacion.proveedor_nombre}"
        )

    # ========================================================
    # 10. REFERENCIA
    # ========================================================

    referencia = ""

    if operacion.tipo_documento:
        referencia = operacion.tipo_documento

    if operacion.numero_documento:

        if referencia:
            referencia += " "

        referencia += operacion.numero_documento

    # ========================================================
    # 11. CREAR ASIENTO
    # ========================================================

    asiento = AsientoContable(
        numero=numero,
        fecha=pago.fecha_pago,
        periodo=periodo,
        tipo=AsientoContable.TipoAsiento.AUTOMATICO,
        glosa=glosa[:500],
        estado=AsientoContable.Estado.BORRADOR,
        origen="PAGO_OPERACION_CONTABLE",
        origen_id=pago.id,
    )

    asiento.full_clean()
    asiento.save()

    # ========================================================
    # 12. DÉBITO: CUENTA POR PAGAR
    # ========================================================

    detalle_debe = DetalleAsiento(
        asiento=asiento,
        secuencia=1,
        cuenta=cuenta_por_pagar,
        descripcion=(
            "Cancelación de obligación pendiente"
        ),
        debe=pago.monto,
        haber=Decimal("0.00"),
        referencia=referencia,
    )

    detalle_debe.full_clean()
    detalle_debe.save()

    # ========================================================
    # 13. HABER: CAJA / BANCO
    # ========================================================

    detalle_haber = DetalleAsiento(
        asiento=asiento,
        secuencia=2,
        cuenta=cuenta_pago,
        descripcion=(
            "Pago de operación"
        ),
        debe=Decimal("0.00"),
        haber=pago.monto,
        referencia=referencia,
    )

    detalle_haber.full_clean()
    detalle_haber.save()

    # ========================================================
    # 14. CONTABILIZAR ASIENTO
    # ========================================================

    contabilizar_asiento(
        asiento
    )

    # ========================================================
    # 15. ACTUALIZAR PAGO
    # ========================================================

    pago.asiento = asiento
    pago.estado = (
        PagoOperacionContable.Estado.CONTABILIZADO
    )
    pago.contabilizado_en = timezone.now()

    pago.save(
        update_fields=[
            "asiento",
            "estado",
            "contabilizado_en",
        ]
    )

    return asiento

@transaction.atomic
def contabilizar_nota_credito(nota):
    """
    Contabiliza una nota de crédito vinculada a una venta.

    Tratamiento:

    1) Reversión de la venta:
        DEBE
            701xx / 704xx   Ingreso revertido
            40111           IGV revertido

        HABER
            12101           Clientes

    2) Si existe devolución de dinero:
        DEBE
            12101           Clientes

        HABER
            101xx / 104xx   Caja / Banco

    3) Si un producto físico vuelve al inventario:
        DEBE
            201xx           Inventario

        HABER
            691xx           Costo de ventas

       Además se recalcula el Kardex del producto utilizando
       el costo original con el que salió en la venta.

    El ticket original no se elimina ni modifica en su total.
    """

    from decimal import Decimal, ROUND_HALF_UP

    from django.core.exceptions import ValidationError
    from django.utils import timezone

    from core.kardex import recalcular_kardex_producto


    # ========================================================
    # 1. VALIDACIONES BÁSICAS
    # ========================================================

    if nota.estado == NotaCredito.Estado.ANULADA:
        raise ValidationError(
            "La nota de crédito está anulada."
        )

    if nota.estado == NotaCredito.Estado.CONTABILIZADA:
        raise ValidationError(
            "La nota de crédito ya está contabilizada."
        )

    if nota.asiento_id:
        raise ValidationError(
            "La nota de crédito ya tiene un asiento asociado."
        )

    nota.full_clean()

    if nota.monto_total <= Decimal("0.00"):
        raise ValidationError(
            "El importe de la nota de crédito debe ser mayor que cero."
        )


    # ========================================================
    # 2. DETALLES DE LA NOTA DE CRÉDITO
    # ========================================================

    detalles_nc = list(
        nota.detalles
        .select_related(
            "detalle_ticket",
            "detalle_ticket__producto",
        )
        .all()
    )

    if not detalles_nc:
        raise ValidationError(
            "La nota de crédito no tiene detalles."
        )

    total_detalles = sum(
        (
            Decimal(detalle.importe)
            for detalle in detalles_nc
        ),
        Decimal("0.00"),
    )

    if total_detalles != Decimal(nota.monto_total):
        raise ValidationError(
            (
                f"El total de los detalles "
                f"(S/ {total_detalles:.2f}) no coincide "
                f"con el total de la nota de crédito "
                f"(S/ {nota.monto_total:.2f})."
            )
        )


    # ========================================================
    # 3. DETALLES QUE REGRESAN AL INVENTARIO
    # ========================================================

    detalles_stock = [
        detalle
        for detalle in detalles_nc
        if detalle.devuelve_stock
    ]

    for detalle_nc in detalles_stock:

        detalle_ticket = detalle_nc.detalle_ticket

        if not detalle_ticket.producto_id:
            raise ValidationError(
                (
                    f"El detalle '{detalle_ticket.descripcion}' "
                    "no tiene un producto inventariable asociado."
                )
            )

        cantidad_devuelta = Decimal(
            str(detalle_nc.cantidad or 0)
        )

        cantidad_vendida = Decimal(
            str(detalle_ticket.cantidad or 0)
        )

        if cantidad_devuelta <= Decimal("0"):
            raise ValidationError(
                "La cantidad devuelta debe ser mayor que cero."
            )

        # ----------------------------------------------------
        # CONTROLAR DEVOLUCIONES ANTERIORES
        # ----------------------------------------------------

        modelo_detalle_nc = type(detalle_nc)

        devoluciones_anteriores = (
            modelo_detalle_nc.objects
            .filter(
                detalle_ticket=detalle_ticket,
                devuelve_stock=True,
                nota_credito__estado=(
                    NotaCredito.Estado.CONTABILIZADA
                ),
            )
            .exclude(
                nota_credito=nota
            )
        )

        cantidad_ya_devuelta = sum(
            (
                Decimal(str(item.cantidad or 0))
                for item in devoluciones_anteriores
            ),
            Decimal("0"),
        )

        if (
            cantidad_ya_devuelta
            + cantidad_devuelta
            > cantidad_vendida
        ):
            raise ValidationError(
                (
                    f"La devolución del producto "
                    f"'{detalle_ticket.descripcion}' excede "
                    f"la cantidad originalmente vendida. "
                    f"Vendido: {cantidad_vendida}. "
                    f"Devuelto anteriormente: "
                    f"{cantidad_ya_devuelta}. "
                    f"Nueva devolución: "
                    f"{cantidad_devuelta}."
                )
            )


    # ========================================================
    # 4. PERIODO CONTABLE
    # ========================================================

    fecha = nota.fecha_emision

    periodo = (
        PeriodoContable.objects
        .filter(
            anio=fecha.year,
            mes=fecha.month,
        )
        .first()
    )

    if not periodo:
        raise ValidationError(
            (
                f"No existe periodo contable para "
                f"{fecha.month:02d}/{fecha.year}."
            )
        )

    if periodo.estado == PeriodoContable.Estado.CERRADO:
        raise ValidationError(
            "El periodo contable de la nota de crédito está cerrado."
        )


    # ========================================================
    # 5. EVITAR DUPLICIDAD
    # ========================================================

    asiento_existente = (
        AsientoContable.objects
        .filter(
            origen="NOTA_CREDITO",
            origen_id=nota.id,
        )
        .exclude(
            estado=AsientoContable.Estado.ANULADO
        )
        .first()
    )

    if asiento_existente:
        raise ValidationError(
            (
                f"La nota de crédito "
                f"{nota.numero:06d} ya tiene "
                f"un asiento contable."
            )
        )


    # ========================================================
    # 6. DETERMINAR CUENTA DE INGRESO
    #
    # Misma lógica de contabilizar_ingreso_venta().
    # ========================================================

    def cuenta_ingreso(detalle_ticket):

        producto = detalle_ticket.producto

        descripcion = (
            detalle_ticket.descripcion
            or ""
        ).strip().lower()

        # ----------------------------------------------------
        # PRODUCTOS INVENTARIABLES
        # ----------------------------------------------------

        if producto:

            tipo = (
                producto.tipo
                or ""
            ).strip().lower()

            descripcion_producto = (
                producto.descripcion
                or ""
            ).strip().lower()

            texto = (
                f"{tipo} "
                f"{descripcion_producto} "
                f"{descripcion}"
            )

            if "montura" in texto:
                return CuentaContable.objects.get(
                    codigo="70101"
                )

            if "contacto" in texto:
                return CuentaContable.objects.get(
                    codigo="70103"
                )

            if (
                "líquido" in texto
                or "liquido" in texto
            ):
                return CuentaContable.objects.get(
                    codigo="70104"
                )

            if "accesorio" in texto:
                return CuentaContable.objects.get(
                    codigo="70105"
                )

        # ----------------------------------------------------
        # LUNAS
        # ----------------------------------------------------

        palabras_lunas = (
            "monofocal",
            "bifocal",
            "multifocal",
            "luna",
            "resina",
            "policarbonato",
            "blue",
            "fotocrom",
            "transition",
            "antireflex",
            "antirreflejo",
        )

        if any(
            palabra in descripcion
            for palabra in palabras_lunas
        ):
            return CuentaContable.objects.get(
                codigo="70102"
            )

        # ----------------------------------------------------
        # BISELADO A TERCEROS
        # ----------------------------------------------------

        if "bisel" in descripcion:
            return CuentaContable.objects.get(
                codigo="70401"
            )

        # ----------------------------------------------------
        # OTROS SERVICIOS
        # ----------------------------------------------------

        return CuentaContable.objects.get(
            codigo="70403"
        )


    # ========================================================
    # 7. CUENTAS DE INVENTARIO Y COSTO PARA DEVOLUCIONES
    # ========================================================

    def cuentas_inventario_costo(detalle_ticket):

        producto = detalle_ticket.producto

        if not producto:
            raise ValidationError(
                "El detalle no corresponde a un producto inventariable."
            )

        tipo = (
            producto.tipo
            or ""
        ).strip().lower()

        descripcion_producto = (
            producto.descripcion
            or ""
        ).strip().lower()

        descripcion_detalle = (
            detalle_ticket.descripcion
            or ""
        ).strip().lower()

        texto = (
            f"{tipo} "
            f"{descripcion_producto} "
            f"{descripcion_detalle}"
        )

        # MONTURAS
        if "montura" in texto:
            return (
                CuentaContable.objects.get(
                    codigo="20101"
                ),
                CuentaContable.objects.get(
                    codigo="69101"
                ),
            )

        # LENTES DE CONTACTO
        if "contacto" in texto:
            return (
                CuentaContable.objects.get(
                    codigo="20103"
                ),
                CuentaContable.objects.get(
                    codigo="69103"
                ),
            )

        # LÍQUIDOS
        if (
            "líquido" in texto
            or "liquido" in texto
        ):
            return (
                CuentaContable.objects.get(
                    codigo="20107"
                ),
                CuentaContable.objects.get(
                    codigo="69107"
                ),
            )

        # ACCESORIOS
        if "accesorio" in texto:
            return (
                CuentaContable.objects.get(
                    codigo="20106"
                ),
                CuentaContable.objects.get(
                    codigo="69106"
                ),
            )

        raise ValidationError(
            (
                f"No se pudo determinar la cuenta de inventario "
                f"y costo de venta para el producto "
                f"'{producto.descripcion}'."
            )
        )


    # ========================================================
    # 8. DETERMINAR COSTO ORIGINAL DE LAS DEVOLUCIONES
    # ========================================================

    reversiones_costo = []

    for detalle_nc in detalles_stock:

        detalle_ticket = detalle_nc.detalle_ticket

        producto = detalle_ticket.producto

        # ----------------------------------------------------
        # PRIORIDAD 1:
        # KARDEX OUT DE LA VENTA ORIGINAL
        # ----------------------------------------------------

        kardex_salida = (
            KardexMovimiento.objects
            .filter(
                ticket=nota.ticket,
                producto=producto,
                tipo="OUT",
            )
            .order_by("-fecha", "-id")
            .first()
        )

        costo_unitario = None

        if (
            kardex_salida
            and kardex_salida.costo_unitario is not None
        ):
            costo_unitario = Decimal(
                kardex_salida.costo_unitario
            )

        # ----------------------------------------------------
        # PRIORIDAD 2:
        # COSTO CONTABLE VALIDADO DE LA VENTA
        # ----------------------------------------------------

        if costo_unitario is None:

            try:
                costo_contable = (
                    detalle_ticket.costo_contable
                )
            except Exception:
                costo_contable = None

            if (
                costo_contable
                and costo_contable.costo_unitario
                is not None
            ):
                costo_unitario = Decimal(
                    costo_contable.costo_unitario
                )

        if costo_unitario is None:
            raise ValidationError(
                (
                    f"No se pudo determinar el costo original "
                    f"del producto "
                    f"'{producto.descripcion}' "
                    f"del ticket "
                    f"{nota.ticket.numero:06d}."
                )
            )

        cantidad_devuelta = Decimal(
            str(detalle_nc.cantidad)
        )

        costo_total_reversion = (
            cantidad_devuelta
            * costo_unitario
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        cuenta_inventario, cuenta_costo = (
            cuentas_inventario_costo(
                detalle_ticket
            )
        )

        reversiones_costo.append({
            "detalle_nc": detalle_nc,
            "producto": producto,
            "cantidad": cantidad_devuelta,
            "costo_unitario": costo_unitario,
            "costo_total": costo_total_reversion,
            "cuenta_inventario": cuenta_inventario,
            "cuenta_costo": cuenta_costo,
        })


    # ========================================================
    # 9. CÁLCULO DEL IGV
    # ========================================================

    factor_igv = Decimal("1.18")

    total_nota = Decimal(
        nota.monto_total
    )

    base_imponible_total = (
        total_nota / factor_igv
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    igv_total = (
        total_nota
        - base_imponible_total
    )


    # ========================================================
    # 10. DISTRIBUIR BASE POR CUENTA DE INGRESO
    # ========================================================

    ingresos_por_cuenta = {}

    base_acumulada = Decimal("0.00")

    for indice, detalle_nc in enumerate(
        detalles_nc,
        start=1,
    ):

        bruto_detalle = Decimal(
            detalle_nc.importe
        )

        if indice < len(detalles_nc):

            base_detalle = (
                bruto_detalle
                / factor_igv
            ).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

            base_acumulada += base_detalle

        else:

            base_detalle = (
                base_imponible_total
                - base_acumulada
            )

        cuenta = cuenta_ingreso(
            detalle_nc.detalle_ticket
        )

        if cuenta.id not in ingresos_por_cuenta:

            ingresos_por_cuenta[
                cuenta.id
            ] = {
                "cuenta": cuenta,
                "importe": Decimal("0.00"),
            }

        ingresos_por_cuenta[
            cuenta.id
        ]["importe"] += base_detalle


    # ========================================================
    # 11. CUENTAS CONTABLES
    # ========================================================

    cuenta_clientes = (
        CuentaContable.objects.get(
            codigo="12101"
        )
    )

    cuenta_igv = (
        CuentaContable.objects.get(
            codigo="40111"
        )
    )


    # ========================================================
    # 12. VALIDAR CUENTA DE DEVOLUCIÓN
    # ========================================================

    if nota.monto_devuelto > Decimal("0.00"):

        if not nota.cuenta_devolucion_id:
            raise ValidationError(
                "Debe indicar la cuenta utilizada "
                "para devolver el dinero."
            )

        cuenta_devolucion = (
            nota.cuenta_devolucion
        )

        if not cuenta_devolucion.activo:
            raise ValidationError(
                "La cuenta de devolución está inactiva."
            )

        if not cuenta_devolucion.acepta_movimientos:
            raise ValidationError(
                "La cuenta de devolución no acepta movimientos."
            )

    else:

        cuenta_devolucion = None


    # ========================================================
    # 13. SIGUIENTE NÚMERO DE ASIENTO
    # ========================================================

    ultimo_numero = (
        AsientoContable.objects
        .filter(
            periodo=periodo
        )
        .order_by("-numero")
        .values_list(
            "numero",
            flat=True,
        )
        .first()
    )

    numero_asiento = (
        (ultimo_numero or 0)
        + 1
    )


    # ========================================================
    # 14. CREAR ASIENTO
    # ========================================================

    asiento = AsientoContable.objects.create(
        numero=numero_asiento,
        fecha=fecha,
        periodo=periodo,
        tipo=(
            AsientoContable
            .TipoAsiento
            .AUTOMATICO
        ),
        glosa=(
            f"Nota de crédito "
            f"{nota.numero:06d} - "
            f"Ticket {nota.ticket.numero:06d}"
        ),
        estado=(
            AsientoContable
            .Estado
            .BORRADOR
        ),
        origen="NOTA_CREDITO",
        origen_id=nota.id,
    )

    secuencia = 1

    referencia = (
        f"NC {nota.numero:06d} / "
        f"Ticket {nota.ticket.numero:06d}"
    )


    # ========================================================
    # 15. DEBE: REVERSIÓN DE INGRESOS
    # ========================================================

    for item in ingresos_por_cuenta.values():

        cuenta = item["cuenta"]

        importe = item["importe"]

        if importe <= Decimal("0.00"):
            continue

        DetalleAsiento.objects.create(
            asiento=asiento,
            secuencia=secuencia,
            cuenta=cuenta,
            descripcion=(
                f"Reversión - {cuenta.nombre}"
            ),
            debe=importe,
            haber=Decimal("0.00"),
            referencia=referencia,
        )

        secuencia += 1


    # ========================================================
    # 16. DEBE: REVERSIÓN DEL IGV
    # ========================================================

    if igv_total > Decimal("0.00"):

        DetalleAsiento.objects.create(
            asiento=asiento,
            secuencia=secuencia,
            cuenta=cuenta_igv,
            descripcion=(
                "Reversión de IGV por nota de crédito"
            ),
            debe=igv_total,
            haber=Decimal("0.00"),
            referencia=referencia,
        )

        secuencia += 1


    # ========================================================
    # 17. HABER: CLIENTES
    # ========================================================

    DetalleAsiento.objects.create(
        asiento=asiento,
        secuencia=secuencia,
        cuenta=cuenta_clientes,
        descripcion=(
            f"Nota de crédito "
            f"{nota.numero:06d}"
        ),
        debe=Decimal("0.00"),
        haber=total_nota,
        referencia=referencia,
    )

    secuencia += 1


    # ========================================================
    # 18. DEVOLUCIÓN DE DINERO
    #
    # DEBE 12101
    # HABER CAJA / BANCO
    # ========================================================

    monto_devuelto = (
        nota.monto_devuelto
        or Decimal("0.00")
    )

    if monto_devuelto > Decimal("0.00"):

        DetalleAsiento.objects.create(
            asiento=asiento,
            secuencia=secuencia,
            cuenta=cuenta_clientes,
            descripcion=(
                "Devolución al cliente "
                f"por NC {nota.numero:06d}"
            ),
            debe=monto_devuelto,
            haber=Decimal("0.00"),
            referencia=referencia,
        )

        secuencia += 1

        DetalleAsiento.objects.create(
            asiento=asiento,
            secuencia=secuencia,
            cuenta=cuenta_devolucion,
            descripcion=(
                "Devolución de dinero al cliente "
                f"por NC {nota.numero:06d}"
            ),
            debe=Decimal("0.00"),
            haber=monto_devuelto,
            referencia=referencia,
        )

        secuencia += 1


    # ========================================================
    # 19. REVERSIÓN DEL COSTO DE VENTA
    #
    # DEBE  INVENTARIO
    # HABER COSTO DE VENTAS
    # ========================================================

    for item in reversiones_costo:

        costo_total = (
            item["costo_total"]
        )

        if costo_total <= Decimal("0.00"):
            continue

        producto = item["producto"]

        # DEBE INVENTARIO

        DetalleAsiento.objects.create(
            asiento=asiento,
            secuencia=secuencia,
            cuenta=item["cuenta_inventario"],
            descripcion=(
                "Reingreso a inventario por "
                f"NC {nota.numero:06d} - "
                f"{producto.descripcion}"
            ),
            debe=costo_total,
            haber=Decimal("0.00"),
            referencia=referencia,
        )

        secuencia += 1

        # HABER COSTO DE VENTAS

        DetalleAsiento.objects.create(
            asiento=asiento,
            secuencia=secuencia,
            cuenta=item["cuenta_costo"],
            descripcion=(
                "Reversión de costo de venta por "
                f"NC {nota.numero:06d} - "
                f"{producto.descripcion}"
            ),
            debe=Decimal("0.00"),
            haber=costo_total,
            referencia=referencia,
        )

        secuencia += 1


    # ========================================================
    # 20. CONTABILIZAR ASIENTO
    # ========================================================

    contabilizar_asiento(
        asiento
    )


    # ========================================================
    # 21. ACTUALIZAR SALDO DEL TICKET
    # ========================================================

    monto_aplicado = (
        nota.monto_aplicado_saldo
        or Decimal("0.00")
    )

    if monto_aplicado > Decimal("0.00"):

        ticket = nota.ticket

        saldo_actual = Decimal(
            ticket.saldo
            or Decimal("0.00")
        )

        nuevo_saldo = (
            saldo_actual
            - monto_aplicado
        )

        if nuevo_saldo < Decimal("0.00"):
            raise ValidationError(
                "La nota de crédito produciría "
                "un saldo negativo en el ticket."
            )

        ticket.saldo = nuevo_saldo

        ticket.save(
            update_fields=[
                "saldo",
            ]
        )


    # ========================================================
    # 22. MARCAR NOTA COMO CONTABILIZADA
    #
    # Esto debe ocurrir ANTES de recalcular Kardex porque
    # core/kardex.py solo toma NC CONTABILIZADAS.
    # ========================================================

    nota.asiento = asiento

    nota.estado = (
        NotaCredito
        .Estado
        .CONTABILIZADA
    )

    nota.contabilizado_en = (
        timezone.now()
    )

    nota.save(
        update_fields=[
            "asiento",
            "estado",
            "contabilizado_en",
        ]
    )


    # ========================================================
    # 23. RECALCULAR KARDEX DE LOS PRODUCTOS DEVUELTOS
    # ========================================================

    productos_recalcular = {}

    for item in reversiones_costo:

        producto = item["producto"]

        productos_recalcular[
            producto.id
        ] = producto

    for producto in productos_recalcular.values():

        recalcular_kardex_producto(
            producto
        )


    # ========================================================
    # 24. FINAL
    # ========================================================

    return asiento