"""
Uso en plantillas:

    {% load privacidad %}
    {{ cliente.telefono|celular:request.user }}

Sirve para enmascarar teléfonos en cualquier otra pantalla del sistema
(lista de clientes, seguimiento, etc.).
"""

from django import template

from whatsapp.privacidad import numero_para_usuario

register = template.Library()


@register.filter
def celular(numero, user):
    return numero_para_usuario(numero, user)
