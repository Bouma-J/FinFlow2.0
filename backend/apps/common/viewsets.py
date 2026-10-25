"""
ViewSets et mixins de base FIN_FLOW.

L'authentification JWT de DRF intervient au niveau de la vue (et non du
middleware Django). La résolution du tenant courant et du contexte
d'audit pour les requêtes API est donc effectuée ici, dans `initial()`,
puis réinitialisée dans `finalize_response()`.

Tout ViewSet exposant des données scopées par filiale DOIT hériter de
`TenantContextMixin` (directement ou via `TenantScopedViewSet` /
`TenantScopedReadOnlyViewSet`).
"""
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated

from .access import apply_data_scope, user_has_agency_access
from .permissions import HasModelPermission, MustChangePasswordGate
from .tenancy import (
    _is_group_context,
    get_current_tenant_id,
    is_group_context,
    reset_current_tenant,
    set_current_tenant,
    set_group_context,
)

TENANT_HEADER = "HTTP_X_TENANT_ID"


class TenantContextMixin:
    """Installe le contexte multi-tenants et d'audit pour la requête."""

    def get_queryset(self):
        """
        Reconstruit un queryset scopé au moment de la requête.

        Indispensable car un attribut de classe `queryset = Model.objects...`
        est évalué à l'import (aucun tenant en contexte) : le manager y
        appliquerait alors un filtrage vide et figé. On reconstruit donc le
        queryset depuis le manager par défaut (scopé sur le tenant courant),
        en conservant les optimisations déclarées (select_related / prefetch).
        """
        declared = self.queryset
        if declared is None:
            return super().get_queryset()

        model = declared.model
        qs = model._default_manager.all()  # scopé au contexte courant

        select_related = declared.query.select_related
        if select_related:
            qs.query.select_related = select_related
        if declared._prefetch_related_lookups:
            qs = qs.prefetch_related(*declared._prefetch_related_lookups)
        return qs

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        user = request.user
        self._tenant_token = None
        self._group_token = None
        self._audit_tokens = None

        if user and user.is_authenticated:
            from apps.audit.context import set_audit_context

            forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
            ip = (
                forwarded.split(",")[0].strip()
                if forwarded
                else request.META.get("REMOTE_ADDR")
            )
            self._audit_tokens = set_audit_context(user, ip)

            if getattr(user, "is_group_level", False):
                self._group_token = set_group_context(True)
                requested = request.META.get(TENANT_HEADER)
                self._tenant_token = set_current_tenant(requested or None)
            else:
                self._group_token = set_group_context(False)
                self._tenant_token = set_current_tenant(
                    getattr(user, "tenant_id", None)
                )

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if getattr(self, "_tenant_token", None) is not None:
            reset_current_tenant(self._tenant_token)
        if getattr(self, "_group_token", None) is not None:
            _is_group_context.reset(self._group_token)
        if getattr(self, "_audit_tokens", None) is not None:
            from apps.audit.context import reset_audit_context

            reset_audit_context(self._audit_tokens)
        return response


class AgencyScopedMixin:
    """Filtre et affecte l'agence selon le périmètre de l'utilisateur."""

    agency_field = "agency"
    owner_field = "created_by"

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user and user.is_authenticated:
            qs = apply_data_scope(
                qs, user, self.agency_field, self.owner_field
            )
        return qs

    def _resolve_default_agency(self, user):
        return getattr(user, "agency", None)

    def _validate_agency_write(self, agency, user):
        if agency is None:
            return
        if not user_has_agency_access(user, agency.id):
            raise PermissionDenied(
                "Vous n'avez pas accès à cette agence."
            )

    def perform_create(self, serializer):
        if get_current_tenant_id() is None:
            raise ValidationError({
                "detail": "Aucune filiale sélectionnée. Choisissez une filiale "
                          "dans la barre supérieure avant de créer un enregistrement."
            })
        user = self.request.user
        extra = {}
        fields = self._model_fields(serializer)
        agency = serializer.validated_data.get(self.agency_field)
        if agency is None and self.agency_field in fields:
            default_agency = self._resolve_default_agency(user)
            if default_agency:
                extra[self.agency_field] = default_agency
                agency = default_agency
        if agency and not getattr(user, "is_group_level", False):
            self._validate_agency_write(agency, user)
        if "created_by" in fields:
            extra["created_by"] = user
        if "updated_by" in fields:
            extra["updated_by"] = user
        serializer.save(**extra)

    def perform_update(self, serializer):
        user = self.request.user
        agency = serializer.validated_data.get(self.agency_field)
        if agency and not getattr(user, "is_group_level", False):
            self._validate_agency_write(agency, user)
        extra = {}
        fields = self._model_fields(serializer)
        if "updated_by" in fields:
            extra["updated_by"] = user
        serializer.save(**extra)


class AuthorPersistMixin:
    """Renseigne automatiquement created_by / updated_by si présents."""

    def _model_fields(self, serializer):
        model = serializer.Meta.model
        return {f.name for f in model._meta.get_fields()}

    def perform_create(self, serializer):
        extra = {}
        fields = self._model_fields(serializer)
        if "created_by" in fields:
            extra["created_by"] = self.request.user
        if "updated_by" in fields:
            extra["updated_by"] = self.request.user
        serializer.save(**extra)

    def perform_update(self, serializer):
        extra = {}
        fields = self._model_fields(serializer)
        if "updated_by" in fields:
            extra["updated_by"] = self.request.user
        serializer.save(**extra)


class TenantMandatoryMixin:
    """Exige une filiale active : données strictement isolées par tenant.

    En contexte Groupe sans ``X-Tenant-Id``, les listes sont vides et les
    créations sont refusées (utile pour produits, circuits, rôles, etc.).
    """

    def get_queryset(self):
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            model = self.queryset.model if self.queryset is not None else None
            if model is not None:
                return model._default_manager.none()
            return super().get_queryset().none()
        qs = super().get_queryset()
        if is_group_context():
            return qs.filter(tenant_id=tenant_id)
        return qs


class TenantScopedViewSet(TenantMandatoryMixin, TenantContextMixin,
                          AuthorPersistMixin, viewsets.ModelViewSet):
    """ViewSet CRUD complet avec isolation multi-tenants, audit et RBAC.

    Inclut ``TenantMandatoryMixin`` : un utilisateur Groupe sans
    ``X-Tenant-Id`` obtient des listes vides (pas de fuite cross-filiale).
    """

    permission_classes = [
        IsAuthenticated,
        MustChangePasswordGate,
        HasModelPermission,
    ]
    enforce_model_permissions = True

    def perform_create(self, serializer):
        # Un objet scopé exige une filiale en contexte. Pour un utilisateur
        # Groupe qui n'a pas sélectionné de filiale, on renvoie une erreur
        # explicite (400) au lieu de laisser échouer l'insertion (500).
        if get_current_tenant_id() is None:
            raise ValidationError({
                "detail": "Aucune filiale sélectionnée. Choisissez une filiale "
                          "dans la barre supérieure avant de créer un enregistrement."
            })
        super().perform_create(serializer)


class AgencyScopedViewSet(AgencyScopedMixin, TenantScopedViewSet):
    """ViewSet CRUD avec isolation filiale + agence + périmètre utilisateur."""


class TenantScopedReadOnlyViewSet(TenantMandatoryMixin, TenantContextMixin,
                                  viewsets.ReadOnlyModelViewSet):
    """ViewSet en lecture seule avec isolation multi-tenants, audit et RBAC."""

    permission_classes = [
        IsAuthenticated,
        MustChangePasswordGate,
        HasModelPermission,
    ]
    enforce_model_permissions = True
