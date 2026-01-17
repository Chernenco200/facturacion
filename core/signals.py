from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import DetalleCompra, DetalleTicketVenta
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

