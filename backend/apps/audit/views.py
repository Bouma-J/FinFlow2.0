from apps.common.tenancy import get_current_tenant_id, is_group_context
from apps.common.viewsets import TenantScopedReadOnlyViewSet

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogViewSet(TenantScopedReadOnlyViewSet):
    """Consultation en lecture seule de la piste d'audit."""

    serializer_class = AuditLogSerializer
    filterset_fields = ["action", "model_label", "object_id", "user", "tenant"]
    search_fields = ["object_repr", "object_id", "model_label"]
    ordering_fields = ["timestamp"]

    def get_queryset(self):
        qs = AuditLog.objects.select_related("user", "tenant")
        if not is_group_context():
            tenant_id = get_current_tenant_id()
            qs = qs.filter(tenant_id=tenant_id) if tenant_id else qs.none()
        return qs
