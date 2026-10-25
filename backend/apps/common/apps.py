from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"
    verbose_name = "Socle commun"

    def ready(self):
        _restrict_django_admin()


def _restrict_django_admin():
    """``is_staff`` ouvre les menus SPA filiale, pas /django-admin/.

    Django admin n'est pas scopé par filiale : un admin filiale qui y
    entrerait verrait et pourrait modifier les dossiers des autres
    filiales. On le réserve donc au superuser et au niveau Groupe.
    """
    from django.contrib import admin

    def has_permission(request):
        user = getattr(request, "user", None)
        if not (
            user
            and user.is_authenticated
            and user.is_active
            and user.is_staff
        ):
            return False
        return bool(
            user.is_superuser or getattr(user, "is_group_level", False)
        )

    admin.site.has_permission = has_permission
