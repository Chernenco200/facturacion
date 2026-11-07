"""
Recálculo automático del kardex.

Antes este archivo nunca se cargaba: en core/apps.py el método se
llamaba `readys` en lugar de `ready`, así que el kardex solo se
recalculaba donde las vistas lo llamaban a mano.

Se activa ÚNICAMENTE el recálculo del kardex, que es idempotente
(reconstruye el producto desde sus documentos). Las señales que
recalculaban el total del ticket se retiraron a propósito: sumaban
cantidad x precio de las líneas y borrarían los descuentos aplicados
al registrar la venta. Esas señales nunca estuvieron activas, por lo
que retirarlas no cambia el comportamiento actual.

Cargas masivas
--------------
Para importar muchas líneas de un mismo producto sin recalcular su
kardex en cada una, usar:

    from core.signals import recalculo_kardex_postergado

    with recalculo_kardex_postergado():
        ... crear o borrar muchos DetalleCompra / DetalleTicketVenta ...

Dentro del bloque solo se anotan los productos afectados; al salir
sin errores se recalcula cada uno UNA vez.
"""

from contextlib import contextmanager
from contextvars import ContextVar

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .kardex import recalcular_kardex_producto
from .models import DetalleCompra, DetalleTicketVenta, Producto

# None = recálculo inmediato; set() = postergado, guarda los ids.
_productos_pendientes = ContextVar("productos_kardex_pendientes", default=None)


@contextmanager
def recalculo_kardex_postergado():
    pendientes = _productos_pendientes.get()
    if pendientes is not None:
        # Ya estamos dentro de otro bloque: lo recalcula el de afuera.
        yield pendientes
        return

    pendientes = set()
    token = _productos_pendientes.set(pendientes)
    try:
        yield pendientes
    finally:
        _productos_pendientes.reset(token)

    for producto in Producto.objects.filter(pk__in=pendientes):
        recalcular_kardex_producto(producto)


@receiver(post_save, sender=DetalleCompra)
@receiver(post_delete, sender=DetalleCompra)
@receiver(post_save, sender=DetalleTicketVenta)
@receiver(post_delete, sender=DetalleTicketVenta)
def actualizar_kardex(sender, instance, raw=False, **kwargs):
    # raw=True: carga de fixtures (loaddata); no hay que recalcular.
    if raw or not instance.producto_id:
        return

    pendientes = _productos_pendientes.get()
    if pendientes is not None:
        pendientes.add(instance.producto_id)
        return

    recalcular_kardex_producto(instance.producto)
