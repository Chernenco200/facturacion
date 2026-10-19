"""
Anulación de ventas (recibos internos) ingresadas por error.

Solo dentro de un mes contable abierto: los asientos de la venta,
su costo, sus cobros y, si se pide, los pagos a proveedores de sus
compras directas, quedan ANULADOS (siguen en el historial pero no
suman en ningún reporte). El recibo se elimina y los productos
vuelven al stock. Queda constancia en VentaAnulada.

Si el mes ya se cerró, o la venta tiene notas de crédito, se debe
usar una nota de crédito.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from .models import (
    AsientoContable,
    CompraDirectaVenta,
    NotaCredito,
    PagoProveedor,
    PeriodoContable,
    PropuestaCostoVenta,
    ServicioTerceroVenta,
    VentaAnulada,
)


def _asientos_activos(filtro):
    return (
        AsientoContable.objects
        .filter(filtro)
        .exclude(estado=AsientoContable.Estado.ANULADO)
        .select_related("periodo")
    )


def revisar_anulacion(ticket):
    """
    Devuelve un dict con lo que implicaría anular la venta:

        bloqueos: motivos que impiden anularla (lista vacía = se puede)
        asientos: asientos de la venta que quedarían anulados
        compras / servicios: costos con terceros asociados
        pagos_proveedor: pagos que se anularían con las compras
        requiere_confirmar_compras: hay compras o servicios con
            efecto contable que se perderían
    """

    from core.models import MovimientoCaja

    bloqueos = []

    if NotaCredito.objects.filter(ticket=ticket).exists():
        bloqueos.append(
            "La venta tiene notas de crédito; corrígela con otra nota de crédito."
        )

    pagos_ids = list(ticket.pagos.values_list("id", flat=True))

    asientos = list(
        _asientos_activos(
            Q(origen__in=["VENTA", "COSTO_VENTA"], origen_id=ticket.id)
            | Q(origen="COBRO_TICKET", origen_id__in=pagos_ids)
        ).order_by("fecha", "numero")
    )

    propuesta = PropuestaCostoVenta.objects.filter(ticket=ticket).first()

    compras = []
    servicios = []
    pagos_proveedor = []
    asientos_pagos = []

    if propuesta:

        compras = list(
            CompraDirectaVenta.objects
            .filter(detalle_costo__propuesta=propuesta)
            .select_related("detalle_costo__detalle_ticket")
        )

        servicios = list(
            ServicioTerceroVenta.objects.filter(
                propuesta=propuesta,
                estado=ServicioTerceroVenta.Estado.CONTABILIZADO,
                costo__gt=0,
            )
        )

        pagos_proveedor = list(
            PagoProveedor.objects
            .filter(compra__in=compras)
            .exclude(estado=PagoProveedor.Estado.ANULADO)
        )

        asientos_pagos = list(
            _asientos_activos(
                Q(
                    origen="PAGO_PROVEEDOR",
                    origen_id__in=[pago.id for pago in pagos_proveedor],
                )
            )
        )

    todos = asientos + asientos_pagos

    periodos_cerrados = sorted({
        str(asiento.periodo)
        for asiento in todos
        if asiento.periodo.estado == PeriodoContable.Estado.CERRADO
    })

    if periodos_cerrados:
        bloqueos.append(
            "Tiene asientos en períodos ya cerrados ("
            + ", ".join(periodos_cerrados)
            + "); en ese caso corresponde una nota de crédito."
        )

    if MovimientoCaja.objects.filter(ticket=ticket, caja__cerrada=True).exists():
        bloqueos.append(
            "Sus cobros están en una caja ya cerrada; reabre la caja o usa "
            "una nota de crédito."
        )

    compras_con_efecto = [
        compra for compra in compras
        if compra.estado == CompraDirectaVenta.Estado.CONTABILIZADA
        or any(pago.compra_id == compra.id for pago in pagos_proveedor)
    ]

    return {
        "bloqueos": bloqueos,
        "asientos": asientos,
        "asientos_pagos": asientos_pagos,
        "propuesta": propuesta,
        "compras": compras,
        "compras_con_efecto": compras_con_efecto,
        "servicios": servicios,
        "pagos_proveedor": pagos_proveedor,
        "requiere_confirmar_compras": bool(compras_con_efecto or servicios),
    }


def _marcar_anulado(asiento, numero_recibo):
    sufijo = f" [ANULADO - recibo {numero_recibo:06d}]"
    asiento.glosa = (asiento.glosa[: 500 - len(sufijo)] + sufijo)
    asiento.estado = AsientoContable.Estado.ANULADO
    asiento.save(update_fields=["glosa", "estado", "actualizado_en"])


@transaction.atomic
def anular_venta(ticket, motivo, usuario=None, anular_compras=False):
    """
    Anula la venta. Lanza ValidationError si no se puede.
    Devuelve el registro VentaAnulada.
    """

    from core.kardex import recalcular_kardex_producto
    from core.models import MovimientoCaja, TicketVenta

    # Bloquea el recibo para que nadie lo modifique a la vez.
    ticket = TicketVenta.objects.select_for_update().get(pk=ticket.pk)

    motivo = (motivo or "").strip()

    if len(motivo) < 5:
        raise ValidationError("Escribe el motivo de la anulación.")

    revision = revisar_anulacion(ticket)

    if revision["bloqueos"]:
        raise ValidationError(revision["bloqueos"])

    if revision["requiere_confirmar_compras"] and not anular_compras:
        raise ValidationError(
            "La venta tiene compras a proveedores o servicios de terceros "
            "contabilizados. Confirma que también fueron parte del error; "
            "si la compra sí ocurrió, usa una nota de crédito."
        )

    numero = ticket.numero

    # --------------------------------------------------------
    # Copia de lo que se elimina (para el registro)
    # --------------------------------------------------------

    detalle = {
        "productos": [
            {
                "codigo": d.producto.cod if d.producto_id else "",
                "descripcion": d.descripcion,
                "cantidad": str(d.cantidad),
                "precio": str(d.precio),
            }
            for d in ticket.detalles.select_related("producto")
        ],
        "pagos": [
            {
                "medio": p.medio_pago,
                "monto": str(p.monto),
            }
            for p in ticket.pagos.all()
        ],
        "asientos_anulados": [
            {
                "numero": a.numero,
                "periodo": str(a.periodo),
                "origen": a.origen,
                "total": str(a.total_debe),
            }
            for a in revision["asientos"] + revision["asientos_pagos"]
        ],
        "compras_anuladas": [
            {
                "proveedor": c.proveedor_nombre,
                "documento": c.numero_documento,
                "total": str(c.costo_total),
            }
            for c in revision["compras"]
        ],
        "servicios_anulados": [
            {
                "proveedor": s.proveedor_nombre,
                "descripcion": s.descripcion,
                "costo": str(s.costo),
            }
            for s in revision["servicios"]
        ],
    }

    productos = {
        d.producto
        for d in ticket.detalles.select_related("producto")
        if d.producto_id
    }

    # --------------------------------------------------------
    # 1. Anular asientos (venta, costo, cobros, pagos proveedor)
    # --------------------------------------------------------

    for asiento in revision["asientos"] + revision["asientos_pagos"]:
        _marcar_anulado(asiento, numero)

    # --------------------------------------------------------
    # 2. Eliminar lo que depende del recibo
    # --------------------------------------------------------

    MovimientoCaja.objects.filter(ticket=ticket).delete()

    propuesta = revision["propuesta"]

    if propuesta:
        # Orden por las relaciones protegidas:
        # pagos -> compras -> detalle de costo -> propuesta.
        PagoProveedor.objects.filter(
            compra__detalle_costo__propuesta=propuesta,
        ).delete()

        CompraDirectaVenta.objects.filter(
            detalle_costo__propuesta=propuesta,
        ).delete()

        ServicioTerceroVenta.objects.filter(propuesta=propuesta).delete()

        propuesta.delete()

    registro = VentaAnulada.objects.create(
        numero_recibo=numero,
        fecha_venta=ticket.fecha_emision,
        cliente=str(ticket.cliente) if ticket.cliente_id else "",
        total=Decimal(ticket.total or 0),
        motivo=motivo,
        compras_anuladas=bool(
            revision["compras"] or revision["servicios"]
        ),
        detalle=detalle,
        usuario=usuario if getattr(usuario, "is_authenticated", False) else None,
    )

    # Borra detalles, pagos y orden de trabajo (CASCADE).
    ticket.delete()

    # --------------------------------------------------------
    # 3. Devolver productos al stock
    # --------------------------------------------------------

    for producto in productos:
        recalcular_kardex_producto(producto)

    return registro
