"""
Lectura flexible de la hora de entrega de los tickets.

Acepta las formas en que se suele escribir a mano:

    5:30 p. m.   5:30p. m.   5:30pm   5:30 PM   5:30 p.m.
    5.30 pm      5 pm        17:30    09:15 a. m.

"5:30" sin a. m./p. m. no se acepta, porque es ambiguo.

y la guarda siempre igual: "5:30 p. m." / "9:15 a. m.".
"""

import re
from datetime import time


_PATRON_HORA = re.compile(
    r"""^\s*
        (?P<h>\d{1,2})                 # hora
        (?:\s*[:.h]\s*(?P<m>\d{2}))?   # minutos (opcional)
        \s*
        (?:(?P<ampm>[ap])\s*\.?\s*m\s*\.?)?   # a. m. / p. m. (opcional)
        \s*$""",
    re.IGNORECASE | re.VERBOSE,
)


def leer_hora(texto, estricto=True):
    """
    Devuelve un datetime.time, o None si el texto no es una hora válida.

    estricto=True  (al registrar una venta): "5:30" sin a. m./p. m. se
                   rechaza por ambiguo.
    estricto=False (al leer tickets ya guardados): "5:30" se lee en
                   formato de 24 horas, como hacía el sistema antes.
    """

    if not texto:
        return None

    coincidencia = _PATRON_HORA.match(str(texto))
    if not coincidencia:
        return None

    hora = int(coincidencia.group("h"))
    minutos = int(coincidencia.group("m") or 0)
    ampm = (coincidencia.group("ampm") or "").lower()

    if minutos > 59:
        return None

    if ampm:
        if not 1 <= hora <= 12:
            return None
        if ampm == "p" and hora != 12:
            hora += 12
        if ampm == "a" and hora == 12:
            hora = 0
    else:
        # Sin a. m./p. m. solo se acepta el formato de 24 horas cuando
        # no hay duda (13:00 a 23:59). "5:30" podría ser mañana o tarde,
        # así que exige el indicador.
        hora_minima = 13 if estricto else 0

        if coincidencia.group("m") is None or not hora_minima <= hora <= 23:
            return None

    return time(hora, minutos)


def formatear_hora(valor):
    """Convierte un datetime.time al formato del ticket: '5:30 p. m.'."""

    hora12 = valor.hour % 12 or 12
    ampm = "p. m." if valor.hour >= 12 else "a. m."
    return f"{hora12}:{valor.minute:02d} {ampm}"


def normalizar_hora_entrega(texto):
    """
    Devuelve la hora en formato estándar, "" si viene vacía,
    o None si no se reconoce como hora.
    """

    if not texto or not str(texto).strip():
        return ""

    valor = leer_hora(texto)
    return formatear_hora(valor) if valor else None
