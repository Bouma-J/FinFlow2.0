"""Synthèse collatéral : haircuts et piliers séparés."""
from decimal import Decimal

import pytest

from apps.common.tenancy import tenant_context
from apps.credits.collateral import build_collateral_summary, retained_value
from apps.credits.models import AnalysisThreshold, CreditApplication
from apps.guarantees.models import Guarantee, PledgeCategory
from apps.sureties.models import Surety, SuretyEngagement

pytestmark = pytest.mark.django_db


def test_retained_value_applies_vehicle_haircut(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        th = AnalysisThreshold.for_tenant(tenant_a.id)
        th.haircut_vehicle = Decimal("30")
        th.save(update_fields=["haircut_vehicle"])

        application = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="D-COL",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("1000000"),
            duration_months=12,
        )
        g = Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            application=application,
            guarantee_type=Guarantee.GuaranteeType.PLEDGE,
            pledge_category=PledgeCategory.VEHICLE,
            description="Véhicule",
            current_value=Decimal("1000000"),
            status=Guarantee.Status.ACTIVE,
            reference="GAR-VEH",
        )
        assert retained_value(g, th) == Decimal("700000.00")

        summary = build_collateral_summary(application, th)
        assert summary["guarantees_retained_total"] == "700000.00"
        assert summary["guarantee_coverage_pct"] == "70.00"
        assert summary["sureties_total"] == "0"


def test_sureties_are_separate_pillar(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        th = AnalysisThreshold.for_tenant(tenant_a.id)
        th.haircut_mortgage = Decimal("0")
        th.save(update_fields=["haircut_mortgage"])

        application = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="D-SURE",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("500000"),
            duration_months=12,
        )
        Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            application=application,
            guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
            description="Terrain",
            current_value=Decimal("400000"),
            status=Guarantee.Status.ACTIVE,
            reference="GAR-M",
        )
        surety = Surety.objects.create(
            tenant=tenant_a,
            surety_type=Surety.SuretyType.PHYSICAL,
            first_name="Jean",
            last_name="Caution",
        )
        SuretyEngagement.objects.create(
            tenant=tenant_a,
            surety=surety,
            application=application,
            amount=Decimal("200000"),
            status=SuretyEngagement.Status.ACTIVE,
        )

        summary = build_collateral_summary(application, th)
        assert summary["guarantees_retained_total"] == "400000.00"
        assert summary["sureties_total"] == "200000.00"
        # Couverture garanties ne fusionne pas les cautions.
        assert summary["guarantee_coverage_pct"] == "80.00"
        assert summary["surety_coverage_pct"] == "40.00"


def test_inactive_guarantees_excluded(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        th = AnalysisThreshold.for_tenant(tenant_a.id)
        application = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="D-INACT",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("500000"),
            duration_months=12,
        )
        Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            application=application,
            guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
            description="Inactif",
            current_value=Decimal("900000"),
            status=Guarantee.Status.RELEASED,
            reference="GAR-D",
        )
        summary = build_collateral_summary(application, th)
        assert summary["guarantees_retained_total"] == "0"
        assert summary["guarantees"] == []
