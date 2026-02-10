from django.shortcuts import render

# Create your views here.
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.shortcuts import get_object_or_404, redirect, render

from .decorators import role_required
from .forms import LoginForm, UserCreateForm, UserUpdateForm, PasswordResetByAdminForm

class CustomLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm

def logout_view(request):
    logout(request)
    return redirect("accounts:login")

@role_required("ADMIN", "SUPERVISOR")
def usuarios_list(request):
    users = User.objects.select_related("profile").order_by("username")
    return render(request, "accounts/usuarios_list.html", {"users": users})

@role_required("ADMIN", "SUPERVISOR")
def usuarios_create(request):
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Usuario creado correctamente.")
            return redirect("accounts:usuarios_list")
    else:
        form = UserCreateForm(initial={"is_active": True})
    return render(request, "accounts/usuarios_form.html", {"form": form, "title": "Crear usuario"})

@role_required("ADMIN", "SUPERVISOR")
def usuarios_update(request, user_id):
    u = get_object_or_404(User.objects.select_related("profile"), pk=user_id)
    if request.method == "POST":
        form = UserUpdateForm(request.POST, instance=u)
        if form.is_valid():
            user = form.save()
            user.profile.rol = form.cleaned_data["rol"]
            user.profile.save()
            messages.success(request, "Usuario actualizado.")
            return redirect("accounts:usuarios_list")
    else:
        form = UserUpdateForm(instance=u, initial={"rol": u.profile.rol})
    return render(request, "accounts/usuarios_form.html", {"form": form, "title": f"Editar: {u.username}"})

@role_required("ADMIN", "SUPERVISOR")
def usuarios_toggle_active(request, user_id):
    u = get_object_or_404(User, pk=user_id)
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
