"""
Si alguien borra las fotos de una montura (desde el admin, la ficha o
cualquier otra pantalla), se revierten los puntos de la tarea FOTO.

Las señales nunca deben romper el guardado del producto: todo va dentro
de try/except y solo se registra el error en el log.
"""
import logging

from django.db import transaction
from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver

from core.models import Producto

log = logging.getLogger(__name__)
CAMPOS = ("imagenF", "imagenD", "imagenL")


def _toca_imagenes(update_fields):
    return update_fields is None or any(c in update_fields for c in CAMPOS)


@receiver(pre_save, sender=Producto, dispatch_uid="ic_producto_pre_save")
def ic_guardar_imagenes_previas(sender, instance, raw=False, update_fields=None, **kwargs):
    instance._ic_imgs_previas = None
    if raw or not instance.pk or not _toca_imagenes(update_fields):
        return
    try:
        instance._ic_imgs_previas = (
            Producto.objects.filter(pk=instance.pk).values_list(*CAMPOS).first()
        )
    except Exception:
        log.exception("Puntos IC: no se pudo leer imágenes previas del producto %s", instance.pk)


@receiver(post_save, sender=Producto, dispatch_uid="ic_producto_post_save")
def ic_revertir_si_borran_fotos(sender, instance, raw=False, **kwargs):
    previas = getattr(instance, "_ic_imgs_previas", None)
    if raw or not previas:
        return
    try:
        actuales = [getattr(instance, c) for c in CAMPOS]
        borradas = [c for c, antes, ahora in zip(CAMPOS, previas, actuales) if antes and not ahora]
        if borradas:
            from .services import revertir_fotos_producto

            pid = instance.pk
            transaction.on_commit(lambda: revertir_fotos_producto(
                pid, "Imágenes borradas desde la ficha del producto (" + ", ".join(borradas) + ")"))
    except Exception:
        log.exception("Puntos IC: error al revisar imágenes del producto %s", instance.pk)


@receiver(pre_delete, sender=Producto, dispatch_uid="ic_producto_pre_delete")
def ic_revertir_si_borran_producto(sender, instance, **kwargs):
    try:
        from .services import revertir_fotos_producto

        revertir_fotos_producto(instance.pk, "Producto eliminado")
    except Exception:
        log.exception("Puntos IC: error al revertir fotos del producto eliminado %s", instance.pk)
