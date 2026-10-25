"""Alignement dation ↔ recouvrement : gel financier et historique."""
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()

from apps.collections.models import CollectionAction, CollectionActionType
from apps.collections.services import ensure_default_tranches, refresh_loan_overdue
from apps.common.tenancy import tenant_context
from apps.credits.models import CreditApplication, Installment, Loan
from apps.guarantees.models import DationRequest, Guarantee
from apps.guarantees.process_services import (
    complete_dation_request,
    initiate_dation_request,
)

pytestmark = pytest.mark.django_db

CBS_OK = {
    "total_outstanding": Decimal("100000"),
    "currency": "XAF",
    "breakdown": [],
    "raw": {},
    "log_id": "x",
}


@pytest.fixture
def agent(tenant_a):
    return User.objects.create_user(
        username="dation_col_agent",
        password="test-pass-123",
        email="dation-col@example.com",
        tenant=None,
        is_group_level=True,
        is_staff=True,
        is_superuser=True,
    )


def _api(user, tenant):
    client = APIClient()
    client.force_authenticate(user=user)
    client.credentials(HTTP_X_TENANT_ID=str(tenant.id))
    return client


def _case(tenant, product, client_obj, *, ref="DAT-COL-1"):
    app = CreditApplication.objects.create(
        tenant=tenant,
        client=client_obj,
        product=product,
        amount_requested=Decimal("20000"),
        duration_months=6,
        risk_level=1,
        reference=ref,
        status=CreditApplication.Status.APPROVED,
    )
    loan = Loan.objects.create(
        tenant=tenant,
        application=app,
        principal=Decimal("20000"),
        interest_rate=Decimal("12"),
        duration_months=6,
        disbursed_at=date.today() - timedelta(days=40),
        first_due_date=date.today() - timedelta(days=20),
        status=Loan.Status.ACTIVE,
    )
    Installment.objects.create(
        tenant=tenant,
        loan=loan,
        number=1,
        due_date=date.today() - timedelta(days=20),
        principal_due=Decimal("20000"),
        interest_due=Decimal("0"),
        total_due=Decimal("20000"),
        status=Installment.Status.OVERDUE,
    )
    return refresh_loan_overdue(
        loan,
        cbs_status={
            "settled": False,
            "days_overdue": 20,
            "overdue_amount": Decimal("20000"),
        },
    )


def _guarantee(tenant, client_obj, *, value="60000", ref="GAR-DC-1"):
    return Guarantee.objects.create(
        tenant=tenant,
        client=client_obj,
        guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
        description="Terrain dation",
        expertise_value=Decimal(value),
        current_value=Decimal(value),
        status=Guarantee.Status.ACTIVE,
        reference=ref,
    )


@patch(
    "apps.guarantees.process_services.assert_client_outstanding_for_dation",
    return_value=CBS_OK,
)
def test_open_dation_freezes_repayment_keeps_actions(
    _cbs, tenant_a, product_a, client_a, agent
):
    with tenant_context(tenant_a.id):
        ensure_default_tranches(tenant_a)
        client_a.cbs_client_id = "CBS-DC-1"
        client_a.save(update_fields=["cbs_client_id"])
        case = _case(tenant_a, product_a, client_a)
        g = _guarantee(tenant_a, client_a)
        req = initiate_dation_request(
            client=client_a,
            user=agent,
            cbs_client_id="CBS-DC-1",
            application=case.loan.application,
            guarantee_ids=[str(g.id)],
            as_draft=True,
        )
        assert req.status == DationRequest.Status.DRAFT

    api = _api(agent, tenant_a)
    detail = api.get(f"/api/v1/collection-cases/{case.id}/")
    assert detail.status_code == 200
    assert detail.data["can_operate"] is True
    assert detail.data["financial_ops_frozen"] is True
    assert detail.data["can_collect"] is False
    assert detail.data["blocking_dation"]["id"] == str(req.id)

    blocked = api.post(
        f"/api/v1/collection-cases/{case.id}/repayments/",
        {"amount": "1000", "payment_date": date.today().isoformat()},
        format="json",
    )
    assert blocked.status_code == 400

    action = api.post(
        "/api/v1/collection-actions/",
        {
            "case": str(case.id),
            "action_type": "CALL",
            "action_date": date.today().isoformat(),
            "result": "Relance hors dation",
        },
        format="json",
    )
    assert action.status_code == 201, action.content


