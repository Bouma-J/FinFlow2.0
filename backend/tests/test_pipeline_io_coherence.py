"""Contrats d'entrée / sortie des pipelines métier (API ↔ données ↔ UI)."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import DataScope, User
from apps.catalog.models import CreditProduct
from apps.clients.models import Client
from apps.collections.models import CollectionCase
from apps.common.tenancy import tenant_context
from apps.credits.models import CreditApplication, FinancialAnalysis, Installment, Loan
from apps.credits.services import submit_application
from apps.guarantees.models import DocumentType, Guarantee
from apps.workflow.models import ApprovalStep, ApprovalTask, WorkflowDefinition, WorkflowInstance

pytestmark = pytest.mark.django_db


UI_APPLICATION_LIST_FIELDS = {
    "id",
    "reference",
    "client",
    "client_display",
    "client_reference",
    "product_label",
    "agency",
    "agency_display",
    "amount_requested",
    "amount_proposed",
    "amount_approved",
    "status",
    "status_display",
    "submitted_by_display",
    "collection_case_id",
    "collection_stage_display",
}

UI_COLLECTION_LIST_FIELDS = {
    "id",
    "loan",
    "application_id",
    "application_reference",
    "client_id",
    "client_name",
    "stage",
    "stage_display",
    "par_class",
    "par_class_display",
    "days_overdue",
    "overdue_amount",
    "assigned_to",
}

UI_MY_DOSSIERS_FIELDS = {
    "id",
    "target_kind",
    "detail_path",
    "reference",
    "client_display",
    "client_type",
    "client_type_display",
    "amount_requested",
    "amount_proposed",
    "status",
    "status_display",
    "current_step_name",
    "current_step_label",
}


def _auth(user, tenant):
    api = APIClient()
    api.force_authenticate(user)
    return api, {"HTTP_X_TENANT_ID": str(tenant.id), "HTTP_HOST": "localhost"}


def _staff(tenant, username="io_staff"):
    return User.objects.create_user(
        username=username,
        password="x",
        tenant=tenant,
        is_staff=True,
        is_superuser=True,
        data_scope=DataScope.TENANT,
    )


def _legal_client(tenant, *, ref, client_type, company_name):
    return Client.objects.create(
        tenant=tenant,
        reference=ref,
        client_type=client_type,
        company_name=company_name,
        kyc_status=Client.KycStatus.VALIDATED,
    )


def _app(tenant, client, product, *, ref, amount="1000000", proposed=None, user=None):
    return CreditApplication.objects.create(
        tenant=tenant,
        reference=ref,
        client=client,
        product=product,
        amount_requested=Decimal(amount),
        amount_proposed=Decimal(proposed) if proposed is not None else None,
        duration_months=12,
        created_by=user,
        submitted_by=user,
    )


def test_client_display_name_and_reference_prefix_by_type(tenant_a):
    with tenant_context(tenant_a.id):
        person = Client.objects.create(
            tenant=tenant_a,
            client_type=Client.ClientType.INDIVIDUAL,
            first_name="Awa",
            last_name="Koné",
            kyc_status=Client.KycStatus.VALIDATED,
        )
        gie = Client.objects.create(
            tenant=tenant_a,
            client_type=Client.ClientType.PROFESSIONAL,
            company_name="GIE Marie N'Guessan",
            kyc_status=Client.KycStatus.VALIDATED,
        )
        empty_gie = Client.objects.create(
            tenant=tenant_a,
            client_type=Client.ClientType.PROFESSIONAL,
            kyc_status=Client.KycStatus.VALIDATED,
        )
        corp = Client.objects.create(
            tenant=tenant_a,
            client_type=Client.ClientType.CORPORATE,
            company_name="SODEF SARL",
            kyc_status=Client.KycStatus.VALIDATED,
        )

    assert person.display_name == "Awa Koné"
    assert person.reference.startswith("PAR-")
    assert gie.display_name == "GIE Marie N'Guessan"
    assert gie.reference.startswith("GRP-")
    assert empty_gie.display_name == "(sans raison sociale)"
    assert corp.display_name == "SODEF SARL"
    assert corp.reference.startswith("ENT-")
    assert gie.is_legal_entity is True
    assert person.is_legal_entity is False


def test_client_api_rejects_groupement_without_company_name(tenant_a):
    user = _staff(tenant_a, "io_cli")
    api, headers = _auth(user, tenant_a)
    res = api.post(
        "/api/v1/clients/",
        {
            "client_type": "PROFESSIONAL",
            "first_name": "Marie",
            "last_name": "NGuessan",
        },
        format="json",
        **headers,
    )
    assert res.status_code == 400, res.content
    body = res.json()
    assert body["success"] is False
    assert body["status_code"] == 400
    assert "company_name" in body["errors"]


def test_client_api_out_matches_list_and_detail_contract(tenant_a, client_a):
    user = _staff(tenant_a, "io_cli2")
    api, headers = _auth(user, tenant_a)
    listing = api.get("/api/v1/clients/", **headers)
    assert listing.status_code == 200, listing.content
    row = next(r for r in listing.json()["results"] if r["id"] == str(client_a.id))
    for key in ("id", "reference", "client_type", "display_name", "kyc_status"):
        assert key in row
    assert row["display_name"] == client_a.display_name
    assert row["client_type"] == "INDIVIDUAL"

    detail = api.get(f"/api/v1/clients/{client_a.id}/", **headers)
    assert detail.status_code == 200, detail.content
    data = detail.json()
    assert data["display_name"] == "Test Client"
    assert data["client_type"] == row["client_type"]
    assert data["reference"] == row["reference"]


def test_product_professional_label_is_groupement(tenant_a, product_a):
    assert dict(CreditProduct.ClientType.choices)["PROFESSIONAL"] == "Groupement"
    user = _staff(tenant_a, "io_prod")
    api, headers = _auth(user, tenant_a)
    res = api.get(f"/api/v1/credit-products/{product_a.id}/", **headers)
    assert res.status_code == 200, res.content
    assert "client_type" in res.json()


def test_application_list_and_detail_expose_ui_fields_and_loan_case(
    tenant_a, product_a, client_a
):
    user = _staff(tenant_a, "io_app")
    with tenant_context(tenant_a.id):
        app = _app(
            tenant_a,
            client_a,
            product_a,
            ref="DOS-IO-1",
            proposed="750000",
            user=user,
        )
        loan = Loan.objects.create(
            tenant=tenant_a,
            application=app,
            principal=Decimal("750000"),
            interest_rate=Decimal("12"),
            duration_months=12,
            disbursed_at=date.today(),
            first_due_date=date.today(),
            status=Loan.Status.ACTIVE,
        )
        case = CollectionCase.objects.create(
            tenant=tenant_a,
            loan=loan,
            stage=CollectionCase.Stage.PRECONTENTIOUS,
            days_overdue=40,
            overdue_amount=Decimal("100000"),
        )

    api, headers = _auth(user, tenant_a)
    listing = api.get("/api/v1/credit-applications/", **headers)
    assert listing.status_code == 200, listing.content
    row = next(r for r in listing.json()["results"] if r["reference"] == "DOS-IO-1")
    missing = UI_APPLICATION_LIST_FIELDS - set(row)
    assert not missing, missing
    assert row["client_display"] == client_a.display_name
    assert row["amount_proposed"] == "750000.00" or Decimal(row["amount_proposed"]) == Decimal(
        "750000"
    )
    assert row["collection_case_id"] == str(case.id)
    assert row["collection_stage_display"] == "Précontentieux"

    detail = api.get(f"/api/v1/credit-applications/{app.id}/", **headers)
    assert detail.status_code == 200, detail.content
    data = detail.json()
    assert data["loan_id"] == str(loan.id)
    assert data["collection_case_id"] == str(case.id)
    assert data["client_type"] == "INDIVIDUAL"
    assert data["amount_proposed"] is not None


def test_loan_list_points_back_to_application_and_case(
    tenant_a, product_a, client_a
):
    user = _staff(tenant_a, "io_loan")
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a, ref="DOS-IO-LN")
        loan = Loan.objects.create(
            tenant=tenant_a,
            application=app,
            principal=Decimal("1000000"),
            interest_rate=Decimal("10"),
            duration_months=12,
            disbursed_at=date.today(),
            first_due_date=date.today(),
            status=Loan.Status.ACTIVE,
        )
        case = CollectionCase.objects.create(tenant=tenant_a, loan=loan)

    api, headers = _auth(user, tenant_a)
    res = api.get("/api/v1/loans/", **headers)
    assert res.status_code == 200, res.content
    row = next(r for r in res.json()["results"] if r["id"] == str(loan.id))
    assert row["application"] == str(app.id)
    assert row["collection_case_id"] == str(case.id)


def test_collection_case_reads_client_from_loan_application(
    tenant_a, product_a
):
    user = _staff(tenant_a, "io_col")
    with tenant_context(tenant_a.id):
        gie = _legal_client(
            tenant_a,
            ref="GRP-IO-1",
            client_type=Client.ClientType.PROFESSIONAL,
            company_name="GIE Pipeline",
        )
        app = _app(tenant_a, gie, product_a, ref="DOS-IO-COL")
        loan = Loan.objects.create(
            tenant=tenant_a,
            application=app,
            principal=Decimal("2000000"),
            interest_rate=Decimal("12"),
            duration_months=18,
            disbursed_at=date.today() - timedelta(days=50),
            first_due_date=date.today() - timedelta(days=40),
            status=Loan.Status.ACTIVE,
        )
        Installment.objects.create(
            tenant=tenant_a,
            loan=loan,
            number=1,
            due_date=date.today() - timedelta(days=40),
            principal_due=Decimal("2000000"),
            interest_due=Decimal("0"),
            total_due=Decimal("2000000"),
        )
        case = CollectionCase.objects.create(
            tenant=tenant_a,
            loan=loan,
            days_overdue=40,
            overdue_amount=Decimal("2000000"),
        )

    api, headers = _auth(user, tenant_a)
    listing = api.get("/api/v1/collection-cases/", **headers)
    assert listing.status_code == 200, listing.content
    row = next(r for r in listing.json()["results"] if r["id"] == str(case.id))
    missing = UI_COLLECTION_LIST_FIELDS - set(row)
    assert not missing, missing
    assert row["application_id"] == str(app.id)
    assert row["application_reference"] == "DOS-IO-COL"
    assert row["client_id"] == str(gie.id)
    assert row["client_name"] == "GIE Pipeline"
    assert row["loan"] == str(loan.id)

    detail = api.get(f"/api/v1/collection-cases/{case.id}/", **headers)
    assert detail.status_code == 200, detail.content
    body = detail.json()
    assert "restructures" in body
    assert "write_offs" in body
    assert body["client_name"] == "GIE Pipeline"


def test_repayment_create_denied_uses_error_envelope(tenant_a, product_a, client_a):
    user = _staff(tenant_a, "io_rep")
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a, ref="DOS-IO-REP")
        loan = Loan.objects.create(
            tenant=tenant_a,
            application=app,
            principal=Decimal("1000000"),
            interest_rate=Decimal("10"),
            duration_months=12,
            disbursed_at=date.today(),
            first_due_date=date.today(),
            status=Loan.Status.ACTIVE,
        )

    api, headers = _auth(user, tenant_a)
    res = api.post(
        "/api/v1/repayments/",
        {"loan": str(loan.id), "amount": "1000", "payment_date": str(date.today())},
        format="json",
        **headers,
    )
    assert res.status_code == 400, res.content
    body = res.json()
    assert body["success"] is False
    detail = body["errors"].get("detail")
    text = detail if isinstance(detail, str) else " ".join(detail)
    assert "CBS" in text or "encaissement" in text.lower() or "remboursement" in text.lower()


def test_my_dossiers_client_type_filters_and_amounts(
    tenant_a, product_a, client_a
):
    user = _staff(tenant_a, "io_tasks")
    with tenant_context(tenant_a.id):
        gie = _legal_client(
            tenant_a,
            ref="GRP-IO-T",
            client_type=Client.ClientType.PROFESSIONAL,
            company_name="GIE Validations",
        )
        corp = _legal_client(
            tenant_a,
            ref="ENT-IO-T",
            client_type=Client.ClientType.CORPORATE,
            company_name="Corp Validations",
        )
        person_app = _app(
            tenant_a, client_a, product_a, ref="DOS-IO-P", proposed="400000", user=user
        )
        gie_app = _app(tenant_a, gie, product_a, ref="DOS-IO-G", user=user)
        corp_app = _app(tenant_a, corp, product_a, ref="DOS-IO-C", user=user)
        role = Group.objects.create(name="IO Filtre")
        definition = WorkflowDefinition.objects.create(
            tenant=tenant_a, code="WF-IO", version=1, is_active=True
        )
        ApprovalStep.objects.create(
            tenant=tenant_a,
            definition=definition,
            name="Validation",
            order=1,
            required_group=role,
            sla_hours=24,
        )
        ct = ContentType.objects.get_for_model(CreditApplication)
        for app in (person_app, gie_app, corp_app):
            app.status = CreditApplication.Status.IN_APPROVAL
            app.save(update_fields=["status", "updated_at"])
            WorkflowInstance.objects.create(
                tenant=tenant_a,
                definition=definition,
                content_type=ct,
                object_id=app.id,
                amount=app.amount_requested,
            )

    api, headers = _auth(user, tenant_a)
    all_rows = api.get(
        "/api/v1/approval-tasks/my_dossiers/",
        {"queue": "all"},
        **headers,
    )
    assert all_rows.status_code == 200, all_rows.content
    refs = {r["reference"] for r in all_rows.json()["results"]}
    assert {"DOS-IO-P", "DOS-IO-G", "DOS-IO-C"} <= refs
    person_row = next(r for r in all_rows.json()["results"] if r["reference"] == "DOS-IO-P")
    missing = UI_MY_DOSSIERS_FIELDS - set(person_row)
    assert not missing, missing
    assert person_row["client_type"] == "INDIVIDUAL"
    assert person_row["amount_proposed"] is not None
    assert Decimal(person_row["amount_requested"]) == Decimal("1000000")
    assert Decimal(person_row["amount_proposed"]) == Decimal("400000")
    assert person_row["client_type_display"]

    groupement = api.get(
        "/api/v1/approval-tasks/my_dossiers/",
        {"client_type": "groupement", "queue": "all"},
        **headers,
    )
    assert {r["reference"] for r in groupement.json()["results"]} == {"DOS-IO-G"}
    assert groupement.json()["results"][0]["client_type"] == "PROFESSIONAL"
    assert groupement.json()["results"][0]["client_display"] == "GIE Validations"

    entreprise = api.get(
        "/api/v1/approval-tasks/my_dossiers/",
        {"client_type": "entreprise", "queue": "all"},
        **headers,
    )
    assert {r["reference"] for r in entreprise.json()["results"]} == {"DOS-IO-C"}

    particulier = api.get(
        "/api/v1/approval-tasks/my_dossiers/",
        {"client_type": "particulier", "queue": "all"},
        **headers,
    )
    assert {r["reference"] for r in particulier.json()["results"]} == {"DOS-IO-P"}


def test_submit_then_proposed_amount_updates_workflow_instance(
    tenant_a, product_a, client_a
):
    from django.contrib.auth.models import Group

    from apps.workflow.services import _apply_proposed_amount

    role = Group.objects.create(name="IO Validateur")
    validator = User.objects.create_user(username="io_val", password="x", tenant=tenant_a)
    validator.groups.add(role)
    submitter = User.objects.create_user(username="io_sub", password="x", tenant=tenant_a)

    with tenant_context(tenant_a.id):
        definition = WorkflowDefinition.objects.create(
            tenant=tenant_a, code="WF-IO-AMT", version=1, is_active=True
        )
        ApprovalStep.objects.create(
            tenant=tenant_a,
            definition=definition,
            name="Comité",
            order=1,
            required_group=role,
            sla_hours=24,
            step_kind=ApprovalStep.StepKind.DECISIONAL,
        )
        app = _app(
            tenant_a, client_a, product_a, ref="DOS-IO-AMT", amount="8000000", user=submitter
        )
        FinancialAnalysis.objects.create(
            tenant=tenant_a,
            application=app,
            is_reference=True,
            recommendation=FinancialAnalysis.Recommendation.FAVORABLE,
            salary_income=Decimal("300000"),
            client_type=client_a.client_type,
        )
        submit_application(app, submitter)
        instance = WorkflowInstance.objects.get(object_id=app.id)
        assert instance.amount == Decimal("8000000")
        _apply_proposed_amount(instance, Decimal("3000000"))
        instance.refresh_from_db()
        app.refresh_from_db()
        assert instance.amount == Decimal("3000000")
        task = ApprovalTask.objects.get(instance=instance)
        assert task.status == ApprovalTask.Status.PENDING


def test_guarantee_create_rejects_client_application_mismatch(
    tenant_a, product_a, client_a
):
    user = _staff(tenant_a, "io_gar")
    with tenant_context(tenant_a.id):
        other = _legal_client(
            tenant_a,
            ref="ENT-IO-G2",
            client_type=Client.ClientType.CORPORATE,
            company_name="Autre Client",
        )
        app = _app(tenant_a, client_a, product_a, ref="DOS-IO-GAR")

    api, headers = _auth(user, tenant_a)
    res = api.post(
        "/api/v1/guarantees/",
        {
            "client": str(other.id),
            "application": str(app.id),
            "guarantee_type": "MORTGAGE",
            "document_type": DocumentType.LAND_TITLE,
            "document_number": "TF-IO-1",
            "document_issue_date": "2024-01-15",
            "description": "Villa",
            "expertise_value": "5000000",
            "expertise_date": "2024-02-01",
            "expert_name": "Cabinet IO",
            "current_value": "5000000",
            "belongs_to_applicant": True,
        },
        format="json",
        **headers,
    )
    assert res.status_code == 400, res.content
    body = res.json()
    assert body["success"] is False
    blob = str(body["errors"]).lower()
    assert "client" in blob or "dossier" in blob or "application" in blob


def test_guarantee_detail_echoes_client_and_application(tenant_a, product_a, client_a):
    user = _staff(tenant_a, "io_gar2")
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a, ref="DOS-IO-GAR2")
        g = Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            application=app,
            guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
            document_type=DocumentType.LAND_TITLE,
            document_number="TF-IO-OK",
            description="Villa alignée",
            expertise_value=Decimal("5000000"),
            current_value=Decimal("5000000"),
            status=Guarantee.Status.ACTIVE,
        )

    api, headers = _auth(user, tenant_a)
    res = api.get(f"/api/v1/guarantees/{g.id}/", **headers)
    assert res.status_code == 200, res.content
    data = res.json()
    assert data["client"] == str(client_a.id)
    assert data["application"] == str(app.id)
    assert data["guarantee_type"] == "MORTGAGE"


def test_tenant_header_isolates_client_retrieve(tenant_a, tenant_b, client_a):
    user = User.objects.create_user(
        username="io_grp",
        password="x",
        is_group_level=True,
        is_staff=True,
        is_superuser=True,
    )
    api, headers_b = _auth(user, tenant_b)
    res = api.get(f"/api/v1/clients/{client_a.id}/", **headers_b)
    assert res.status_code in (403, 404)


def test_agency_scope_without_agency_hides_credit_and_loan_lists(
    tenant_a, product_a, client_a
):
    """Un staff périmètre agence, sans agence, ne voit aucune ligne (pas d'erreur)."""
    scoped = User.objects.create_user(
        username="io_agency",
        password="x",
        tenant=tenant_a,
        is_staff=True,
        is_superuser=True,
        data_scope=DataScope.AGENCY,
    )
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a, ref="DOS-IO-AG", user=scoped)
        Loan.objects.create(
            tenant=tenant_a,
            application=app,
            principal=Decimal("1000000"),
            interest_rate=Decimal("10"),
            duration_months=12,
            disbursed_at=date.today(),
            first_due_date=date.today(),
            status=Loan.Status.ACTIVE,
        )
    api, headers = _auth(scoped, tenant_a)
    credits = api.get("/api/v1/credit-applications/", **headers)
    loans = api.get("/api/v1/loans/", **headers)
    assert credits.status_code == 200, credits.content
    assert loans.status_code == 200, loans.content
    assert credits.json()["count"] == 0
    assert loans.json()["count"] == 0


