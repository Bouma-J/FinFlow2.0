"""Tests des garde-fous critiques (montants, isolation ViewSet)."""
from decimal import Decimal

import pytest

from apps.catalog.models import CreditProduct
from apps.common.tenancy import reset_current_tenant, set_current_tenant, set_group_context, tenant_context
from apps.common.viewsets import TenantScopedViewSet
from apps.credits.amounts import reference_amount
from apps.credits.models import CreditApplication

pytestmark = pytest.mark.django_db


def test_reference_amount_uses_approved_during_disbursement_pending(
    tenant_a, product_a, client_a,
):
    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="AMT1",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("100000"),
            amount_proposed=Decimal("90000"),
            amount_approved=Decimal("80000"),
            duration_months=12,
            status=CreditApplication.Status.DISBURSEMENT_PENDING,
        )
        assert reference_amount(app) == Decimal("80000")


def test_tenant_scoped_viewset_empty_for_group_without_header(tenant_a, product_a):
    """Groupe sans X-Tenant-Id : listes vides (pas de fuite cross-filiale)."""
    with tenant_context(tenant_a.id):
        assert CreditProduct.objects.count() == 1

    class _Probe(TenantScopedViewSet):
        queryset = CreditProduct.objects.all()

    view = _Probe()
    view.queryset = CreditProduct.objects.all()

    gtoken = set_group_context(True)
    ttoken = set_current_tenant(None)
    try:
        assert list(view.get_queryset()) == []
    finally:
        reset_current_tenant(ttoken)
        from apps.common import tenancy as t

        t._is_group_context.reset(gtoken)

    gtoken = set_group_context(True)
    ttoken = set_current_tenant(str(tenant_a.id))
    try:
        assert view.get_queryset().count() == 1
    finally:
        reset_current_tenant(ttoken)
        from apps.common import tenancy as t

        t._is_group_context.reset(gtoken)
