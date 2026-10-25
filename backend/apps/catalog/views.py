from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.common.tenancy import get_current_tenant_id
from apps.common.viewsets import TenantScopedReadOnlyViewSet, TenantScopedViewSet

from .models import (
    CbsProductReference,
    CbsManager,
    CbsProfession,
    ChecklistItem,
    CreditProduct,
    Currency,
    DecisionMotif,
    FinancingObject,
    FinancingSource,
    LoanPeriodicity,
    ProductCategory,
    RejectReason,
    RepaymentMethod,
    ServicePoint,
)
from .serializers import (
    CbsProductReferenceSerializer,
    CbsManagerSerializer,
    CbsProfessionSerializer,
    ChecklistItemSerializer,
    CreditProductSerializer,
    CurrencySerializer,
    DecisionMotifSerializer,
    FinancingObjectSerializer,
    FinancingSourceSerializer,
    LoanPeriodicitySerializer,
    ProductCategorySerializer,
    RejectReasonSerializer,
    RepaymentMethodSerializer,
    ServicePointSerializer,
)


class ProductCategoryViewSet(TenantScopedViewSet):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer
    filterset_fields = ["is_active"]
    search_fields = ["code", "label"]


class CreditProductViewSet(TenantScopedViewSet):
    queryset = CreditProduct.objects.select_related("category").all()
    serializer_class = CreditProductSerializer
    filterset_fields = ["category", "client_type", "currency", "is_active"]
    search_fields = ["code", "label"]

class CbsProductReferenceViewSet(TenantScopedViewSet):
    queryset = CbsProductReference.objects.select_related("connector").all()
    serializer_class = CbsProductReferenceSerializer
    filterset_fields = ["kind", "is_active", "verification_status", "connector"]
    search_fields = ["cbs_code", "label", "source_reference"]
    http_method_names = ["get", "post", "patch", "head", "options"]
    action_perms = {
        "list": ["catalog.view_creditproduct"], "retrieve": ["catalog.view_creditproduct"],
        "create": ["catalog.change_creditproduct"], "partial_update": ["catalog.change_creditproduct"],
        "confirm": ["catalog.change_creditproduct"],
    }

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("for_active_connector") == "true":
            from apps.corebanking.services import CoreBankingError, resolve_active_connector
            try:
                connector = resolve_active_connector(get_current_tenant_id())
            except CoreBankingError:
                return qs.none()
            return qs.filter(connector=connector)
        return qs

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def confirm(self, request, pk=None):
        from .cbs_resolve import is_demo_product_code

        if request.data.get("document_checked") is not True:
            raise ValidationError({"document_checked": "Confirmez avoir vérifié cet identifiant dans la source documentaire indiquée."})
        ref = self.get_queryset().select_related(None).select_for_update().get(pk=self.get_object().pk)
        if not ref.is_active or not ref.connector.is_active or not ref.source_reference.strip():
            raise ValidationError("La référence, le connecteur et le justificatif doivent être actifs et renseignés.")
        if is_demo_product_code(ref.cbs_code):
            raise ValidationError({"cbs_code": "Cet identifiant est une valeur de démonstration connue. Renseignez l'identifiant réel du CBS."})
        if ref.verification_status != "VERIFIED":
            ref.verification_status = "VERIFIED"
            ref.verified_at = timezone.now()
            ref.verified_by = request.user
            ref.save(update_fields=["verification_status", "verified_at", "verified_by", "updated_at"])
        return Response(self.get_serializer(ref).data)


class RejectReasonViewSet(TenantScopedViewSet):
    queryset = RejectReason.objects.all()
    serializer_class = RejectReasonSerializer
    filterset_fields = ["is_active"]
    search_fields = ["code", "label"]


class LoanPeriodicityViewSet(TenantScopedReadOnlyViewSet):
    """Périodicités : source CBS uniquement (sync Perfect)."""

    queryset = LoanPeriodicity.objects.all()
    serializer_class = LoanPeriodicitySerializer
    filterset_fields = ["is_active"]
    search_fields = ["code", "label", "cbs_code"]
    ordering = ["sort_order", "label"]


class RepaymentMethodViewSet(TenantScopedViewSet):
    queryset = RepaymentMethod.objects.all()
    serializer_class = RepaymentMethodSerializer
    filterset_fields = ["is_active"]
    search_fields = ["code", "label", "cbs_code"]
    ordering = ["sort_order", "label"]


class CurrencyViewSet(TenantScopedReadOnlyViewSet):
    """Devises : source CBS uniquement (sync Perfect)."""

    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer
    filterset_fields = ["is_active"]
    search_fields = ["code", "label", "cbs_code"]
    ordering = ["sort_order", "label"]


class FinancingObjectViewSet(TenantScopedReadOnlyViewSet):
    """Objets de financement : source CBS uniquement (sync Perfect)."""

    queryset = FinancingObject.objects.all()
    serializer_class = FinancingObjectSerializer
    filterset_fields = ["is_active", "purpose_type"]
    search_fields = ["code", "label", "cbs_code", "purpose_type"]
    ordering = ["sort_order", "label"]


class ServicePointViewSet(TenantScopedReadOnlyViewSet):
    """Points de service Perfect : source CBS uniquement."""

    queryset = ServicePoint.objects.all()
    serializer_class = ServicePointSerializer
    filterset_fields = ["is_active"]
    search_fields = ["code", "label", "cbs_code"]
    ordering = ["sort_order", "label"]


class CbsManagerViewSet(TenantScopedReadOnlyViewSet):
    """Gestionnaires Perfect : source CBS uniquement."""

    queryset = CbsManager.objects.all()
    serializer_class = CbsManagerSerializer
    filterset_fields = ["is_active"]
    search_fields = ["code", "label", "cbs_code"]
    ordering = ["sort_order", "label"]


class FinancingSourceViewSet(TenantScopedReadOnlyViewSet):
    """Sources de financement Perfect : source CBS uniquement."""

    queryset = FinancingSource.objects.all()
    serializer_class = FinancingSourceSerializer
    filterset_fields = ["is_active"]
    search_fields = ["code", "label", "cbs_code"]
    ordering = ["sort_order", "label"]


class DecisionMotifViewSet(TenantScopedReadOnlyViewSet):
    """Motifs de décision Perfect : source CBS uniquement."""

    queryset = DecisionMotif.objects.all()
    serializer_class = DecisionMotifSerializer
    filterset_fields = ["is_active"]
    search_fields = ["code", "label", "cbs_code"]
    ordering = ["sort_order", "label"]


class CbsProfessionViewSet(TenantScopedReadOnlyViewSet):
    """Professions Perfect : source CBS uniquement."""

    queryset = CbsProfession.objects.all()
    serializer_class = CbsProfessionSerializer
    filterset_fields = ["is_active"]
    search_fields = ["code", "label", "cbs_code"]
    ordering = ["sort_order", "label"]


class ChecklistItemViewSet(TenantScopedViewSet):
    queryset = ChecklistItem.objects.select_related("product").all()
    serializer_class = ChecklistItemSerializer
    filterset_fields = ["product", "is_mandatory"]
