"""Parcours UAT FinFlow — hors branchement CBS live.

Chaîne : client → dossier → analyse → circuit → décaissement local
→ prêt / échéancier → recouvrement (statut injecté) → restructuration / perte.
Les encaissements restent refusés (CBS only).
"""
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from apps.accounts.models import DataScope, User
from apps.clients.models import Client
from apps.collections.services import (
    approve_restructure,
    approve_write_off,
    propose_restructure,
    propose_write_off,
    refresh_loan_overdue,
)
from apps.common.tenancy import tenant_context
from apps.credits.models import CreditApplication, Loan
from apps.guarantees.models import DocumentType
from apps.workflow.models import ApprovalStep, ApprovalTask, WorkflowDefinition

pytestmark = pytest.mark.django_db


def _auth(user, tenant):
    api = APIClient()
    api.force_authenticate(user)
    return api, {"HTTP_X_TENANT_ID": str(tenant.id), "HTTP_HOST": "localhost"}


def _staff(tenant, username):
    return User.objects.create_user(
        username=username,
        password="x",
        tenant=tenant,
        is_staff=True,
        is_superuser=True,
        data_scope=DataScope.TENANT,
    )


def _circuit(tenant, *, code, group_name):
    role = Group.objects.create(name=group_name)
    definition = WorkflowDefinition.objects.create(
        tenant=tenant, code=code, version=1, is_active=True
    )
    ApprovalStep.objects.create(
        tenant=tenant,
        definition=definition,
        name="Comité UAT",
        order=1,
        required_group=role,
        sla_hours=24,
        step_kind=ApprovalStep.StepKind.DECISIONAL,
    )
    return role


def test_uat_credit_pipeline_to_local_loan(tenant_a, product_a):
    submitter = _staff(tenant_a, "uat_sub")
    validator = _staff(tenant_a, "uat_val")
    with tenant_context(tenant_a.id):
        role = _circuit(tenant_a, code="WF-UAT-CR", group_name="UAT Comité")
        validator.groups.add(role)

    api, headers = _auth(submitter, tenant_a)
    client_res = api.post(
        "/api/v1/clients/",
        {
            "client_type": "INDIVIDUAL",
            "first_name": "Awa",
            "last_name": "Koné",
            "kyc_status": "VALIDATED",
        },
        format="json",
        **headers,
    )
    assert client_res.status_code == 201, client_res.content
    client_id = client_res.json()["id"]
    assert client_res.json()["display_name"] == "Awa Koné"
    assert client_res.json()["reference"].startswith("PAR-")

    app_res = api.post(
        "/api/v1/credit-applications/",
        {
            "client": client_id,
            "product": str(product_a.id),
            "amount_requested": "500000",
            "duration_months": 12,
        },
        format="json",
        **headers,
    )
    assert app_res.status_code == 201, app_res.content
    app_id = app_res.json()["id"]
    assert app_res.json()["status"] == "DRAFT"
    assert app_res.json()["client_display"] == "Awa Koné"

    analysis = api.post(
        "/api/v1/financial-analyses/",
        {
            "application": app_id,
            "is_reference": True,
            "recommendation": "FAVORABLE",
            "salary_income": "300000",
        },
        format="json",
        **headers,
    )
    assert analysis.status_code == 201, analysis.content
    first_installment = Decimal(str(analysis.json()["new_installment"]))
    assert first_installment > 0

    patched = api.patch(
        f"/api/v1/credit-applications/{app_id}/",
        {"amount_requested": "2000000", "amount_proposed": "2000000"},
        format="json",
        **headers,
    )
    assert patched.status_code == 200, patched.content
    refreshed = api.get(
        f"/api/v1/financial-analyses/{analysis.json()['id']}/", **headers
    )
    assert refreshed.status_code == 200, refreshed.content
    assert Decimal(str(refreshed.json()["new_installment"])) > first_installment

    submitted = api.post(
        f"/api/v1/credit-applications/{app_id}/submit/", {}, format="json", **headers
    )
    assert submitted.status_code == 200, submitted.content
    assert submitted.json()["status"] == "IN_APPROVAL"

    with tenant_context(tenant_a.id):
        task = ApprovalTask.objects.get(instance__object_id=app_id)

    val_api, val_headers = _auth(validator, tenant_a)
    decided = val_api.post(
        f"/api/v1/approval-tasks/{task.id}/decide/",
        {"decision": "APPROVED", "opinion": "FAVORABLE", "comment": "UAT"},
        format="json",
        **val_headers,
    )
    assert decided.status_code == 200, decided.content

    detail = api.get(f"/api/v1/credit-applications/{app_id}/", **headers)
    assert detail.status_code == 200
    assert detail.json()["status"] == "APPROVED"

    from tests.setup_helpers import configure_local_cbs, prepare_setup
    application = CreditApplication.all_tenants.get(pk=app_id)
    configure_local_cbs(application)
    executor = prepare_setup(application)
    execution_api, execution_headers = _auth(executor, tenant_a)
    with patch("apps.corebanking.disbursement.submit_credit_to_cbs", return_value={
        "external_id": application.reference, "num_contrat": "UAT-CONTRACT",
        "num_demande": "UAT-DEMANDE", "ref_demande": "UAT-REF", "raw": {"responseCode": 200},
    }) as submit_cbs:
        disbursed = execution_api.post(
            f"/api/v1/credit-applications/{app_id}/disburse/",
            {}, format="json", **execution_headers,
        )
    submit_cbs.assert_called_once()
    assert disbursed.status_code == 200, disbursed.content
    loan_id = disbursed.json()["id"]
    assert disbursed.json()["status"] == "ACTIVE"
    assert disbursed.json()["cbs_contract_number"] == "UAT-CONTRACT"
    assert Decimal(str(disbursed.json()["principal"])) == Decimal("2000000")

    loan_detail = api.get(f"/api/v1/loans/{loan_id}/", **headers)
    assert loan_detail.status_code == 200, loan_detail.content
    assert loan_detail.json()["application"] == app_id
    assert loan_detail.json()["application_reference"]
    assert len(loan_detail.json().get("installments") or []) >= 1

    app_after = api.get(f"/api/v1/credit-applications/{app_id}/", **headers)
    assert app_after.json()["status"] == "DISBURSED"
    assert app_after.json()["loan_id"] == str(loan_id)

    denied = api.post(
        "/api/v1/repayments/",
        {"loan": loan_id, "amount": "1000", "payment_date": str(date.today())},
        format="json",
        **headers,
    )
    assert denied.status_code == 400, denied.content
    assert denied.json()["success"] is False


