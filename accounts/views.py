from django.shortcuts import render

# Create your views here.
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.shortcuts import get_object_or_404, redirect, render

from .decorators import role_required
from .forms import LoginForm, UserCreateForm, UserUpdateForm, PasswordResetByAdminForm
from .models import Profile

class CustomLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm

def logout_view(request):
    logout(request)
    return redirect("accounts:login")

# ============================================================
# REGLAS DE GESTIÓN DE USUARIOS
#
#   - Un superusuario o usuario staff solo lo gestiona otro superusuario
#     (si no, cualquiera podría cambiarle la contraseña y entrar a
#     Contabilidad).
#   - Un usuario con rol ADMIN solo lo gestiona un ADMIN o superusuario.
#   - Un SUPERVISOR gestiona los demás perfiles, pero no puede asignar
#     el rol ADMIN (ni a otros ni a sí mismo).
# ============================================================

def _rol(user):
    profile = getattr(user, "profile", None)
    return getattr(profile, "rol", None)


def _es_admin(actor):
    return actor.is_superuser or _rol(actor) == Profile.ROLE_ADMIN


def puede_gestionar(actor, objetivo):
    if objetivo.is_superuser or objetivo.is_staff:
        return actor.is_superuser

    if _rol(objetivo) == Profile.ROLE_ADMIN:
        return _es_admin(actor)

    return True


def roles_asignables(actor):
    if _es_admin(actor):
        return list(Profile.ROLE_CHOICES)

    return [
        (valor, etiqueta)
        for valor, etiqueta in Profile.ROLE_CHOICES
        if valor != Profile.ROLE_ADMIN
    ]


def _sin_permiso(request, objetivo):
    messages.error(
        request,
        f"No tienes permiso para modificar al usuario {objetivo.username}.",
    )
    return redirect("accounts:usuarios_list")


@role_required("ADMIN", "SUPERVISOR")
def usuarios_list(request):
    users = list(User.objects.select_related("profile").order_by("username"))

    for u in users:
        u.puede_gestionar = puede_gestionar(request.user, u)

    return render(request, "accounts/usuarios_list.html", {"users": users})


@role_required("ADMIN", "SUPERVISOR")
def usuarios_create(request):
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        form.fields["rol"].choices = roles_asignables(request.user)

        if form.is_valid():
            form.save()
            messages.success(request, "Usuario creado correctamente.")
            return redirect("accounts:usuarios_list")
    else:
        form = UserCreateForm(initial={"is_active": True})
        form.fields["rol"].choices = roles_asignables(request.user)

    return render(request, "accounts/usuarios_form.html", {"form": form, "title": "Crear usuario"})


@role_required("ADMIN", "SUPERVISOR")
def usuarios_update(request, user_id):
    u = get_object_or_404(User.objects.select_related("profile"), pk=user_id)

    if not puede_gestionar(request.user, u):
        return _sin_permiso(request, u)

    if request.method == "POST":
        form = UserUpdateForm(request.POST, instance=u)
        form.fields["rol"].choices = roles_asignables(request.user)

        if form.is_valid():
            if u.pk == request.user.pk and not form.cleaned_data.get("is_active"):
                messages.warning(request, "No puedes desactivar tu propio usuario.")
                return redirect("accounts:usuarios_list")

            user = form.save()
            user.profile.rol = form.cleaned_data["rol"]
            user.profile.save()
            messages.success(request, "Usuario actualizado.")
            return redirect("accounts:usuarios_list")
    else:
        form = UserUpdateForm(instance=u, initial={"rol": u.profile.rol})
        form.fields["rol"].choices = roles_asignables(request.user)

    return render(request, "accounts/usuarios_form.html", {"form": form, "title": f"Editar: {u.username}"})


@role_required("ADMIN", "SUPERVISOR")
def usuarios_toggle_active(request, user_id):
    u = get_object_or_404(User, pk=user_id)

    # Solo por formulario (POST): un enlace no debe cambiar cuentas.
    if request.method != "POST":
        return redirect("accounts:usuarios_list")

    if not puede_gestionar(request.user, u):
        return _sin_permiso(request, u)

    if u.pk == request.user.pk:
        messages.warning(request, "No puedes desactivar tu propio usuario.")
        return redirect("accounts:usuarios_list")

    u.is_active = not u.is_active
    u.save()
    messages.success(request, f"Estado actualizado: {u.username} -> {'ACTIVO' if u.is_active else 'INACTIVO'}")
    return redirect("accounts:usuarios_list")


@role_required("ADMIN", "SUPERVISOR")
def usuarios_reset_password(request, user_id):
    u = get_object_or_404(User, pk=user_id)

    if not puede_gestionar(request.user, u):
        return _sin_permiso(request, u)

    if request.method == "POST":
        form = PasswordResetByAdminForm(request.POST)
        if form.is_valid():
            u.set_password(form.cleaned_data["password1"])
            u.save()
            messages.success(request, "Contraseña actualizada.")
            return redirect("accounts:usuarios_list")
    else:
        form = PasswordResetByAdminForm()
    return render(request, "accounts/reset_password.html", {"form": form, "u": u})