def test_error_envelope_on_invalid_application_create(tenant_a, client_a):
    user = _staff(tenant_a, "io_err")
    api, headers = _auth(user, tenant_a)
    res = api.post(
        "/api/v1/credit-applications/",
        {"client": str(client_a.id), "amount_requested": "1000"},
        format="json",
        **headers,
    )
    assert res.status_code == 400, res.content
    body = res.json()
    assert set(body) >= {"success", "status_code", "errors"}
    assert body["success"] is False
    assert isinstance(body["errors"], dict)


def test_submit_workflow_amount_uses_reference_amount(
    tenant_a, product_a, client_a
):
    from django.contrib.auth.models import Group

    role = Group.objects.create(name="IO C1")
    submitter = User.objects.create_user(
        username="io_c1_sub", password="x", tenant=tenant_a
    )
    with tenant_context(tenant_a.id):
        definition = WorkflowDefinition.objects.create(
            tenant=tenant_a, code="WF-C1", version=1, is_active=True
        )
        ApprovalStep.objects.create(
            tenant=tenant_a,
            definition=definition,
            name="Comité",
            order=1,
            required_group=role,
            sla_hours=24,
            step_kind=ApprovalStep.StepKind.DECISIONAL,
        )
        app = _app(
            tenant_a,
            client_a,
            product_a,
            ref="DOS-C1",
            amount="8000000",
            proposed="3000000",
            user=submitter,
        )
        FinancialAnalysis.objects.create(
            tenant=tenant_a,
            application=app,
            is_reference=True,
            recommendation=FinancialAnalysis.Recommendation.FAVORABLE,
            salary_income=Decimal("300000"),
            client_type=client_a.client_type,
        )
        submit_application(app, submitter)
        instance = WorkflowInstance.objects.get(object_id=app.id)
        assert instance.amount == Decimal("3000000")


