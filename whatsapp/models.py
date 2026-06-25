from django.db import models

class ConversacionWhatsApp(models.Model):
    numero = models.CharField(max_length=20, unique=True)

    MODO_CHOICES = [
        ("BOT", "Bot"),
        ("HUMANO", "Humano"),
    ]

    modo = models.CharField(max_length=20, choices=MODO_CHOICES, default="BOT")
    estado = models.CharField(max_length=50, default="INICIO")
    actualizado = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.numero} - {self.modo} - {self.estado}"        


class CitaWhatsApp(models.Model):
    numero = models.CharField(max_length=20)
    datos_cliente = models.TextField()
    atendido = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Cita {self.numero} - {self.creado}"


class MensajeWhatsApp(models.Model):
    TIPO_CHOICES = [
        ("ENTRANTE", "Entrante"),
        ("SALIENTE", "Saliente"),
    ]

    numero = models.CharField(max_length=20)
    nombre = models.CharField(max_length=150, blank=True, null=True)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)

    mensaje = models.TextField(blank=True, null=True)
    archivo = models.FileField(upload_to="whatsapp_archivos/", blank=True, null=True)

    wa_message_id = models.CharField(max_length=150, blank=True, null=True)
    leido = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["creado"]

    def __str__(self):
        return f"{self.numero} - {self.tipo}"