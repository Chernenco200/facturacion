"""Genera las tareas que faltan en la cola (también se hace solo al presionar 'Siguiente tarea')."""
from django.core.management.base import BaseCommand

from incentivos import services as S


class Command(BaseCommand):
    help = "Genera tareas FOTO, COD, WA_LISTA, WA_RESP, INV y TEL que falten."

    def handle(self, *args, **opts):
        self.stdout.write(str(S.generar_tareas(forzar=True)))