def test_approve_without_proposed_amount_syncs_instance_from_dossier(
    tenant_a, product_a, client_a
):
    from django.contrib.auth.models import Group

    from apps.workflow.services import process_decision

    role = Group.objects.create(name="IO C2")
    validator = User.objects.create_user(
        username="io_c2_val", password="x", tenant=tenant_a
    )
    validator.groups.add(role)
    submitter = User.objects.create_user(
        username="io_c2_sub", password="x", tenant=tenant_a
    )
    with tenant_context(tenant_a.id):
        definition = WorkflowDefinition.objects.create(
            tenant=tenant_a, code="WF-C2", version=1, is_active=True
        )
        ApprovalStep.objects.create(
            tenant=tenant_a,
            definition=definition,
            name="Comité",
            order=1,
            required_group=role,
            sla_hours=24,
            step_kind=ApprovalStep.StepKind.DECISIONAL,
        )
        app = _app(
            tenant_a,
            client_a,
            product_a,
            ref="DOS-C2",
            amount="8000000",
            proposed="2500000",
            user=submitter,
        )
        FinancialAnalysis.objects.create(
            tenant=tenant_a,
            application=app,
            is_reference=True,
            recommendation=FinancialAnalysis.Recommendation.FAVORABLE,
            salary_income=Decimal("300000"),
            client_type=client_a.client_type,
        )
        submit_application(app, submitter)
        instance = WorkflowInstance.objects.get(object_id=app.id)
        instance.amount = Decimal("8000000")
        instance.save(update_fields=["amount", "updated_at"])
        task = ApprovalTask.objects.get(instance=instance)
        process_decision(
            task,
            validator,
            ApprovalTask.Status.APPROVED,
            opinion=ApprovalTask.Opinion.FAVORABLE,
        )
        instance.refresh_from_db()
        assert instance.amount == Decimal("2500000")


