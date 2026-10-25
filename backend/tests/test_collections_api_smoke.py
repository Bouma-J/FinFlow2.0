"""Smoke tests API — recouvrement P2/P3 + contentieux v2."""
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.collections.models import (
    CollectionCase,
    LegalParty,
    LitigationFile,
)
from apps.collections.services import (
    apply_restructure,
    ensure_litigation_document_categories,
    refresh_loan_overdue,
    write_off_case,
)
from apps.common.tenancy import tenant_context
from apps.credits.models import CreditApplication, Installment, Loan
from apps.documents.models import Document

User = get_user_model()


@pytest.fixture
def api_user(tenant_a):
    # Groupe + en-tête X-Tenant-Id : périmètre filiale sans filtre agence.
    return User.objects.create_user(
        username="reco_agent",
        password="test-pass-123",
        email="reco@example.com",
        tenant=None,
        is_group_level=True,
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def api(api_user, tenant_a):
    client = APIClient()
    client.force_authenticate(user=api_user)
    client.credentials(HTTP_X_TENANT_ID=str(tenant_a.id))
    return client


def _loan_case(tenant, product, client_obj, *, days=40, principal="20000", ref="REF-API"):
    app = CreditApplication.objects.create(
        tenant=tenant,
        client=client_obj,
        product=product,
        amount_requested=Decimal(principal),
        duration_months=6,
        risk_level=1,
        reference=ref,
        status=CreditApplication.Status.APPROVED,
    )
    loan = Loan.objects.create(
        tenant=tenant,
        application=app,
        principal=Decimal(principal),
        interest_rate=Decimal("12"),
        duration_months=6,
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
    case = refresh_loan_overdue(
        loan,
        cbs_status={
            "settled": False,
            "days_overdue": days,
            "overdue_amount": Decimal(principal),
        },
    )
    return loan, case


def test_api_collection_case_list_and_detail(api, tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        _, case = _loan_case(tenant_a, product_a, client_a, ref="REF-API-LIST")
    r = api.get("/api/v1/collection-cases/", {"open": 1})
    assert r.status_code == 200, r.content
    assert r.data["count"] >= 1

    r = api.get(f"/api/v1/collection-cases/{case.id}/")
    assert r.status_code == 200
    assert "installments" in r.data
    assert "outstanding_principal" in r.data
    assert "litigations" in r.data


def test_api_agent_dashboard_and_hearings(api, api_user, tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        _, case = _loan_case(tenant_a, product_a, client_a, ref="REF-API-DASH")
        case.assigned_to = api_user
        case.next_action_date = timezone.localdate()
        case.next_action_type = "VISIT"
        case.save()
        firm = LegalParty.objects.create(
            tenant=tenant_a,
            party_type=LegalParty.PartyType.LAW_FIRM,
            name="Cabinet API",
        )
        LitigationFile.objects.create(
            tenant=tenant_a,
            case=case,
            title="Audience API",
            hearing_date=timezone.localdate() + timedelta(days=3),
            status=LitigationFile.Status.IN_PROGRESS,
            law_firm=firm,
        )

    r = api.get("/api/v1/collection-cases/agent-dashboard/")
    assert r.status_code == 200
    assert "assigned_open" in r.data
    assert "followups_due" in r.data

    r = api.get("/api/v1/collection-cases/hearings-agenda/", {"within_days": 30})
    assert r.status_code == 200
    assert isinstance(r.data, list)
    assert any(row["title"] == "Audience API" for row in r.data)


def test_api_repayment_and_set_next_action(api, tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        _, case = _loan_case(
            tenant_a, product_a, client_a, principal="10000", ref="REF-API-PAY"
        )

    r = api.post(
        f"/api/v1/collection-cases/{case.id}/repayments/",
        {"amount": "4000", "payment_date": str(date.today()), "reference": "ENC-T"},
        format="json",
    )
    assert r.status_code == 400, r.content
    assert "CBS" in r.json()["errors"]["detail"]

    r = api.post(
        f"/api/v1/collection-cases/{case.id}/set-next-action/",
        {
            "next_action_date": str(date.today() + timedelta(days=2)),
            "next_action_type": "CALL",
            "next_action_note": "Relance test",
        },
        format="json",
    )
    assert r.status_code == 200
    assert r.data["next_action_type"] == "CALL"


def test_api_litigation_event_refuses_without_open_file(
    api, tenant_a, product_a, client_a
):
    with tenant_context(tenant_a.id):
        _, case = _loan_case(tenant_a, product_a, client_a, ref="REF-API-NO-LIT")

    r = api.post(
        f"/api/v1/collection-cases/{case.id}/litigation-events/",
        {
            "event_type": "HEARING",
            "event_date": (timezone.localdate() + timedelta(days=5)).isoformat(),
        },
        format="json",
    )
    assert r.status_code == 400, r.content
    assert case.litigations.count() == 0


def test_api_legal_party_and_litigation_flow(api, tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        _, case = _loan_case(tenant_a, product_a, client_a, ref="REF-API-LIT")

    r = api.post(
        "/api/v1/legal-parties/",
        {
            "party_type": "LAW_FIRM",
            "name": "Cabinet Smoke",
            "phone": "+22501010101",
            "email": "smoke@cabinet.ci",
            "is_active": True,
        },
        format="json",
    )
    assert r.status_code == 201, r.content
    firm_id = r.data["id"]

    r = api.post(
        "/api/v1/litigations/",
        {
            "case": str(case.id),
            "title": "Procédure smoke",
            "action_type": "SUMMONS",
            "court_name": "TGI Test",
            "case_reference": "RG-SMOKE",
            "law_firm": firm_id,
            "status": "FILED",
            "claimed_principal": "20000",
        },
        format="json",
    )
    assert r.status_code == 201, r.content
    lit_id = r.data["id"]
    assert r.data["law_firm_detail"]["name"] == "Cabinet Smoke"

    hearing = (timezone.localdate() + timedelta(days=10)).isoformat()
    r = api.post(
        f"/api/v1/litigations/{lit_id}/events/",
        {
            "event_type": "HEARING",
            "event_date": hearing,
            "event_time": "09:30:00",
            "location": "Salle 1",
            "comment": "Audience introductive",
        },
        format="json",
    )
    assert r.status_code == 201, r.content

    r = api.get(f"/api/v1/litigations/{lit_id}/")
    assert r.status_code == 200
    assert r.data["hearing_date"] == hearing
    assert r.data["hearing_location"] == "Salle 1"

    r = api.post(
        f"/api/v1/litigations/{lit_id}/costs/",
        {
            "cost_type": "FEE",
            "label": "Provision",
            "amount": "150000",
            "cost_date": str(date.today()),
            "is_paid": False,
            "recoverable": True,
            "party": firm_id,
        },
        format="json",
    )
    assert r.status_code == 201, r.content

    r = api.post(
        f"/api/v1/litigations/{lit_id}/seizures/",
        {
            "seizure_type": "ATTRIBUTION",
            "status": "PLANNED",
            "seizure_date": str(date.today() + timedelta(days=20)),
            "amount": "20000",
            "report_reference": "PV-SMOKE",
        },
        format="json",
    )
    assert r.status_code == 201, r.content

    # GED
    with tenant_context(tenant_a.id):
        ensure_litigation_document_categories(tenant_a)
    upload = SimpleUploadedFile(
        "assignation.pdf",
        b"%PDF-1.4 smoke test",
        content_type="application/pdf",
    )
    r = api.post(
        f"/api/v1/litigations/{lit_id}/documents/",
        {"file": upload, "name": "Assignation", "category": "LIT_ASSIGNATION"},
        format="multipart",
    )
    assert r.status_code == 201, r.content
    with tenant_context(tenant_a.id):
        assert Document.objects.filter(name="Assignation").exists()

    r = api.get(f"/api/v1/litigations/{lit_id}/documents/")
    assert r.status_code == 200
    assert len(r.data) >= 1

    r = api.get(f"/api/v1/collection-cases/{case.id}/")
    assert r.status_code == 200
    assert r.data["stage"] == CollectionCase.Stage.LITIGATION
    assert len(r.data["litigations"]) >= 1


def test_api_export_csv(api, tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        _loan_case(tenant_a, product_a, client_a, ref="REF-API-CSV")

    r = api.get("/api/v1/collection-cases/export/", {"open": 1})
    assert r.status_code == 200
    assert "text/csv" in r["Content-Type"]
    body = r.content.decode("utf-8-sig")
    assert "reference" in body
    assert "REF-API-CSV" in body


def test_service_restructure_then_second_litigation(tenant_a, product_a, client_a):
    """Parcours métier : retard → restructuration → nouvelle procédure si besoin."""
    with tenant_context(tenant_a.id):
        loan, case = _loan_case(
            tenant_a, product_a, client_a, days=45, principal="12000", ref="REF-FLOW"
        )
        assert case.days_overdue >= 31
        apply_restructure(case, new_duration_months=4, reason="Test smoke")
        loan.refresh_from_db()
        assert loan.status == Loan.Status.ACTIVE
        assert loan.duration_months == 6
        case.refresh_from_db()
        assert case.restructures.filter(status="PENDING").exists()
        assert case.days_overdue >= 31

        # Réouverture contentieuse possible (2e procédure)
        lit1 = LitigationFile.objects.create(
            tenant=tenant_a,
            case=case,
            title="Ancienne",
            status=LitigationFile.Status.CLOSED,
        )
        lit2 = LitigationFile.objects.create(
            tenant=tenant_a,
            case=case,
            title="Appel",
            status=LitigationFile.Status.APPEAL,
            action_type=LitigationFile.ActionType.APPEAL,
        )
        assert case.litigations.count() == 2
        assert lit1.id != lit2.id


def test_service_write_off_stops_active_loan(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        loan, case = _loan_case(
            tenant_a, product_a, client_a, days=120, principal="8000", ref="REF-WO-API"
        )
        write_off_case(case, reason="Smoke write-off")
        loan.refresh_from_db()
        case.refresh_from_db()
        assert loan.status == Loan.Status.DEFAULTED
        assert case.stage == CollectionCase.Stage.CLOSED
        # Un nouvel encaissement n'est pas le focus ; le prêt n'est plus ACTIVE
        with pytest.raises(ValueError):
            write_off_case(case, reason="déjà fait")