@patch(
    "apps.guarantees.process_services.assert_client_outstanding_for_dation",
    return_value=CBS_OK,
)
def test_completed_residual_unfreezes_and_logs_action(
    _cbs, tenant_a, product_a, client_a, agent
):
    with tenant_context(tenant_a.id):
        ensure_default_tranches(tenant_a)
        client_a.cbs_client_id = "CBS-DC-2"
        client_a.save(update_fields=["cbs_client_id"])
        case = _case(tenant_a, product_a, client_a, ref="DAT-COL-RES")
        g = _guarantee(tenant_a, client_a, value="60000", ref="GAR-DC-RES")
        req = initiate_dation_request(
            client=client_a,
            user=agent,
            cbs_client_id="CBS-DC-2",
            application=case.loan.application,
            guarantee_ids=[str(g.id)],
            as_draft=True,
        )
        assert req.covers_claim() is False
        complete_dation_request(req)
        req.refresh_from_db()
        case.refresh_from_db()
        assert req.status == DationRequest.Status.COMPLETED
        assert case.stage != case.Stage.CLOSED
        assert case.next_action_type == CollectionActionType.DATION
        logged = CollectionAction.objects.filter(
            case=case, action_type=CollectionActionType.DATION
        )
        assert logged.exists()
        assert "résiduel" in logged.first().comment.lower()

    api = _api(agent, tenant_a)
    detail = api.get(f"/api/v1/collection-cases/{case.id}/")
    assert detail.data["financial_ops_frozen"] is False
    assert detail.data["can_collect"] is True


@patch(
    "apps.guarantees.process_services.assert_client_outstanding_for_dation",
    return_value=CBS_OK,
)
def test_completed_full_coverage_keeps_finance_frozen(
    _cbs, tenant_a, product_a, client_a, agent
):
    with tenant_context(tenant_a.id):
        ensure_default_tranches(tenant_a)
        client_a.cbs_client_id = "CBS-DC-3"
        client_a.save(update_fields=["cbs_client_id"])
        case = _case(tenant_a, product_a, client_a, ref="DAT-COL-FULL")
        g = _guarantee(tenant_a, client_a, value="120000", ref="GAR-DC-FULL")
        req = initiate_dation_request(
            client=client_a,
            user=agent,
            cbs_client_id="CBS-DC-3",
            application=case.loan.application,
            guarantee_ids=[str(g.id)],
            as_draft=True,
        )
        assert req.covers_claim() is True
        complete_dation_request(req)
        case.refresh_from_db()
        assert case.stage != case.Stage.CLOSED
        assert case.next_action_type == CollectionActionType.DATION

    api = _api(agent, tenant_a)
    detail = api.get(f"/api/v1/collection-cases/{case.id}/")
    assert detail.data["financial_ops_frozen"] is True
    assert detail.data["can_collect"] is False
    blocked = api.post(
        f"/api/v1/collection-cases/{case.id}/repayments/",
        {"amount": "500", "payment_date": date.today().isoformat()},
        format="json",
    )
    assert blocked.status_code == 400


