from django.urls import path
from .views import whatsapp_webhook

from . import views

urlpatterns = [
    path("webhook/whatsapp/", whatsapp_webhook, name="whatsapp_webhook"),

    path("whatsapp/bandeja/", views.bandeja_whatsapp, name="bandeja_whatsapp"),
    path("whatsapp/chat/<str:numero>/", views.chat_whatsapp, name="chat_whatsapp"),
    path("whatsapp/chat/<str:numero>/modo/", views.cambiar_modo_whatsapp, name="cambiar_modo_whatsapp"),
]