def test_uat_collection_restructure_and_writeoff(tenant_a, product_a, client_a):
    ca = _staff(tenant_a, "uat_ca")
    chef = _staff(tenant_a, "uat_chef")
    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="DOS-UAT-REC",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("1000000"),
            amount_approved=Decimal("1000000"),
            duration_months=12,
            status=CreditApplication.Status.DISBURSED,
            created_by=ca,
            submitted_by=ca,
        )
        loan = Loan.objects.create(
            tenant=tenant_a,
            application=app,
            principal=Decimal("1000000"),
            interest_rate=Decimal("12"),
            duration_months=12,
            disbursed_at=date.today() - timedelta(days=50),
            first_due_date=date.today() - timedelta(days=40),
            status=Loan.Status.ACTIVE,
        )
        from apps.credits.models import Installment

        Installment.objects.create(
            tenant=tenant_a,
            loan=loan,
            number=1,
            due_date=date.today() - timedelta(days=40),
            principal_due=Decimal("1000000"),
            interest_due=Decimal("0"),
            total_due=Decimal("1000000"),
            status=Installment.Status.OVERDUE,
        )
        case = refresh_loan_overdue(
            loan,
            cbs_status={
                "settled": False,
                "days_overdue": 40,
                "overdue_amount": Decimal("1000000"),
            },
        )
        assert case.days_overdue == 40
        assert case.overdue_amount == Decimal("1000000")

        record = propose_restructure(
            loan, new_duration_months=18, reason="UAT mensualités", user=ca
        )
        approved = approve_restructure(record, user=chef, comment="Accord UAT")
        assert approved.status == approved.Status.APPROVED
        loan.refresh_from_db()
        assert loan.duration_months == 12

        wo_app = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="DOS-UAT-WO",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("800000"),
            duration_months=12,
            status=CreditApplication.Status.DISBURSED,
        )
        wo_loan = Loan.objects.create(
            tenant=tenant_a,
            application=wo_app,
            principal=Decimal("800000"),
            interest_rate=Decimal("12"),
            duration_months=12,
            disbursed_at=date.today() - timedelta(days=200),
            first_due_date=date.today() - timedelta(days=180),
            status=Loan.Status.ACTIVE,
        )
        Installment.objects.create(
            tenant=tenant_a,
            loan=wo_loan,
            number=1,
            due_date=date.today() - timedelta(days=180),
            principal_due=Decimal("800000"),
            interest_due=Decimal("0"),
            total_due=Decimal("800000"),
            status=Installment.Status.OVERDUE,
        )
        wo_case = refresh_loan_overdue(
            wo_loan,
            cbs_status={
                "settled": False,
                "days_overdue": 180,
                "overdue_amount": Decimal("800000"),
            },
        )
        wo = propose_write_off(wo_case, reason="Perte UAT", user=ca)
        done = approve_write_off(wo, user=chef, comment="Perte actée")
        assert done.status == done.Status.APPLIED
        wo_loan.refresh_from_db()
        wo_case.refresh_from_db()
        assert wo_loan.status == Loan.Status.DEFAULTED
        assert wo_case.overdue_amount == 0
        assert wo_case.stage == wo_case.Stage.CLOSED

    api, headers = _auth(ca, tenant_a)
    listing = api.get("/api/v1/collection-cases/", {"open": 1}, **headers)
    assert listing.status_code == 200, listing.content
    ids = {row["id"] for row in listing.json()["results"]}
    assert str(case.id) in ids
    assert str(wo_case.id) not in ids


