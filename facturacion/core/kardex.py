from decimal import Decimal
from datetime import datetime, time
from django.db import transaction
from django.utils import timezone

from .models import Producto, KardexMovimiento, DetalleCompra, DetalleTicketVenta


def _compra_dt(compra):
    # Compra.fecha es DateField
    if getattr(compra, "fecha", None):
        return datetime.combine(compra.fecha, time(0, 0))
    return timezone.now()


def _ticket_dt(ticket):
    # TicketVenta: fecha_emision (DateField) + hora_emision (TimeField)
    fe = getattr(ticket, "fecha_emision", None)
    he = getattr(ticket, "hora_emision", None)
    if fe and he:
        return datetime.combine(fe, he)
    return timezone.now()


@transaction.atomic
def recalcular_kardex_producto(producto: Producto):
    KardexMovimiento.objects.filter(producto=producto).delete()

    stock = Decimal("0")
    costo_prom = Decimal("0")

    eventos = []

    # ENTRADAS: DetalleCompra
    for dc in DetalleCompra.objects.filter(producto=producto).select_related("compra"):
        cantidad = Decimal(str(dc.cantidad or 0))
        costo_in = Decimal(str(dc.precio_compra or 0))
        fecha_dt = _compra_dt(dc.compra)

        eventos.append(("IN", fecha_dt, cantidad, costo_in, dc.compra, None))

    # SALIDAS: DetalleTicketVenta (tu FK se llama ticket_numero)
    for dv in DetalleTicketVenta.objects.filter(producto=producto).select_related("ticket_numero"):
        cantidad = Decimal(str(dv.cantidad or 0))
        fecha_dt = _ticket_dt(dv.ticket_numero)

        eventos.append(("OUT", fecha_dt, cantidad, None, None, dv.ticket_numero))

    eventos.sort(key=lambda x: x[1])

    for tipo, fecha_dt, cantidad, costo_in, compra_ref, ticket_ref in eventos:
        if cantidad <= 0:
            continue

        if tipo == "IN":
            nuevo_stock = stock + cantidad
            nuevo_costo_prom = (
                ((stock * costo_prom) + (cantidad * costo_in)) / nuevo_stock
                if nuevo_stock > 0 else Decimal("0")
            )

            KardexMovimiento.objects.create(
                producto=producto,
                fecha=fecha_dt,
                tipo="IN",
                cantidad=cantidad,
                costo_unitario=costo_in,
                costo_total=cantidad * costo_in,
                stock_anterior=stock,
                stock_actual=nuevo_stock,
                costo_promedio=nuevo_costo_prom,
                compra=compra_ref,
            )
            stock = nuevo_stock
            costo_prom = nuevo_costo_prom

        else:
            nuevo_stock = stock - cantidad

            KardexMovimiento.objects.create(
                producto=producto,
                fecha=fecha_dt,
                tipo="OUT",
                cantidad=cantidad,
                costo_unitario=costo_prom,
                costo_total=cantidad * costo_prom,
                stock_anterior=stock,
                stock_actual=nuevo_stock,
                costo_promedio=costo_prom,
                ticket=ticket_ref,
            )
            stock = nuevo_stock

    # sincroniza stock del producto (en tu modelo es IntegerField)
    producto.stock = int(stock)
    producto.save()


def recalcular_kardex_todo():
    for p in Producto.objects.all():
        recalcular_kardex_producto(p)

