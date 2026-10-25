"""Circuit d'analyse restructuration / passage en perte (initiateur ≠ valideur)."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.models import DataScope
from apps.accounts.services import (
    CHARGE_AFFAIRE_ROLE_NAME,
    CHEF_AGENCE_ROLE_NAME,
    ensure_default_role_packs,
    get_or_create_tenant_role,
)
from apps.collections.models import LoanRestructure, WriteOff
from apps.collections.services import (
    approve_restructure,
    approve_write_off,
    propose_restructure,
    propose_write_off,
    refresh_loan_overdue,
)
from apps.common.tenancy import tenant_context
from apps.credits.models import CreditApplication, Installment, Loan

User = get_user_model()

pytestmark = pytest.mark.django_db


def _role_user(tenant, username, role_name):
    ensure_default_role_packs(tenant)
    group, _ = get_or_create_tenant_role(tenant, role_name)
    user = User.objects.create_user(
        username=username,
        password="test-pass-123",
        email=f"{username}@example.com",
        tenant=tenant,
        data_scope=DataScope.TENANT,
    )
    user.groups.add(group)
    return User.objects.get(pk=user.pk)


def _api(user, tenant):
    client = APIClient()
    client.force_authenticate(user=user)
    client.credentials(HTTP_X_TENANT_ID=str(tenant.id))
    return client


def _loan(tenant, product, client_obj, *, ref, days=40, principal="12000"):
    app = CreditApplication.objects.create(
        tenant=tenant,
        client=client_obj,
        product=product,
        amount_requested=Decimal(principal),
        duration_months=12,
        interest_rate=Decimal("12"),
        risk_level=1,
        reference=ref,
        status=CreditApplication.Status.DISBURSED,
    )
    loan = Loan.objects.create(
        tenant=tenant,
        application=app,
        principal=Decimal(principal),
        interest_rate=Decimal("12"),
        duration_months=12,
        disbursed_at=date.today() - timedelta(days=days + 10),
        first_due_date=date.today() - timedelta(days=days),
        status=Loan.Status.ACTIVE,
    )
    Installment.objects.create(
        tenant=tenant,
        loan=loan,
        number=1,
        due_date=date.today() - timedelta(days=days),
        principal_due=Decimal(principal),
        interest_due=Decimal("0"),
        total_due=Decimal(principal),
        status=Installment.Status.OVERDUE,
    )
    return loan


def test_propose_from_loan_keeps_schedule(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        loan = _loan(tenant_a, product_a, client_a, ref="RST-LOAN")
        record = propose_restructure(
            loan,
            new_duration_months=24,
            reason="Mensualités trop lourdes",
            origin=LoanRestructure.Origin.LOAN,
            request_kind=LoanRestructure.RequestKind.CLIENT,
        )
        loan.refresh_from_db()
        assert record.status == LoanRestructure.Status.PENDING
        assert record.origin == LoanRestructure.Origin.LOAN
        assert record.request_kind == LoanRestructure.RequestKind.CLIENT
        assert record.case_id is None
        assert loan.duration_months == 12
        assert loan.installments.count() == 1
        assert record.proposed_schedule.get("count") == 24


def test_approve_does_not_mutate_schedule(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        ca = _role_user(tenant_a, "ca_rst", CHARGE_AFFAIRE_ROLE_NAME)
        chef = _role_user(tenant_a, "chef_rst", CHEF_AGENCE_ROLE_NAME)
        loan = _loan(tenant_a, product_a, client_a, ref="RST-APP")
        record = propose_restructure(
            loan,
            new_duration_months=18,
            reason="Demande client après 3 échéances",
            origin=LoanRestructure.Origin.LOAN,
            request_kind=LoanRestructure.RequestKind.CLIENT,
            user=ca,
        )
        approved = approve_restructure(record, user=chef)
        loan.refresh_from_db()
        assert approved.status == LoanRestructure.Status.APPROVED
        assert approved.applied_by_id == chef.id
        assert loan.duration_months == 12
        assert loan.interest_rate == Decimal("12")
        assert loan.installments.count() == 1


def test_same_user_cannot_approve_own_request(tenant_a, product_a, client_a):
    from rest_framework.exceptions import PermissionDenied

    with tenant_context(tenant_a.id):
        chef = _role_user(tenant_a, "chef_sod", CHEF_AGENCE_ROLE_NAME)
        loan = _loan(tenant_a, product_a, client_a, ref="RST-SOD")
        record = propose_restructure(
            loan,
            new_duration_months=18,
            reason="Demande client",
            user=chef,
        )
        with pytest.raises(PermissionDenied):
            approve_restructure(record, user=chef)


def test_api_loan_propose_and_chef_approve(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        ca = _role_user(tenant_a, "ca_api", CHARGE_AFFAIRE_ROLE_NAME)
        chef = _role_user(tenant_a, "chef_api", CHEF_AGENCE_ROLE_NAME)
        loan = _loan(tenant_a, product_a, client_a, ref="RST-API")

    ca_api = _api(ca, tenant_a)
    preview = ca_api.post(
        f"/api/v1/loans/{loan.id}/preview-restructure/",
        {"new_duration_months": 18, "reason": "Mensualités trop lourdes"},
        format="json",
    )
    assert preview.status_code == 200, preview.content
    assert preview.data["count"] == 18

    proposed = ca_api.post(
        f"/api/v1/loans/{loan.id}/restructure/",
        {
            "new_duration_months": 18,
            "reason": "Mensualités trop lourdes",
            "request_kind": "CLIENT",
        },
        format="json",
    )
    assert proposed.status_code == 200, proposed.content
    rec = proposed.data["restructures"][0]
    assert rec["status"] == "PENDING"
    assert rec["origin"] == "LOAN"

    same = ca_api.post(
        f"/api/v1/loan-restructures/{rec['id']}/approve/",
        {},
        format="json",
    )
    assert same.status_code == 403

    chef_api = _api(chef, tenant_a)
    ok = chef_api.post(
        f"/api/v1/loan-restructures/{rec['id']}/approve/",
        {"comment": "Accord chef d'agence"},
        format="json",
    )
    assert ok.status_code == 200, ok.content
    assert ok.data["status"] == "APPROVED"

    with tenant_context(tenant_a.id):
        loan.refresh_from_db()
        assert loan.duration_months == 12


def test_api_write_off_second_look(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        ca = _role_user(tenant_a, "ca_wo", CHARGE_AFFAIRE_ROLE_NAME)
        chef = _role_user(tenant_a, "chef_wo", CHEF_AGENCE_ROLE_NAME)
        loan = _loan(tenant_a, product_a, client_a, ref="WO-API", days=20)
        loan.application.created_by = ca
        loan.application.save(update_fields=["created_by"])
        case = refresh_loan_overdue(
            loan,
            cbs_status={"days_overdue": 20, "overdue_amount": "12000"},
        )

    ca_api = _api(ca, tenant_a)
    proposed = ca_api.post(
        f"/api/v1/collection-cases/{case.id}/write-off/",
        {"reason": "Irrécouvrable après contentieux"},
        format="json",
    )
    assert proposed.status_code == 200, proposed.content
    wo = proposed.data["write_offs"][0]
    assert wo["status"] == "PENDING"

    with tenant_context(tenant_a.id):
        loan.refresh_from_db()
        assert loan.status == Loan.Status.ACTIVE

    denied = ca_api.post(
        f"/api/v1/write-offs/{wo['id']}/approve/", {}, format="json"
    )
    assert denied.status_code == 403

    chef_api = _api(chef, tenant_a)
    ok = chef_api.post(
        f"/api/v1/write-offs/{wo['id']}/approve/",
        {"comment": "Validé"},
        format="json",
    )
    assert ok.status_code == 200, ok.content
    assert ok.data["status"] == "APPLIED"

    with tenant_context(tenant_a.id):
        loan.refresh_from_db()
        case.refresh_from_db()
        assert loan.status == Loan.Status.DEFAULTED
        assert case.stage == "CLOSED"


def test_reject_write_off_leaves_loan_active(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        ca = _role_user(tenant_a, "ca_wor", CHARGE_AFFAIRE_ROLE_NAME)
        chef = _role_user(tenant_a, "chef_wor", CHEF_AGENCE_ROLE_NAME)
        loan = _loan(tenant_a, product_a, client_a, ref="WO-REJ", days=20)
        case = refresh_loan_overdue(
            loan,
            cbs_status={"days_overdue": 20, "overdue_amount": "12000"},
        )
        record = propose_write_off(case, reason="Proposition perte", user=ca)
        from apps.collections.services import reject_write_off

        reject_write_off(record, user=chef, comment="Encore recouvrable")
        loan.refresh_from_db()
        case.refresh_from_db()
        assert loan.status == Loan.Status.ACTIVE
        assert case.stage != "CLOSED"
        assert WriteOff.objects.get(pk=record.pk).status == WriteOff.Status.REJECTED


def test_loan_origin_restructure_visible_on_collection_case(
    tenant_a, product_a, client_a,
):
    with tenant_context(tenant_a.id):
        loan = _loan(tenant_a, product_a, client_a, ref="RST-VIS")
        record = propose_restructure(
            loan,
            new_duration_months=24,
            reason="Demande née sur le prêt",
            origin=LoanRestructure.Origin.LOAN,
            request_kind=LoanRestructure.RequestKind.CLIENT,
        )
        assert record.case_id is None
        case = refresh_loan_overdue(
            loan,
            cbs_status={"days_overdue": 40, "overdue_amount": "12000"},
        )
        record.refresh_from_db()
        assert record.case_id == case.id

    viewer = User.objects.create_user(
        username="rst_vis_admin",
        password="test-pass-123",
        email="rst-vis@example.com",
        is_superuser=True,
        is_staff=True,
        is_group_level=True,
    )
    api = _api(viewer, tenant_a)
    res = api.get(f"/api/v1/collection-cases/{case.id}/")
    assert res.status_code == 200, res.content
    ids = [str(row["id"]) for row in res.data["restructures"]]
    assert str(record.id) in ids
    assert res.data["restructures"][0]["origin"] == LoanRestructure.Origin.LOAN
