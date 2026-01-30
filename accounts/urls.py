from django.urls import path
from .views import (
    CustomLoginView, logout_view,
    usuarios_list, usuarios_create, usuarios_update,
    usuarios_toggle_active, usuarios_reset_password
)

app_name = "accounts"

urlpatterns = [
    path("login/", CustomLoginView.as_view(), name="login"),
    path("logout/", logout_view, name="logout"),

    path("usuarios/", usuarios_list, name="usuarios_list"),
    path("usuarios/nuevo/", usuarios_create, name="usuarios_create"),
    path("usuarios/<int:user_id>/editar/", usuarios_update, name="usuarios_update"),
    path("usuarios/<int:user_id>/toggle/", usuarios_toggle_active, name="usuarios_toggle_active"),
    path("usuarios/<int:user_id>/reset-password/", usuarios_reset_password, name="usuarios_reset_password"),
]
