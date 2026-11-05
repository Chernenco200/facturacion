from django.urls import path
from .views import whatsapp_webhook

from . import views

urlpatterns = [
    path("webhook/whatsapp/", whatsapp_webhook, name="whatsapp_webhook"),

    path("whatsapp/bandeja/", views.bandeja_whatsapp, name="bandeja_whatsapp"),
    # Se usa el ID de la conversación, no el número de celular,
    # para que el número no quede en la URL ni en el historial del navegador.
    path("whatsapp/chat/<int:conversacion_id>/", views.chat_whatsapp, name="chat_whatsapp"),
    path("whatsapp/chat/<int:conversacion_id>/modo/", views.cambiar_modo_whatsapp, name="cambiar_modo_whatsapp"),

    path(
        "webhook/facebook/",
        views.webhook_facebook,
        name="webhook_facebook"
    ),

]