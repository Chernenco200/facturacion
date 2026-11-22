"""
Proceso diario de Puntos IC.

Heroku Scheduler (hora UTC): programar "Every day at 04:00 UTC" = 23:00 de Lima:
    python manage.py incentivos_diario

Para reprocesar un día:  python manage.py incentivos_diario --fecha 2026-12-05
"""
from datetime import date

from django.core.management.base import BaseCommand

from incentivos import services as S
from incentivos.tiempo import hoy


class Command(BaseCommand):
    help = "Cierra el día en Puntos IC: faltas, meta, días cumplidos, tareas abiertas y nuevas tareas."

    def add_arguments(self, parser):
        parser.add_argument("--fecha", help="YYYY-MM-DD (por defecto, hoy en Lima)")
        parser.add_argument("--sin-liberar", action="store_true", help="No devolver a la cola las tareas en curso")

    def handle(self, *args, **opts):
        fecha = date.fromisoformat(opts["fecha"]) if opts.get("fecha") else hoy()
        if S.mes_cerrado(fecha):
            self.stdout.write(self.style.WARNING(f"El mes de {fecha} ya está cerrado: no se procesa."))
            return
        resumen = S.procesar_dia(fecha, liberar=not opts["sin_liberar"])
        for nombre, r in resumen:
            self.stdout.write(f"{nombre}: {r['puntos']} pts / meta {r['meta']} "
                              f"({r['tickets']} tickets) -> {'CUMPLIDO' if r['cumplido'] else 'no cumplido'}")
        gen = S.generar_tareas(forzar=True)
        self.stdout.write(f"Tareas nuevas: {gen}")
        self.stdout.write(self.style.SUCCESS(f"Día {fecha} procesado."))
