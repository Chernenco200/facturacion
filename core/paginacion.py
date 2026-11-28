"""Paginación común para los listados pesados."""
from django.core.paginator import Paginator


def paginar(request, objetos, por_pagina, param="page", quitar=()):
    """
    Devuelve (pagina, filtros): la página pedida y la query string actual sin
    los parámetros de página, para armar los enlaces sin perder los filtros.
    """
    pagina = Paginator(objetos, por_pagina).get_page(request.GET.get(param))
    filtros = request.GET.copy()
    for p in (param, *quitar):
        filtros.pop(p, None)
    return pagina, filtros.urlencode()