@patch(
    "apps.guarantees.process_services.assert_client_outstanding_for_dation",
    return_value=CBS_OK,
)
def test_navigation_links_credit_dation(
    _cbs, tenant_a, product_a, client_a, agent
):
    with tenant_context(tenant_a.id):
        ensure_default_tranches(tenant_a)
        client_a.cbs_client_id = "CBS-DC-NAV"
        client_a.save(update_fields=["cbs_client_id"])
        case = _case(tenant_a, product_a, client_a, ref="DAT-COL-NAV")
        g = _guarantee(tenant_a, client_a, value="60000", ref="GAR-DC-NAV")
        g.application = case.loan.application
        g.save(update_fields=["application"])
        req = initiate_dation_request(
            client=client_a,
            user=agent,
            cbs_client_id="CBS-DC-NAV",
            application=case.loan.application,
            guarantee_ids=[str(g.id)],
            as_draft=True,
        )

    api = _api(agent, tenant_a)
    app = api.get(f"/api/v1/credit-applications/{case.loan.application_id}/")
    assert app.status_code == 200
    assert app.data["collection_case_id"] == str(case.id)

    loans = api.get(
        "/api/v1/loans/", {"application": str(case.loan.application_id)}
    )
    assert loans.status_code == 200
    row = next(r for r in loans.data["results"] if r["id"] == str(case.loan_id))
    assert row["collection_case_id"] == str(case.id)

    dation = api.get(f"/api/v1/dation-requests/{req.id}/")
    assert dation.status_code == 200
    assert str(dation.data["application"]) == str(case.loan.application_id)
    assert str(dation.data["collection_case_id"]) == str(case.id)
    assert dation.data["application_reference"] == "DAT-COL-NAV"

    listed = api.get(
        "/api/v1/dation-requests/",
        {"application": str(case.loan.application_id)},
    )
    assert listed.status_code == 200
    assert any(str(r["id"]) == str(req.id) for r in listed.data["results"])

    gar = api.get(f"/api/v1/guarantees/{g.id}/")
    assert gar.status_code == 200
    assert str(gar.data["open_dation_id"]) == str(req.id)
    assert str(gar.data["collection_case_id"]) == str(case.id)


def test_guarantee_list_application_and_collection_link(
    tenant_a, product_a, client_a, agent
):
    with tenant_context(tenant_a.id):
        ensure_default_tranches(tenant_a)
        case = _case(tenant_a, product_a, client_a, ref="GAR-LIST-APP")
        app = case.loan.application
        attached = _guarantee(tenant_a, client_a, ref="GAR-ON-APP")
        attached.application = app
        attached.save(update_fields=["application"])
        _guarantee(tenant_a, client_a, ref="GAR-OTHER")

    api = _api(agent, tenant_a)
    res = api.get("/api/v1/guarantees/", {"application": str(app.id)})
    assert res.status_code == 200, res.content
    refs = {r["reference"] for r in res.data["results"]}
    assert "GAR-ON-APP" in refs
    assert "GAR-OTHER" not in refs
    row = next(r for r in res.data["results"] if r["reference"] == "GAR-ON-APP")
    assert row["client_display"]
    assert row["application_reference"] == "GAR-LIST-APP"
    assert str(row["collection_case_id"]) == str(case.id)


def test_collection_case_exposes_sureties(
    tenant_a, product_a, client_a, agent
):
    from apps.sureties.models import Surety, SuretyEngagement

    with tenant_context(tenant_a.id):
        ensure_default_tranches(tenant_a)
        case = _case(tenant_a, product_a, client_a, ref="SURETY-COL")
        surety = Surety.objects.create(
            tenant=tenant_a,
            surety_type=Surety.SuretyType.PHYSICAL,
            first_name="Awa",
            last_name="Diallo",
            commitment_ceiling=Decimal("5000000"),
        )
        eng = SuretyEngagement.objects.create(
            tenant=tenant_a,
            surety=surety,
            application=case.loan.application,
            amount=Decimal("1000000"),
            engagement_type=SuretyEngagement.EngagementType.SOLIDAIRE,
        )

    api = _api(agent, tenant_a)
    res = api.get(f"/api/v1/collection-cases/{case.id}/")
    assert res.status_code == 200, res.content
    rows = res.data.get("surety_engagements") or []
    assert any(str(r["id"]) == str(eng.id) for r in rows)
    row = next(r for r in rows if str(r["id"]) == str(eng.id))
    assert "Diallo" in row["surety_display"]
    assert row["status"] == SuretyEngagement.Status.ACTIVE
