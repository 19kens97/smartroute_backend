from django.apps import AppConfig


class InfractionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.infractions"
    verbose_name = "Infractions routières"

    def ready(self):
        from . import signals  # noqa: F401
