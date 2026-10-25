from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.cache_utils import cache_key, cached_get
from apps.common.permissions import (
    HasDashboardPermission,
    IsGroupLevel,
    MustChangePasswordGate,
)

from .services import build_after_sales_hub, build_dashboard, build_group_breakdown
from .snapshots import get_fresh_snapshot


def _params_fingerprint(params) -> str:
    items = sorted((k, ",".join(params.getlist(k))) for k in params.keys())
    return "&".join(f"{k}={v}" for k, v in items)


def _want_live(request) -> bool:
    return str(request.query_params.get("live", "")).lower() in ("1", "true", "yes")


def _has_material_filters(params) -> bool:
    """Filtres hors tenant / dimension → forcer le calcul live."""
    skip = {"tenant", "dimension", "live", "page", "page_size"}
    return any(k not in skip and params.get(k) for k in params.keys())


@extend_schema(responses=OpenApiTypes.OBJECT)
class OperationalDashboardView(APIView):
    """Tableau de bord opérationnel d'une filiale."""

    permission_classes = [
        IsAuthenticated,
        MustChangePasswordGate,
        HasDashboardPermission,
    ]

    def get(self, request):
        user = request.user
        if user.is_group_level:
            tenant_id = request.query_params.get("tenant")
        else:
            tenant_id = user.tenant_id

        # Snapshot filiale = vue TENANT complète ; hors scope TENANT / Groupe
        # on calcule en live pour respecter data_scope.
        scope_ok = (
            getattr(user, "is_group_level", False)
            or getattr(user, "data_scope", None) == "TENANT"
            or getattr(user, "is_superuser", False)
        )
        if (
            not _want_live(request)
            and not _has_material_filters(request.query_params)
            and tenant_id
            and scope_ok
        ):
            snap = get_fresh_snapshot(
                scope="TENANT",
                tenant_id=tenant_id,
                kind="dashboard",
                params={},
            )
            if snap is not None:
                return Response(snap)

        key = cache_key(
            "dashboard",
            tenant_id,
            getattr(user, "id", None),
            getattr(user, "data_scope", None),
            _params_fingerprint(request.query_params),
        )
        ttl = getattr(settings, "DASHBOARD_CACHE_TTL", 45)

        def _produce():
            return build_dashboard(
                tenant_id=tenant_id,
                params=request.query_params,
                user=user,
            )

        return Response(cached_get(key, _produce, timeout=ttl))


@extend_schema(responses=OpenApiTypes.OBJECT)
class GroupConsolidationView(APIView):
    """
    Consolidation Groupe multi-axes avec filtres combinables.

    Sans filtre (et hors ?live=1), sert le snapshot matérialisé si frais.
    """

    permission_classes = [
        IsAuthenticated,
        MustChangePasswordGate,
        IsGroupLevel,
        HasDashboardPermission,
    ]

    def get(self, request):
        if not _want_live(request) and not _has_material_filters(request.query_params):
            snap = get_fresh_snapshot(
                scope="GROUP",
                tenant_id=None,
                kind="dashboard",
                params={},
            )
            if snap is not None:
                return Response(snap)

        key = cache_key(
            "dashboard",
            "group",
            getattr(request.user, "id", None),
            _params_fingerprint(request.query_params),
        )
        ttl = getattr(settings, "DASHBOARD_CACHE_TTL", 45)

        def _produce():
            return build_dashboard(
                tenant_id=None,
                params=request.query_params,
                user=request.user,
            )

        return Response(cached_get(key, _produce, timeout=ttl))


@extend_schema(responses=OpenApiTypes.OBJECT)
class GroupBreakdownView(APIView):
    """Décomposition consolidée selon un axe (drill-down), ex. ?dimension=country."""

    permission_classes = [
        IsAuthenticated,
        MustChangePasswordGate,
        IsGroupLevel,
        HasDashboardPermission,
    ]

    def get(self, request):
        dimension = request.query_params.get("dimension", "tenant")
        if not _want_live(request) and not _has_material_filters(request.query_params):
            snap = get_fresh_snapshot(
                scope="GROUP",
                tenant_id=None,
                kind=f"breakdown:{dimension}",
                params={},
            )
            if snap is not None:
                return Response(snap)

        key = cache_key(
            "breakdown",
            dimension,
            _params_fingerprint(request.query_params),
        )
        ttl = getattr(settings, "DASHBOARD_CACHE_TTL", 45)

        def _produce():
            return {
                "dimension": dimension,
                "rows": build_group_breakdown(
                    request.query_params, dimension=dimension
                ),
            }

        return Response(cached_get(key, _produce, timeout=ttl))

@extend_schema(responses=OpenApiTypes.OBJECT)
class AfterSalesHubView(APIView):
    """Hub après-vente : volumes ouverts + files récentes (ML / dation / form. / recouvrement)."""

    permission_classes = [IsAuthenticated, MustChangePasswordGate]

    def get(self, request):
        from apps.common.tenancy import get_current_tenant_id
        from .services import _after_sales_module_access

        user = request.user
        access = _after_sales_module_access(user=user)
        if not any(access.values()):
            return Response({"detail": "Droit insuffisant."}, status=403)

        tenant_id = get_current_tenant_id()
        if not tenant_id and getattr(user, "is_group_level", False):
            tenant_id = request.query_params.get("tenant")
        if not tenant_id:
            tenant_id = getattr(user, "tenant_id", None)
        if not tenant_id:
            return Response(
                {"detail": "Sélectionnez une filiale pour le hub après-vente."},
                status=400,
            )
        return Response(
            build_after_sales_hub(tenant_id=tenant_id, user=user)
        )
