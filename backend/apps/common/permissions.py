"""Permissions réutilisables (RBAC)."""
from rest_framework.permissions import BasePermission, SAFE_METHODS


def is_configuration_administrator(user):
    """Même fonction d'administration que dans l'interface, sans nom de rôle."""
    if not user or not user.is_authenticated or not user.is_active:
        return False
    from apps.accounts.capabilities import TENANT_ADMIN, user_has_capability

    return bool(user.is_superuser or (user.is_group_level and user.is_staff)
                or user_has_capability(user, TENANT_ADMIN))


class IsConfigurationAdministrator(BasePermission):
    message = "Le paramétrage est réservé aux administrateurs habilités."

    def has_permission(self, request, view):
        return is_configuration_administrator(request.user)


class IsGroupLevel(BasePermission):
    """Autorise uniquement les utilisateurs de niveau Groupe."""

    message = "Accès réservé aux utilisateurs de niveau Groupe."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "is_group_level", False)
        )


class IsGroupAdministrator(BasePermission):
    """Le périmètre Groupe seul ne confère pas les droits d'administration."""

    message = "Accès réservé aux administrateurs Groupe."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (
            user.is_superuser or (user.is_group_level and user.is_staff)
        ))


class MustChangePasswordGate(BasePermission):
    """
    Tant que ``must_change_password`` est vrai, n'autorise que le profil,
    le changement de mot de passe et la déconnexion.
    """

    message = (
        "Vous devez changer votre mot de passe avant d'accéder à l'application."
    )

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return True
        if not getattr(user, "must_change_password", False):
            return True
        if request.method == "OPTIONS":
            return True

        action = getattr(view, "action", None)
        view_name = (getattr(view, "__class__", type(view)).__name__ or "").lower()

        if action in {"me", "change_password"}:
            return True
        if action == "create" and "logout" in view_name:
            return True
        # Vues JWT logout non-viewset
        path = (request.path or "").rstrip("/") + "/"
        if path.endswith("/auth/logout/") or path.endswith("/users/me/"):
            return True
        if path.endswith("/users/me/change-password/"):
            return True
        return False


class HasDashboardPermission(BasePermission):
    """Consulter le tableau de bord opérationnel (reporting.view_dashboard)."""

    message = "Droit insuffisant pour consulter le tableau de bord."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        return user.has_perm("reporting.view_dashboard")


class HasModelPermission(BasePermission):
    """
    Contrôle d'accès basé sur les permissions Django (RBAC).

    Ordre d'évaluation :
    1. Superutilisateur → autorisé
    2. `view.action_perms[action]` si défini (liste de codenames ; [] = authentifié)
    3. `view.required_perms` (liste statique)
    4. Si `view.enforce_model_permissions` : mappe la méthode HTTP
       vers view/add/change/delete du modèle du queryset
    5. Sinon → autorisé (compatibilité vues non migrées)
    """

    message = "Droit insuffisant pour cette action."

    _METHOD_TO_ACTION = {
        "GET": "view",
        "HEAD": "view",
        "OPTIONS": "view",
        "POST": "add",
        "PUT": "change",
        "PATCH": "change",
        "DELETE": "delete",
    }

    # Les référentiels restent consultables par les formulaires métier selon
    # leurs permissions. Leur administration exige aussi la fonction admin.
    _PARAMETER_MODELS = {
        "workflow.workflowdefinition", "workflow.approvalstep", "workflow.businesscalendar",
        "credits.analysisthreshold", "credits.creditinstructionpolicy",
        "contracts.contracttemplate", "documents.documentcategory",
        "corebanking.corebankingconnector", "collections.collectiontranche",
        "collections.collectionescalationrule", "tenants.agency", "accounts.tenantrole",
    }

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        # Même si une vue omet MustChangePasswordGate dans permission_classes.
        if not MustChangePasswordGate().has_permission(request, view):
            self.message = MustChangePasswordGate.message
            return False
        model = self._model_from_view(view)
        if (
            self._requires_configuration_administrator(model, view)
            and request.method not in SAFE_METHODS
            and not self._is_detail_request(view)
            and not is_configuration_administrator(user)
        ):
            self.message = IsConfigurationAdministrator.message
            return False
        if user.is_superuser:
            return True

        action = getattr(view, "action", None)
        method_perms = (getattr(view, "action_method_perms", None) or {}).get(
            action, {}
        ).get(request.method.upper())
        if method_perms is not None:
            if not method_perms:
                return True
            return user.has_perms(method_perms)

        method_any_perms = (getattr(view, "action_method_any_perms", None) or {}).get(
            action, {}
        ).get(request.method.upper())
        if method_any_perms is not None:
            return any(user.has_perm(perm) for perm in method_any_perms)

        action_perms = getattr(view, "action_perms", None) or {}
        if action is not None and action in action_perms:
            required = action_perms[action]
            if not required:
                return True
            return user.has_perms(required)

        action_any_perms = getattr(view, "action_any_perms", None) or {}
        if action is not None and action in action_any_perms:
            return any(user.has_perm(perm) for perm in action_any_perms[action])

        required = getattr(view, "required_perms", None)
        if required:
            return user.has_perms(required)

        if not getattr(view, "enforce_model_permissions", False):
            return True

        model = self._model_from_view(view)
        if model is None:
            return False

        verb = self._METHOD_TO_ACTION.get(request.method.upper())
        if verb is None:
            return False
        # Lecture seule via SAFE_METHODS si la vue le souhaite
        if request.method in SAFE_METHODS and verb != "view":
            verb = "view"

        perm = f"{model._meta.app_label}.{verb}_{model._meta.model_name}"
        return user.has_perm(perm)

    def has_object_permission(self, request, view, obj):
        if (
            request.method not in SAFE_METHODS
            and self._requires_configuration_administrator(obj, view)
            and not is_configuration_administrator(request.user)
        ):
            self.message = IsConfigurationAdministrator.message
            return False
        return True

    @classmethod
    def _requires_configuration_administrator(cls, model_or_object, view):
        model = getattr(model_or_object, "_meta", None)
        if model is None:
            model = getattr(getattr(model_or_object, "__class__", None), "_meta", None)
        if model is None:
            return False
        return bool(
            model.app_label in {"catalog", "configuration"}
            or model.label_lower in cls._PARAMETER_MODELS
            or (
                model.label_lower == "accounts.user"
                and getattr(view, "action", None) not in {"me", "change_password"}
            )
        )

    @staticmethod
    def _is_detail_request(view):
        if getattr(view, "detail", False):
            return True
        lookup = getattr(view, "lookup_url_kwarg", None) or "pk"
        return bool(getattr(view, "kwargs", {}).get(lookup))

    @staticmethod
    def _model_from_view(view):
        queryset = getattr(view, "queryset", None)
        if queryset is not None:
            return queryset.model
        get_queryset = getattr(view, "get_queryset", None)
        if callable(get_queryset):
            try:
                return get_queryset().model
            except Exception:  # noqa: BLE001
                return None
        return None
