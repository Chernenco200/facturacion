"""
Horario de acceso al sistema para los trabajadores de Puntos IC.

- Lunes a sábado: de la apertura (9:00) al cierre (19:45) + un margen para
  terminar una venta (ACCESO_MARGEN_FIN, 15 min).
- Domingos y feriados: solo quien tiene turno ese día, de 10:30 a 18:00 + margen.

Fuera de ese horario la sesión se cierra y se vuelve al login con un aviso.
No aplica a la gerencia, a los superusuarios ni a usuarios que no estén en
Puntos IC (por ejemplo, el usuario de la pantalla de TV).
La pantalla de marcación funciona siempre: no usa la sesión.
"""
import logging
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect

log = logging.getLogger(__name__)

RUTAS_LIBRES = (
    "/accounts/login", "/accounts/logout", "/admin/login", "/incentivos/marcar",
    "/static/", "/media/", "/webhook/", "/favicon",
)


def dentro_de_horario(usuario, momento=None):
    from .horario import es_domingo_o_feriado, horario_del_dia
    from .models import Turno
    from .params import P
    from .tiempo import LIMA, ahora

    momento = (momento or ahora()).astimezone(LIMA)
    hoy = momento.date()
    if es_domingo_o_feriado(hoy) and not Turno.objects.filter(usuario=usuario, fecha=hoy).exists():
        return False
    ini, fin = horario_del_dia(hoy)
    abre = datetime.combine(hoy, ini).replace(tzinfo=LIMA)
    cierra = datetime.combine(hoy, fin).replace(tzinfo=LIMA) + timedelta(minutes=P("ACCESO_MARGEN_FIN"))
    return abre <= momento <= cierra


class HorarioAccesoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            bloquear = self._debe_bloquear(request)
        except Exception:  # ante cualquier error, nunca dejar a nadie fuera del sistema
            log.exception("Puntos IC: error revisando el horario de acceso")
            bloquear = False
        if bloquear:
            logout(request)
            messages.warning(request, "Fuera del horario de trabajo: el sistema se usa de 9:00 a. m. a 7:45 p. m. "
                                      "(domingos y feriados, según tu turno).")
            return redirect("accounts:login")
        return self.get_response(request)

    def _debe_bloquear(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or user.is_superuser:
            return False
        if request.path.startswith(RUTAS_LIBRES):
            return False
        from .params import P
        from .services import es_gerencia, trabajador_de

        if not P("ACCESO_CONTROL"):
            return False
        if trabajador_de(user) is None or es_gerencia(user):
            return False
        return not dentro_de_horario(user)