def test_uat_guarantee_and_after_sales_hub(tenant_a, product_a, client_a):
    user = _staff(tenant_a, "uat_gar")
    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="DOS-UAT-GAR",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("1500000"),
            duration_months=12,
            created_by=user,
        )

    api, headers = _auth(user, tenant_a)
    created = api.post(
        "/api/v1/guarantees/",
        {
            "client": str(client_a.id),
            "application": str(app.id),
            "guarantee_type": "MORTGAGE",
            "document_type": DocumentType.LAND_TITLE,
            "document_number": "TF-UAT-1",
            "document_issue_date": "2024-01-15",
            "description": "Villa UAT",
            "expertise_value": "5000000",
            "expertise_date": "2024-02-01",
            "expert_name": "Cabinet UAT",
            "current_value": "5000000",
            "belongs_to_applicant": True,
        },
        format="json",
        **headers,
    )
    assert created.status_code == 201, created.content
    assert created.json()["client"] == str(client_a.id)
    assert created.json()["application"] == str(app.id)

    hub = api.get("/api/v1/reporting/after-sales-hub/", **headers)
    assert hub.status_code == 200, hub.content
    assert "modules" in hub.json()
    assert "recent" in hub.json()


def test_uat_groupement_contracts_and_tenant_isolation(
    tenant_a, tenant_b, product_a
):
    from apps.contracts.context import build_context
    from apps.contracts.models import ContractTemplate

    user_a = _staff(tenant_a, "uat_iso_a")
    api_a, headers_a = _auth(user_a, tenant_a)
    groupement = api_a.post(
        "/api/v1/clients/",
        {
            "client_type": "PROFESSIONAL",
            "company_name": "GIE UAT Maraîchers",
            "kyc_status": "VALIDATED",
        },
        format="json",
        **headers_a,
    )
    assert groupement.status_code == 201, groupement.content
    assert groupement.json()["display_name"] == "GIE UAT Maraîchers"
    assert groupement.json()["reference"].startswith("GRP-")

    with tenant_context(tenant_a.id):
        client = Client.objects.get(pk=groupement.json()["id"])
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="DOS-UAT-GIE",
            client=client,
            product=product_a,
            amount_requested=Decimal("900000"),
            duration_months=12,
        )
        assert ContractTemplate(
            applies_to=ContractTemplate.AppliesTo.CORPORATE,
            is_active=True,
            name="Caution UAT",
        ).applies_to_application(app)
        ctx = build_context(app)
        assert "GIE UAT Maraîchers" in str(ctx)

    user_b = User.objects.create_user(
        username="uat_iso_b",
        password="x",
        is_group_level=True,
        is_staff=True,
        is_superuser=True,
    )
    api_b, headers_b = _auth(user_b, tenant_b)
    hidden = api_b.get(f"/api/v1/clients/{groupement.json()['id']}/", **headers_b)
    assert hidden.status_code in (403, 404)
