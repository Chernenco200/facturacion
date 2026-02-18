from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import DetalleCompra, DetalleTicketVenta, recalcular_totales_ticket
from .kardex import recalcular_kardex_producto


@receiver(post_save, sender=DetalleCompra)
@receiver(post_delete, sender=DetalleCompra)
def kardex_por_compra(sender, instance, **kwargs):
    if instance.producto_id:
        recalcular_kardex_producto(instance.producto)


@receiver(post_save, sender=DetalleTicketVenta)
@receiver(post_delete, sender=DetalleTicketVenta)
def kardex_por_venta(sender, instance, **kwargs):
    if instance.producto_id:
        recalcular_kardex_producto(instance.producto)


@receiver(post_save, sender=DetalleTicketVenta)
def detalle_guardado_recalcular(sender, instance, **kwargs):
    recalcular_totales_ticket(instance.ticket_numero)


@receiver(post_delete, sender=DetalleTicketVenta)
def detalle_eliminado_recalcular(sender, instance, **kwargs):
    recalcular_totales_ticket(instance.ticket_numero)
