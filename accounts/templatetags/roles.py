from django import template
register = template.Library()

@register.filter
def has_role(user, roles_csv: str):
    if not user.is_authenticated:
        return False
    profile = getattr(user, "profile", None)
    if not profile:
        return False
    roles = [r.strip().upper() for r in roles_csv.split(",") if r.strip()]
    return (profile.rol or "").upper() in roles
