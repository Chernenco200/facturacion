"""
Horario de la tienda y feriados.

- Lunes a sábado: 9:00 a 19:45.
- Domingos y feriados: 10:30 a 18:00.

Los valores y la lista de feriados se cambian en /incentivos/configuracion/.
"""
from datetime import date, datetime, timedelta

from .params import P
from .tiempo import LIMA, ahora as _ahora

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def feriados():
    res = set()
    for texto in P("FERIADOS"):
        try:
            res.add(date.fromisoformat(texto))
        except ValueError:
            continue
    return res


def es_feriado(fecha):
    return fecha in feriados()


def es_domingo_o_feriado(fecha):
    return fecha.weekday() == 6 or es_feriado(fecha)


def horario_del_dia(fecha):
    """(hora de apertura, hora de cierre) de ese día."""
    if es_domingo_o_feriado(fecha):
        return P("HORARIO_DF_INICIO", fecha), P("HORARIO_DF_FIN", fecha)
    return P("HORARIO_LS_INICIO", fecha), P("HORARIO_LS_FIN", fecha)


def _texto_hora(h):
    sufijo = "a. m." if h.hour < 12 else "p. m."
    hh = h.hour if h.hour <= 12 else h.hour - 12
    return f"{hh}:{h.minute:02d} {sufijo}"


def tienda_abierta(momento=None):
    """(abierta, texto de la próxima apertura, por ejemplo 'mañana a las 9:00 a. m.')."""
    momento = (momento or _ahora()).astimezone(LIMA)
    hoy = momento.date()
    ini, fin = horario_del_dia(hoy)
    abre = datetime.combine(hoy, ini).replace(tzinfo=LIMA)
    cierra = datetime.combine(hoy, fin).replace(tzinfo=LIMA)
    if abre <= momento < cierra:
        return True, "en breve"
    if momento < abre:
        return False, f"hoy a las {_texto_hora(ini)}"
    manana = hoy + timedelta(days=1)
    return False, f"mañana {DIAS[manana.weekday()]} a las {_texto_hora(horario_del_dia(manana)[0])}"
