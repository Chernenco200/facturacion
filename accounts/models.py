from django.db import models

# Create your models here.
from django.db import models
from django.contrib.auth.models import User

class Profile(models.Model):
    ROLE_ADMIN = "ADMIN"
    ROLE_SUPERVISOR = "SUPERVISOR"
    ROLE_VENDEDOR = "VENDEDOR"
    ROLE_CAJA = "CAJA"
    ROLE_TALLER = "TALLER"

    ROLE_CHOICES = [
        (ROLE_ADMIN, "ADMIN"),
        (ROLE_SUPERVISOR, "SUPERVISOR"),
        (ROLE_VENDEDOR, "VENDEDOR"),
        (ROLE_CAJA, "CAJA"),
        (ROLE_TALLER, "TALLER"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    rol = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_VENDEDOR)

    def __str__(self):
        return f"{self.user.username} ({self.rol})"
