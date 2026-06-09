from django.urls import path
from .views import whatsapp_webhook

urlpatterns = [
    path("webhook/whatsapp/", whatsapp_webhook, name="whatsapp_webhook"),
]