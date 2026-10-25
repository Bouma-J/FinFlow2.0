from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = "Utilisateurs et habilitations"

    def ready(self):
        from . import audit_signals  # noqa: F401