def test_must_change_password_blocks_credit_applications(tenant_a):
    user = User.objects.create_user(
        username="io_pwd",
        password="x",
        tenant=tenant_a,
        is_staff=True,
        is_superuser=True,
        data_scope=DataScope.TENANT,
        must_change_password=True,
    )
    api, headers = _auth(user, tenant_a)
    res = api.get("/api/v1/credit-applications/", **headers)
    assert res.status_code == 403, res.content


def test_group_user_tranche_replace_uses_x_tenant_id(tenant_a):
    group = User.objects.create_user(
        username="io_grp_tr",
        password="x",
        is_group_level=True,
        is_staff=True,
        is_superuser=True,
    )
    api, headers = _auth(group, tenant_a)
    listing = api.get("/api/v1/collection-tranches/", **headers)
    assert listing.status_code == 200, listing.content
    res = api.post(
        "/api/v1/collection-tranches/replace/",
        {
            "tranches": [
                {
                    "name": "Gestionnaire",
                    "min_days_overdue": 1,
                    "max_days_overdue": None,
                    "owner_kind": "GESTIONNAIRE",
                }
            ]
        },
        format="json",
        **headers,
    )
    assert res.status_code == 200, res.content
    assert len(res.json()) >= 1


def test_delete_guarantee_blocked_when_busy(tenant_a, product_a, client_a):
    user = _staff(tenant_a, "io_delg")
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a, ref="DOS-IO-DEL")
        g = Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            application=app,
            guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
            document_type=DocumentType.LAND_TITLE,
            document_number="TF-DEL",
            description="Villa busy",
            expertise_value=Decimal("5000000"),
            current_value=Decimal("5000000"),
            status=Guarantee.Status.ACTIVE,
        )
        from apps.guarantees.formalization_services import (
            initiate_formalization_request,
        )

        initiate_formalization_request(guarantee=g, user=user, as_draft=True)

    api, headers = _auth(user, tenant_a)
    res = api.delete(f"/api/v1/guarantees/{g.id}/", **headers)
    assert res.status_code == 400, res.content
    blob = str(res.json()).lower()
    assert "formalisation" in blob or "busy" in blob or "processus" in blob


