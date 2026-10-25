"""Référentiels CBS catalogue (périodicités, remboursements, devises)."""
import pytest

from apps.catalog.cbs_resolve import (
    resolve_currency_cbs,
    resolve_periodicity_cbs,
    resolve_repayment_cbs,
)
from apps.catalog.defaults import ensure_catalog_defaults
from apps.catalog.models import Currency, LoanPeriodicity, RepaymentMethod
from apps.common.tenancy import tenant_context

pytestmark = pytest.mark.django_db


def test_ensure_catalog_defaults_idempotent(tenant_a):
    first = ensure_catalog_defaults(tenant_a)
    second = ensure_catalog_defaults(tenant_a)
    assert first["periodicities"] == 7
    assert first["repayment_methods"] == 3
    assert first["currencies"] >= 4
    assert second["periodicities"] == 0
    with tenant_context(tenant_a.id):
        assert LoanPeriodicity.objects.filter(code="MONTHLY").exists()
        assert RepaymentMethod.objects.filter(code="DEGRESSIVE").exists()
        assert Currency.objects.filter(code="XOF").exists()


def test_resolve_cbs_codes_from_catalog(tenant_a):
    ensure_catalog_defaults(tenant_a)
    with tenant_context(tenant_a.id):
        LoanPeriodicity.objects.filter(code="MONTHLY").update(cbs_code="MENSUEL-CUSTOM")
        LoanPeriodicity.objects.filter(code="BIMONTHLY").update(cbs_code="BIMENSUEL")
        RepaymentMethod.objects.filter(code="DEGRESSIVE").update(
            cbs_code="REMB-DEG"
        )
        Currency.objects.filter(code="XOF").update(cbs_code="XOF")

    assert (
        resolve_periodicity_cbs(tenant_a.id, "MONTHLY") == "MENSUEL-CUSTOM"
    )
    assert resolve_periodicity_cbs(tenant_a.id, "BIMONTHLY") == "BIMENSUEL"
    assert resolve_repayment_cbs(tenant_a.id, "DEGRESSIVE") == "REMB-DEG"
    assert resolve_currency_cbs(tenant_a.id, "XOF") == "XOF"


def test_bimonthly_period_count(tenant_a):
    ensure_catalog_defaults(tenant_a)
    from apps.credits.services import period_count

    assert period_count(12, "BIMONTHLY", tenant_id=tenant_a.id) == 24
    assert LoanPeriodicity.all_tenants.filter(
        tenant=tenant_a, code="BIMONTHLY", cbs_code="BIMENSUEL"
    ).exists()
