from django.db import models

class ConversacionWhatsApp(models.Model):
    numero = models.CharField(max_length=20, unique=True)
    estado = models.CharField(max_length=50, default="INICIO")
    actualizado = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.numero} - {self.estado}"


class CitaWhatsApp(models.Model):
    numero = models.CharField(max_length=20)
    datos_cliente = models.TextField()
    atendido = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Cita {self.numero} - {self.creado}"