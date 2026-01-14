from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from functools import wraps

def role_required(*allowed_roles):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            profile = getattr(request.user, "profile", None)
            rol = getattr(profile, "rol", None)
            if rol in allowed_roles:
                return view_func(request, *args, **kwargs)
            return HttpResponseForbidden("No tienes permisos para acceder a esta sección.")
        return _wrapped
    return decorator
