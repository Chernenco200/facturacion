from django.apps import AppConfig


class IncentivosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "incentivos"
    verbose_name = "Puntos IC (incentivos)"

    def ready(self):
        # OJO: el método se llama "ready" (sin s). Si se escribe mal,
        # Django no lo ejecuta y las señales no se registran.
        import incentivos.signals  # noqa: F401
