from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Profile

@receiver(post_save, sender=User)
def create_or_update_profile(sender, instance, created, **kwargs):
    profile, _ = Profile.objects.get_or_create(user=instance)

    # Regla de negocio:
    if instance.is_superuser:
        if profile.rol != Profile.ROLE_ADMIN:
            profile.rol = Profile.ROLE_ADMIN
            profile.save()

