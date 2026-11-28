from django.conf import settings
from django.db import models
from django.utils import timezone


def numero_normalizado(numero):
    """
    Guarda siempre el celular peruano como 51 + 9 dígitos (ej. 51987654321).
    Antes algunos mensajes se guardaban sin el 51 y el bot no los veía en
    el historial. Si el número no es un celular peruano, se deja igual.
    """
    if not numero:
        return numero
    dig = "".join(c for c in str(numero) if c.isdigit())
    while dig.startswith("5151") and len(dig) > 11:
        dig = dig[2:]
    if len(dig) == 9 and dig.startswith("9"):
        dig = "51" + dig
    if len(dig) == 11 and dig.startswith("51"):
        return dig
    return str(numero).strip()

class ConversacionWhatsApp(models.Model):
    numero = models.CharField(max_length=20, unique=True)

    MODO_CHOICES = [
        ("BOT", "Bot"),
        ("HUMANO", "Humano"),
    ]

    ESTADO_CHOICES = [
        ("INICIO", "Inicio"),
        ("ESPERANDO_TICKET", "Esperando Ticket"),
        ("ESPERANDO_DATOS_CITA", "Esperando Datos Cita"),
        ("ESPERANDO_CONFIRMACION_ASESOR", "Esperando Confirmación Asesor"),
        ("ASESOR", "Asesor"),
        ("FINALIZADO", "Finalizado"),
    ]

    modo = models.CharField(max_length=20, choices=MODO_CHOICES, default="BOT")
    estado = models.CharField(max_length=50, choices=ESTADO_CHOICES, default="INICIO")
    actualizado = models.DateTimeField(auto_now=True)
    # Desde cuándo está en el estado o modo actual (para que los estados de espera caduquen)
    estado_desde = models.DateTimeField(null=True, blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._estado_inicial = (self.estado, self.modo)

    def save(self, *args, **kwargs):
        if self._state.adding or (self.estado, self.modo) != self._estado_inicial or not self.estado_desde:
            self.estado_desde = timezone.now()
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = list(set(kwargs["update_fields"]) | {"estado_desde"})
        super().save(*args, **kwargs)
        self._estado_inicial = (self.estado, self.modo)

    def __str__(self):
        return f"{self.numero} - {self.modo} - {self.estado}"        


class CitaWhatsApp(models.Model):
    numero = models.CharField(max_length=20)
    datos_cliente = models.TextField()
    atendido = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.numero = numero_normalizado(self.numero)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Cita {self.numero} - {self.creado}"


class MensajeWhatsApp(models.Model):

    TIPO_CHOICES = [
        ("ENTRANTE", "Entrante"),
        ("SALIENTE", "Saliente"),
    ]

    ESTADO_CHOICES = [
        ("PENDIENTE", "Pendiente"),
        ("ENVIADO", "Enviado"),
        ("ENTREGADO", "Entregado"),
        ("LEIDO", "Leído"),
        ("FALLIDO", "Fallido"),
    ]

    numero = models.CharField(max_length=20)
    nombre = models.CharField(max_length=150, blank=True, null=True)

    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CHOICES
    )

    mensaje = models.TextField(blank=True, null=True)

    archivo = models.FileField(
        upload_to="whatsapp_archivos/",
        blank=True,
        null=True
    )

    wa_message_id = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        db_index=True,
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default="PENDIENTE",
    )

    leido = models.BooleanField(default=False)

    creado = models.DateTimeField(auto_now_add=True)

    # Quién respondió a mano desde la bandeja (vacío: bot, plantilla o envío automático)
    enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="mensajes_whatsapp_enviados",
    )

    def save(self, *args, **kwargs):
        self.numero = numero_normalizado(self.numero)
        super().save(*args, **kwargs)

    class Meta:
        ordering = ["creado"]

    def __str__(self):
        return f"{self.numero} - {self.tipo}"