"""Tests Contentieux v2 — intervenants, procédures, audiences, frais, saisies."""
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.collections.models import (
    CollectionCase,
    LegalParty,
    LitigationCost,
    LitigationEvent,
    LitigationFile,
    LitigationSeizure,
)
from apps.collections.services import (
    create_litigation,
    upcoming_hearings,
)
from apps.common.tenancy import tenant_context
from apps.credits.models import CreditApplication, Installment, Loan


def _overdue_case(tenant, product, client, *, ref="REF-LIT-V2"):
    app = CreditApplication.objects.create(
        tenant=tenant,
        client=client,
        product=product,
        amount_requested=Decimal("15000"),
        duration_months=6,
        risk_level=1,
        reference=ref,
        status=CreditApplication.Status.APPROVED,
    )
    loan = Loan.objects.create(
        tenant=tenant,
        application=app,
        principal=Decimal("15000"),
        interest_rate=Decimal("12"),
        duration_months=6,
        disbursed_at=date.today() - timedelta(days=50),
        first_due_date=date.today() - timedelta(days=40),
        status=Loan.Status.ACTIVE,
    )
    Installment.objects.create(
        tenant=tenant,
        loan=loan,
        number=1,
        due_date=date.today() - timedelta(days=40),
        principal_due=Decimal("15000"),
        interest_due=Decimal("0"),
        total_due=Decimal("15000"),
        status=Installment.Status.OVERDUE,
    )
    return CollectionCase.objects.create(
        tenant=tenant,
        loan=loan,
        days_overdue=40,
        overdue_amount=Decimal("15000"),
        par_class=CollectionCase.ParClass.PAR30,
        stage=CollectionCase.Stage.PRECONTENTIOUS,
    )


def test_create_legal_party(tenant_a):
    with tenant_context(tenant_a.id):
        firm = LegalParty.objects.create(
            tenant=tenant_a,
            party_type=LegalParty.PartyType.LAW_FIRM,
            name="Cabinet Koné & Associés",
            email="contact@kone.ci",
            phone="+22507000000",
        )
        assert firm.pk
        assert firm.is_active is True
        assert firm.get_party_type_display() == "Cabinet d'avocats"


def test_create_litigation_with_firm(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        case = _overdue_case(tenant_a, product_a, client_a, ref="REF-LIT-FIRM")
        firm = LegalParty.objects.create(
            tenant=tenant_a,
            party_type=LegalParty.PartyType.LAW_FIRM,
            name="Cabinet Diarra",
        )
        lit = create_litigation(
            case,
            data={
                "title": "Injonction de payer",
                "court_name": "TGI Abidjan",
                "case_reference": "RG-2026-01",
                "law_firm": firm,
                "action_type": LitigationFile.ActionType.PAYMENT_ORDER,
                "status": LitigationFile.Status.FILED,
            },
        )
        assert lit.law_firm_id == firm.id
        assert lit.case_id == case.id
        case.refresh_from_db()
        assert case.stage == CollectionCase.Stage.LITIGATION
        assert case.litigations.count() == 1


def test_hearing_event_updates_hearing_date(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        case = _overdue_case(tenant_a, product_a, client_a, ref="REF-LIT-HEAR")
        lit = create_litigation(
            case,
            data={"title": "Assignation", "court_name": "Tribunal de commerce"},
        )
        hearing = timezone.localdate() + timedelta(days=14)
        event = LitigationEvent.objects.create(
            tenant=tenant_a,
            litigation=lit,
            event_date=hearing,
            event_type=LitigationEvent.EventType.HEARING,
            location="Salle A",
            comment="Première audience",
        )
        lit.recompute_next_hearing()
        lit.refresh_from_db()
        assert event.pk
        assert lit.hearing_date == hearing
        assert lit.hearing_location == "Salle A"


def test_add_litigation_cost(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        case = _overdue_case(tenant_a, product_a, client_a, ref="REF-LIT-COST")
        firm = LegalParty.objects.create(
            tenant=tenant_a,
            party_type=LegalParty.PartyType.LAW_FIRM,
            name="Cabinet Fees",
        )
        lit = create_litigation(case, data={"title": "Frais", "law_firm": firm})
        cost = LitigationCost.objects.create(
            tenant=tenant_a,
            litigation=lit,
            cost_type=LitigationCost.CostType.FEE,
            label="Provision honoraires",
            amount=Decimal("250000"),
            cost_date=timezone.localdate(),
            party=firm,
            is_paid=False,
            recoverable=True,
        )
        assert cost.pk
        assert lit.costs.count() == 1
        assert lit.costs.first().amount == Decimal("250000")


def test_add_litigation_seizure(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        case = _overdue_case(tenant_a, product_a, client_a, ref="REF-LIT-SEIZ")
        bailiff = LegalParty.objects.create(
            tenant=tenant_a,
            party_type=LegalParty.PartyType.BAILIFF,
            name="Étude Huissier Touré",
        )
        lit = create_litigation(
            case,
            data={
                "title": "Exécution",
                "status": LitigationFile.Status.ENFORCEMENT,
                "bailiff_party": bailiff,
            },
        )
        seizure = LitigationSeizure.objects.create(
            tenant=tenant_a,
            litigation=lit,
            seizure_type=LitigationSeizure.SeizureType.ATTRIBUTION,
            status=LitigationSeizure.Status.PLANNED,
            seizure_date=timezone.localdate() + timedelta(days=7),
            amount=Decimal("15000"),
            bailiff=bailiff,
            report_reference="PV-001",
        )
        assert seizure.pk
        assert lit.seizures.count() == 1
        assert seizure.bailiff_id == bailiff.id


def test_upcoming_hearings(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        case = _overdue_case(tenant_a, product_a, client_a, ref="REF-LIT-AGENDA")
        firm = LegalParty.objects.create(
            tenant=tenant_a,
            party_type=LegalParty.PartyType.LAW_FIRM,
            name="Cabinet Agenda",
        )
        hearing = timezone.localdate() + timedelta(days=5)
        lit = create_litigation(
            case,
            data={
                "title": "Audience prochaine",
                "case_reference": "RG-AGENDA",
                "law_firm": firm,
                "hearing_date": hearing,
                "hearing_location": "Chambre civile",
                "status": LitigationFile.Status.IN_PROGRESS,
            },
        )
        # Hors fenêtre
        create_litigation(
            case,
            data={
                "title": "Loin",
                "hearing_date": timezone.localdate() + timedelta(days=90),
                "status": LitigationFile.Status.IN_PROGRESS,
            },
        )
        rows = upcoming_hearings(tenant_id=tenant_a.id, within_days=30)
        ids = {row["id"] for row in rows}
        assert str(lit.id) in ids
        match = next(r for r in rows if r["id"] == str(lit.id))
        assert match["hearing_date"] == hearing.isoformat()
        assert match["law_firm_name"] == "Cabinet Agenda"
        assert match["client_name"]
