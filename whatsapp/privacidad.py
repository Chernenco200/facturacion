"""
Privacidad de números de celular.

Solo ADMIN, SUPERVISOR y superusuarios ven el número completo.
El resto de roles (VENDEDOR, CAJA, TALLER) ve una versión enmascarada,
por ejemplo: +51 987 *** 321

El enmascarado se hace en el servidor: el número completo nunca llega
al navegador de un vendedor, ni siquiera en el HTML o en la URL.
"""

ROLES_VEN_NUMERO_COMPLETO = {"ADMIN", "SUPERVISOR"}


def puede_ver_numero_completo(user):
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    profile = getattr(user, "profile", None)
    rol = (getattr(profile, "rol", "") or "").upper()
    return rol in ROLES_VEN_NUMERO_COMPLETO


def enmascarar_numero(numero):
    """
    51987654321 -> +51 987 *** 321
    987654321   -> 987 *** 321
    Cualquier otro formato: solo deja visibles los 3 últimos dígitos.
    """
    if not numero:
        return ""

    digitos = "".join(c for c in str(numero) if c.isdigit())

    if len(digitos) == 11 and digitos.startswith("51"):
        return f"+51 {digitos[2:5]} *** {digitos[-3:]}"

    if len(digitos) == 9:
        return f"{digitos[:3]} *** {digitos[-3:]}"

    if len(digitos) <= 3:
        return "***"

    return "*" * (len(digitos) - 3) + digitos[-3:]


def numero_para_usuario(numero, user):
    """Devuelve el número completo o enmascarado según el rol."""
    if puede_ver_numero_completo(user):
        return numero
    return enmascarar_numero(numero)
