"""Tests engagements de caution — type, plafond, libération, appel."""
from decimal import Decimal

import pytest
from rest_framework.exceptions import ValidationError

from apps.common.tenancy import tenant_context
from apps.credits.models import CreditApplication
from apps.sureties.models import Surety, SuretyEngagement
from apps.sureties.services import call_engagement, release_engagement

pytestmark = pytest.mark.django_db


def _app(tenant, client_obj, product, *, ref="CR-SURETY-1"):
    return CreditApplication.objects.create(
        tenant=tenant,
        client=client_obj,
        product=product,
        reference=ref,
        amount_requested=Decimal("500000"),
        duration_months=12,
        risk_level=1,
    )


def test_available_ceiling_excludes_released(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        surety = Surety.objects.create(
            tenant=tenant_a,
            surety_type=Surety.SuretyType.PHYSICAL,
            first_name="Awa",
            last_name="Diallo",
            commitment_ceiling=Decimal("10000000"),
        )
        app = _app(tenant_a, client_a, product_a)
        eng = SuretyEngagement.objects.create(
            tenant=tenant_a,
            surety=surety,
            application=app,
            amount=Decimal("4000000"),
            engagement_type=SuretyEngagement.EngagementType.SOLIDAIRE,
        )
        assert surety.available_ceiling == Decimal("6000000")
        release_engagement(eng, comment="Soldé")
        assert Surety.objects.get(pk=surety.pk).available_ceiling == Decimal(
            "10000000"
        )
        assert eng.status == SuretyEngagement.Status.RELEASED


def test_call_keeps_committed_exposure(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        surety = Surety.objects.create(
            tenant=tenant_a,
            surety_type=Surety.SuretyType.PHYSICAL,
            first_name="Ibra",
            last_name="Ndiaye",
            commitment_ceiling=Decimal("5000000"),
        )
        app = _app(tenant_a, client_a, product_a, ref="CR-SURETY-2")
        eng = SuretyEngagement.objects.create(
            tenant=tenant_a,
            surety=surety,
            application=app,
            amount=Decimal("2000000"),
            engagement_type=SuretyEngagement.EngagementType.SIMPLE,
        )
        call_engagement(eng, comment="Impayé")
        assert eng.status == SuretyEngagement.Status.CALLED
        assert Surety.objects.get(pk=surety.pk).available_ceiling == Decimal(
            "3000000"
        )
        with pytest.raises(ValidationError):
            call_engagement(eng)