def test_patch_dation_and_formalization_not_allowed(
    tenant_a, product_a, client_a
):
    from unittest.mock import patch

    from apps.guarantees.formalization_services import (
        initiate_formalization_request,
    )
    from apps.guarantees.process_services import initiate_dation_request

    user = _staff(tenant_a, "io_patch")
    with tenant_context(tenant_a.id):
        client_a.cbs_client_id = "CBS-IO-PATCH"
        client_a.save(update_fields=["cbs_client_id"])
        app = _app(tenant_a, client_a, product_a, ref="DOS-IO-PT")
        g_form = Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            application=app,
            guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
            document_type=DocumentType.LAND_TITLE,
            document_number="TF-PT-F",
            description="Villa form",
            expertise_value=Decimal("5000000"),
            current_value=Decimal("5000000"),
            status=Guarantee.Status.ACTIVE,
        )
        g_dat = Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            application=app,
            guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
            document_type=DocumentType.LAND_TITLE,
            document_number="TF-PT-D",
            description="Villa dation",
            expertise_value=Decimal("4000000"),
            current_value=Decimal("4000000"),
            status=Guarantee.Status.ACTIVE,
        )
        form = initiate_formalization_request(
            guarantee=g_form, user=user, as_draft=True
        )
        with patch(
            "apps.guarantees.process_services.assert_client_outstanding_for_dation",
            return_value={
                "total_outstanding": Decimal("100000"),
                "currency": "XOF",
                "breakdown": [],
                "raw": {},
                "log_id": "x",
            },
        ):
            dation = initiate_dation_request(
                client=client_a,
                user=user,
                guarantee_ids=[str(g_dat.id)],
                as_draft=True,
            )

    api, headers = _auth(user, tenant_a)
    form_res = api.patch(
        f"/api/v1/guarantee-formalizations/{form.id}/",
        {"comment": "bypass"},
        format="json",
        **headers,
    )
    dat_res = api.patch(
        f"/api/v1/dation-requests/{dation.id}/",
        {"comment": "bypass"},
        format="json",
        **headers,
    )
    assert form_res.status_code == 405, form_res.content
    assert dat_res.status_code == 405, dat_res.content


