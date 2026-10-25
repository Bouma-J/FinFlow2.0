"""Les références CBS du catalogue sont utilisées dans le process dossier."""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.catalog.cbs_resolve import application_cbs_refs
from apps.catalog.defaults import ensure_catalog_defaults
from apps.catalog.models import LoanPeriodicity, RepaymentMethod
from apps.clients.models import Client
from apps.common.tenancy import tenant_context
from apps.credits.instruction_policy import build_readiness
from apps.credits.models import CreditApplication
from apps.credits.serializers import CreditApplicationSerializer
from apps.credits.services import compute_amortization_schedule, period_count
from apps.tenants.models import Agency

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup(tenant_a, product_a, client_a):
    ensure_catalog_defaults(tenant_a)
    from apps.corebanking.models import CoreBankingConnector
    with tenant_context(tenant_a.id):
        CoreBankingConnector.objects.create(tenant=tenant_a, name="CBS local", protocol="REST",
            mapping_rules={"force_simulate": True, "disbursement": {"mode": "LOCAL"}}, is_active=True)
        agency = Agency.objects.create(
            tenant=tenant_a,
            code="AG-REF",
            name="Agence Refs",
            cbs_point_of_service_id="PS-REF",
        )
        LoanPeriodicity.objects.filter(code="MONTHLY").update(
            cbs_code="MENSUEL-REF", periods_per_year=12
        )
        RepaymentMethod.objects.filter(code="DEGRESSIVE").update(
            cbs_code="REMB-REF"
        )
        product_a.cbs_product_code = "CRED-REF"
        product_a.cbs_repayment_product_code = ""
        product_a.save(
            update_fields=["cbs_product_code", "cbs_repayment_product_code"]
        )
        client_a.cbs_client_id = "A-REF-1"
        client_a.save(update_fields=["cbs_client_id"])
        user = User.objects.create_user(
            username="ref_officer",
            password="FinFlow2026!",
            tenant=tenant_a,
            agency=agency,
            cbs_id="GEST-REF",
            is_superuser=True,
            is_staff=True,
            is_group_level=True,
            data_scope="TENANT",
        )
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="REF-CBS-001",
            client=client_a,
            product=product_a,
            agency=agency,
            amount_requested=Decimal("500000"),
            duration_months=12,
            periodicity="MONTHLY",
            repayment_mechanism="DEGRESSIVE",
            currency="XOF",
            interest_rate=Decimal("10"),
            created_by=user,
            submitted_by=user,
        )
    return {
        "tenant": tenant_a,
        "app": app,
        "user": user,
        "agency": agency,
        "product": product_a,
        "client": client_a,
    }


def test_application_cbs_refs_snapshot(setup):
    refs = application_cbs_refs(setup["app"])
    assert refs["periodicity"]["cbs_code"] == "MENSUEL-REF"
    assert refs["repayment_method"]["cbs_code"] == "REMB-REF"
    assert refs["product_cbs_code"] == "CRED-REF"
    assert refs["product_repayment_cbs_code"] == "REMB-REF"
    assert refs["manager_cbs_id"] == "GEST-REF"
    assert refs["client_adherent_id"] == "A-REF-1"
    assert refs["point_of_service_id"] == "PS-REF"
    assert refs["ready_for_cbs"] is True


def test_serializer_exposes_cbs_labels_and_refs(setup):
    with tenant_context(setup["tenant"].id):
        data = CreditApplicationSerializer(setup["app"]).data
    assert data["periodicity_label"]
    assert data["repayment_mechanism_label"]
    assert data["currency_label"]
    assert data["cbs_refs"]["periodicity"]["cbs_code"] == "MENSUEL-REF"
    assert data["cbs_refs"]["product_cbs_code"] == "CRED-REF"


def test_readiness_includes_cbs_mapping_check(setup):
    with tenant_context(setup["tenant"].id):
        readiness = build_readiness(setup["app"])
    keys = {c["key"] for c in readiness["checks"]}
    assert "cbs_mapping" in keys
    cbs_check = next(c for c in readiness["checks"] if c["key"] == "cbs_mapping")
    assert cbs_check["ok"] is True
    assert readiness["cbs_refs"]["ready_for_cbs"] is True


def test_schedule_and_period_count_use_catalog(setup, tenant_a):
    with tenant_context(tenant_a.id):
        LoanPeriodicity.objects.filter(code="QUARTERLY").update(
            periods_per_year=4, cbs_code="TRIM-REF"
        )
    assert period_count(12, "QUARTERLY", tenant_id=tenant_a.id) == 4
    schedule = compute_amortization_schedule(
        Decimal("1200000"),
        Decimal("12"),
        12,
        periodicity="QUARTERLY",
        tenant_id=tenant_a.id,
    )
    assert len(schedule) == 4


def test_api_detail_returns_cbs_refs(setup):
    api = APIClient()
    api.force_authenticate(setup["user"])
    api.credentials(HTTP_X_TENANT_ID=str(setup["tenant"].id))
    res = api.get(f"/api/v1/credit-applications/{setup['app'].pk}/")
    assert res.status_code == 200, res.content
    body = res.json()
    assert body["cbs_refs"]["periodicity"]["cbs_code"] == "MENSUEL-REF"
    assert body["periodicity_label"]
    assert "MENSUEL" in (
        body["cbs_refs"]["periodicity"]["cbs_code"] or ""
    ) or body["cbs_refs"]["periodicity"]["cbs_code"] == "MENSUEL-REF"
