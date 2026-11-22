"""Fechas y horas siempre en hora de Lima, sin depender de settings.TIME_ZONE."""
import calendar
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

LIMA = ZoneInfo("America/Lima")


def ahora():
    return timezone.now().astimezone(LIMA)


def hoy():
    return ahora().date()


def a_lima(dt):
    if dt is None:
        return None
    if timezone.is_naive(dt):
        return dt.replace(tzinfo=LIMA)
    return dt.astimezone(LIMA)


def fecha_local(dt):
    dt = a_lima(dt)
    return dt.date() if dt else None


def combinar(fecha, hora):
    return datetime.combine(fecha, hora).replace(tzinfo=LIMA)


def inicio_dia(fecha):
    return datetime.combine(fecha, datetime.min.time()).replace(tzinfo=LIMA)


def rango_dia(fecha):
    ini = inicio_dia(fecha)
    return ini, ini + timedelta(days=1)


def primer_dia(fecha):
    return fecha.replace(day=1)


def ultimo_dia(fecha):
    return fecha.replace(day=calendar.monthrange(fecha.year, fecha.month)[1])


def dias_del_mes(periodo, hasta=None):
    fin = ultimo_dia(periodo)
    if hasta is not None and hasta < fin:
        fin = hasta
    d = primer_dia(periodo)
    while d <= fin:
        yield d
        d += timedelta(days=1)


def mismo_mes_anio_anterior(periodo):
    return date(periodo.year - 1, periodo.month, 1)


def parse_periodo(texto, defecto=None):
    """'2026-12' -> date(2026,12,1)"""
    try:
        y, m = str(texto).split("-")[:2]
        return date(int(y), int(m), 1)
    except Exception:
        return defecto or primer_dia(hoy())