def test_write_off_clears_overdue_and_par(tenant_a, product_a, client_a):
    from apps.collections.models import WriteOff
    from apps.collections.services import _execute_write_off

    user = _staff(tenant_a, "io_wo")
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a, ref="DOS-IO-WO")
        loan = Loan.objects.create(
            tenant=tenant_a,
            application=app,
            principal=Decimal("1000000"),
            interest_rate=Decimal("10"),
            duration_months=12,
            disbursed_at=date.today(),
            first_due_date=date.today(),
            status=Loan.Status.ACTIVE,
        )
        case = CollectionCase.objects.create(
            tenant=tenant_a,
            loan=loan,
            days_overdue=120,
            overdue_amount=Decimal("800000"),
            par_class=CollectionCase.ParClass.PAR90,
            stage=CollectionCase.Stage.LITIGATION,
        )
        record = WriteOff.objects.create(
            tenant=tenant_a,
            case=case,
            loan=loan,
            amount=Decimal("800000"),
            write_off_date=date.today(),
            reason="Perte test I/O",
            requested_by=user,
        )
        _execute_write_off(case, loan, record, user=user)
        case.refresh_from_db()
        loan.refresh_from_db()
        assert loan.status == Loan.Status.DEFAULTED
        assert case.days_overdue == 0
        assert case.overdue_amount == 0
        assert case.par_class == CollectionCase.ParClass.HEALTHY
        assert case.stage == CollectionCase.Stage.CLOSED


