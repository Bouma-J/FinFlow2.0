from django.http import FileResponse, Http404
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.common.permissions import (
    HasModelPermission,
    IsGroupLevel,
    IsGroupAdministrator,
    IsConfigurationAdministrator,
    MustChangePasswordGate,
)
from apps.common.tenancy import get_current_tenant_id, is_group_context
from apps.common.viewsets import TenantContextMixin

from .models import Agency, Tenant
from .serializers import (
    AgencySerializer,
    PublicTenantBrandingSerializer,
    TenantSerializer,
)
from .services import bootstrap_tenant, tenant_business_data


class TenantViewSet(TenantContextMixin, viewsets.ModelViewSet):
    """Gestion des filiales — création réservée au niveau Groupe."""

    queryset = Tenant.objects.prefetch_related("officers").all()
    serializer_class = TenantSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filterset_fields = ["country", "zone", "is_active", "currency"]
    search_fields = ["code", "name", "country"]
    ordering_fields = ["code", "name", "created_at"]

    def get_permissions(self):
        if self.action in ("logo", "branding"):
            # Logo / charte pour l'écran de connexion (sans JWT).
            return [AllowAny()]
        if self.action in ("retrieve", "current"):
            return [IsAuthenticated(), MustChangePasswordGate()]
        if self.action in ("update", "partial_update"):
            return [IsAuthenticated(), MustChangePasswordGate(), IsConfigurationAdministrator()]
        if self.action == "list":
            return [IsAuthenticated(), MustChangePasswordGate(), IsGroupLevel()]
        return [IsAuthenticated(), MustChangePasswordGate(), IsGroupAdministrator()]

    def perform_update(self, serializer):
        user = self.request.user
        if user.is_superuser or (user.is_group_level and user.is_staff):
            serializer.save()
            return
        if user.is_group_level:
            raise PermissionDenied("Accès réservé aux administrateurs Groupe.")
        if str(serializer.instance.id) != str(user.tenant_id):
            raise PermissionDenied(
                "Vous ne pouvez modifier que votre propre filiale."
            )
        if not user.has_perm("tenants.change_tenant"):
            raise PermissionDenied(
                "Droit « tenants.change_tenant » requis pour modifier la filiale."
            )
        serializer.save()

    def perform_create(self, serializer):
        tenant = serializer.save()
        bootstrap_tenant(tenant)

    def perform_destroy(self, instance):
        """Supprime une filiale, sauf si elle porte déjà des données métier.

        La suppression cascade sur les dossiers de crédit, la GED et la piste
        d'audit : irréversible et incompatible avec les obligations de
        conservation. La désactivation (`is_active=False`) coupe l'accès tout
        en préservant l'historique. Une filiale créée par erreur (vide) reste
        supprimable.
        """
        existing = tenant_business_data(instance)
        if existing:
            detail = ", ".join(f"{wording} : {count}" for wording, count in existing)
            raise ValidationError(
                f"La filiale « {instance.code} » porte des données métier "
                f"({detail}) et ne peut pas être supprimée. Désactivez-la pour "
                "en couper l'accès tout en conservant l'historique et la piste "
                "d'audit."
            )
        instance.delete()

    def get_queryset(self):
        user = self.request.user
        if self.action in ("retrieve", "current", "logo"):
            if getattr(user, "is_authenticated", False) and (
                getattr(user, "is_group_level", False) or user.is_superuser
            ):
                return Tenant.objects.all()
            if getattr(user, "is_authenticated", False) and user.tenant_id:
                return Tenant.objects.filter(pk=user.tenant_id)
            tenant_id = get_current_tenant_id()
            if tenant_id:
                return Tenant.objects.filter(pk=tenant_id)
            if self.action == "logo":
                return Tenant.objects.all()
            return Tenant.objects.none()
        return Tenant.objects.all()

    @action(detail=True, methods=["get"], url_path="logo")
    def logo(self, request, pk=None):
        """Sert le logo de la filiale (affichage sidebar / branding)."""
        tenant = Tenant.objects.filter(pk=pk).first()
        if tenant is None or not tenant.logo:
            raise Http404("Logo introuvable.")
        try:
            handle = tenant.logo.open("rb")
        except Exception as exc:  # noqa: BLE001
            raise Http404("Fichier logo inaccessible.") from exc

        from apps.common.storage_urls import image_content_type

        response = FileResponse(
            handle, content_type=image_content_type(tenant.logo.name)
        )
        response["Cache-Control"] = "public, max-age=3600"
        return response

    @action(detail=False, methods=["get"], url_path="branding")
    def branding(self, request):
        """
        Charte publique d'une filiale (écran de connexion).

        Query : ``?code=FIL01`` — uniquement les filiales actives.
        """
        code = (request.query_params.get("code") or "").strip()
        if not code:
            raise ValidationError(
                {"code": "Indiquez le code filiale (?code=…)."}
            )
        tenant = Tenant.objects.filter(code__iexact=code, is_active=True).first()
        if tenant is None:
            raise Http404("Filiale introuvable ou inactive.")
        return Response(
            PublicTenantBrandingSerializer(
                tenant, context={"request": request}
            ).data
        )

    @action(detail=True, methods=["post"], url_path="bootstrap")
    def bootstrap_defaults(self, request, pk=None):
        """Crée les rôles par défaut pour une filiale existante."""
        tenant = self.get_object()
        bootstrap_tenant(tenant)
        return Response({
            "detail": "Rôles par défaut créés pour la filiale.",
        })

    @action(detail=False, methods=["get"])
    def current(self, request):
        """Filiale active (utilisateur filiale ou filiale sélectionnée)."""
        user = request.user
        tenant_id = user.tenant_id or get_current_tenant_id()
        if not tenant_id:
            raise ValidationError(
                "Aucune filiale active. Sélectionnez une filiale."
            )
        tenant = Tenant.objects.filter(pk=tenant_id).first()
        if tenant is None:
            raise ValidationError("Filiale introuvable.")
        return Response(
            TenantSerializer(tenant, context={"request": request}).data
        )


class AgencyViewSet(TenantContextMixin, viewsets.ModelViewSet):
    """Gestion des agences, filtrées selon le périmètre de l'utilisateur."""

    queryset = Agency.objects.select_related("tenant").all()
    serializer_class = AgencySerializer
    permission_classes = [
        IsAuthenticated,
        MustChangePasswordGate,
        HasModelPermission,
    ]
    enforce_model_permissions = True
    filterset_fields = ["tenant", "region", "is_active"]
    search_fields = ["code", "name", "region"]

    def get_queryset(self):
        qs = Agency.objects.select_related("tenant").all()
        tenant_id = get_current_tenant_id()
        if tenant_id:
            return qs.filter(tenant_id=tenant_id)
        # Filiale sans tenant, ou Groupe sans X-Tenant-Id : aucune fuite.
        if is_group_context():
            return qs.none()
        return qs.none()

    def perform_create(self, serializer):
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            raise ValidationError({
                "detail": "Aucune filiale sélectionnée. Choisissez une filiale "
                          "avant de créer une agence."
            })
        serializer.save(tenant_id=tenant_id)