def test_patch_application_refreshes_reference_analysis(
    tenant_a, product_a, client_a
):
    user = _staff(tenant_a, "io_c3")
    with tenant_context(tenant_a.id):
        app = _app(
            tenant_a, client_a, product_a, ref="DOS-C3", amount="500000", user=user
        )
        analysis = FinancialAnalysis.objects.create(
            tenant=tenant_a,
            application=app,
            is_reference=True,
            recommendation=FinancialAnalysis.Recommendation.FAVORABLE,
            salary_income=Decimal("300000"),
            client_type=client_a.client_type,
        )
        before = analysis.new_installment
        assert before is not None

    api, headers = _auth(user, tenant_a)
    res = api.patch(
        f"/api/v1/credit-applications/{app.id}/",
        {"amount_requested": "2000000", "amount_proposed": "2000000"},
        format="json",
        **headers,
    )
    assert res.status_code == 200, res.content
    with tenant_context(tenant_a.id):
        analysis.refresh_from_db()
        assert analysis.new_installment is not None
        assert analysis.new_installment != before
        assert analysis.new_installment > before


def test_restructure_writeoff_scoped_to_visible_cases(
    tenant_a, product_a, client_a
):
    from django.contrib.auth.models import Permission

    from apps.accounts.services import (
        CHEF_AGENCE_ROLE_NAME,
        ensure_default_role_packs,
        get_or_create_tenant_role,
    )
    from apps.collections.services import propose_restructure, propose_write_off
    from apps.tenants.models import Agency

    ensure_default_role_packs(tenant_a)
    group, _ = get_or_create_tenant_role(tenant_a, CHEF_AGENCE_ROLE_NAME)
    chef = User.objects.create_user(
        username="io_chef_r1",
        password="x",
        tenant=tenant_a,
        is_staff=True,
        data_scope=DataScope.AGENCY,
    )
    chef.groups.add(group)
    for codename in (
        "view_loanrestructure",
        "change_loanrestructure",
        "view_writeoff",
        "change_writeoff",
        "view_collectioncase",
    ):
        perm = Permission.objects.filter(
            content_type__app_label="collections", codename=codename
        ).first()
        if perm:
            chef.user_permissions.add(perm)

    with tenant_context(tenant_a.id):
        ag_a = Agency.objects.create(tenant=tenant_a, code="IOA", name="Agence IO A")
        ag_b = Agency.objects.create(tenant=tenant_a, code="IOB", name="Agence IO B")
        chef.agency = ag_a
        chef.save(update_fields=["agency"])
        chef.agencies.add(ag_a)

        def _loan_case(ref, agency):
            app = _app(tenant_a, client_a, product_a, ref=ref)
            app.agency = agency
            app.status = CreditApplication.Status.DISBURSED
            app.save(update_fields=["agency", "status", "updated_at"])
            loan = Loan.objects.create(
                tenant=tenant_a,
                application=app,
                principal=Decimal("1000000"),
                interest_rate=Decimal("12"),
                duration_months=12,
                disbursed_at=date.today(),
                first_due_date=date.today(),
                status=Loan.Status.ACTIVE,
            )
            Installment.objects.create(
                tenant=tenant_a,
                loan=loan,
                number=1,
                due_date=date.today(),
                principal_due=Decimal("1000000"),
                interest_due=Decimal("0"),
                total_due=Decimal("1000000"),
                status=Installment.Status.OVERDUE,
            )
            case = CollectionCase.objects.create(
                tenant=tenant_a,
                loan=loan,
                days_overdue=40,
                overdue_amount=Decimal("200000"),
            )
            return loan, case

        loan_a, _ = _loan_case("DOS-R1-A", ag_a)
        loan_b, _ = _loan_case("DOS-R1-B", ag_b)
        loan_wo, case_wo = _loan_case("DOS-R1-WO", ag_b)
        mine = propose_restructure(
            loan_a, new_duration_months=18, reason="Agence A", user=chef
        )
        other = propose_restructure(
            loan_b, new_duration_months=18, reason="Agence B"
        )
        other_wo = propose_write_off(case_wo, reason="Perte B")

    api, headers = _auth(chef, tenant_a)
    listed = api.get("/api/v1/loan-restructures/", **headers)
    assert listed.status_code == 200, listed.content
    ids = {row["id"] for row in listed.json()["results"]}
    assert str(mine.id) in ids
    assert str(other.id) not in ids

    hidden = api.get(f"/api/v1/loan-restructures/{other.id}/", **headers)
    assert hidden.status_code == 404, hidden.content
    approve = api.post(
        f"/api/v1/loan-restructures/{other.id}/approve/",
        {"comment": "hors périmètre"},
        format="json",
        **headers,
    )
    assert approve.status_code == 404, approve.content

    wo = api.get(f"/api/v1/write-offs/{other_wo.id}/", **headers)
    assert wo.status_code == 404, wo.content
    wo_approve = api.post(
        f"/api/v1/write-offs/{other_wo.id}/approve/",
        {"comment": "hors périmètre"},
        format="json",
        **headers,
    )
    assert wo_approve.status_code == 404, wo_approve.content
