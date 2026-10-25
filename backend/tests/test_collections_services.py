"""Tests du moteur de recouvrement (impayés CBS / PAR)."""
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.collections.models import (
    CollectionCase,
    CollectionEscalationRule,
    CollectionStageHistory,
    LitigationFile,
    PaymentPromise,
)
from apps.collections.services import (
    apply_restructure,
    ensure_default_escalation_rules,
    outstanding_principal,
    refresh_broken_promises,
    refresh_loan_overdue,
    send_collection_reminder,
    set_next_action,
    upsert_litigation,
    write_off_case,
)
from apps.common.tenancy import tenant_context
from apps.credits.models import CreditApplication, Installment, Loan
from apps.notifications.models import NotificationLog, TenantNotificationSettings


def _cbs(days, amount="0", *, settled=False):
    return {
        "settled": settled,
        "days_overdue": 0 if settled else days,
        "overdue_amount": Decimal("0") if settled else Decimal(str(amount)),
    }


def test_cbs_overdue_decrease_then_settle(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            client=client_a,
            product=product_a,
            amount_requested=Decimal("100000"),
            duration_months=2,
            risk_level=1,
            reference="REF-COL-1",
            status=CreditApplication.Status.APPROVED,
        )
        loan = Loan.objects.create(
            tenant=tenant_a,
            application=app,
            principal=Decimal("100000"),
            interest_rate=Decimal("12"),
            duration_months=2,
            disbursed_at=date.today() - timedelta(days=60),
            first_due_date=date.today() - timedelta(days=40),
            status=Loan.Status.ACTIVE,
        )
        Installment.objects.create(
            tenant=tenant_a,
            loan=loan,
            number=1,
            due_date=date.today() - timedelta(days=40),
            principal_due=Decimal("50000"),
            interest_due=Decimal("1000"),
            total_due=Decimal("51000"),
            amount_paid=Decimal("0"),
            status=Installment.Status.OVERDUE,
        )
        Installment.objects.create(
            tenant=tenant_a,
            loan=loan,
            number=2,
            due_date=date.today() - timedelta(days=10),
            principal_due=Decimal("50000"),
            interest_due=Decimal("500"),
            total_due=Decimal("50500"),
            amount_paid=Decimal("0"),
            status=Installment.Status.OVERDUE,
        )

        case = refresh_loan_overdue(loan, cbs_status=_cbs(40, "101500"))
        assert case is not None
        assert case.days_overdue == 40
        assert case.overdue_amount == Decimal("101500")

        case = refresh_loan_overdue(loan, cbs_status=_cbs(10, "50500"))
        assert case.days_overdue == 10
        assert case.overdue_amount == Decimal("50500")

        case2 = refresh_loan_overdue(loan, cbs_status=_cbs(0, settled=True))
        loan.refresh_from_db()
        assert loan.status == Loan.Status.CLOSED
        case2.refresh_from_db()
        assert case2.stage == CollectionCase.Stage.CLOSED
        assert case2.days_overdue == 0


def test_promise_kept_when_cbs_settles(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            client=client_a,
            product=product_a,
            amount_requested=Decimal("10000"),
            duration_months=1,
            risk_level=1,
            reference="REF-COL-2",
            status=CreditApplication.Status.APPROVED,
        )
        loan = Loan.objects.create(
            tenant=tenant_a,
            application=app,
            principal=Decimal("10000"),
            interest_rate=Decimal("10"),
            duration_months=1,
            disbursed_at=date.today() - timedelta(days=40),
            first_due_date=date.today() - timedelta(days=20),
            status=Loan.Status.ACTIVE,
        )
        Installment.objects.create(
            tenant=tenant_a,
            loan=loan,
            number=1,
            due_date=date.today() - timedelta(days=20),
            principal_due=Decimal("10000"),
            interest_due=Decimal("0"),
            total_due=Decimal("10000"),
            status=Installment.Status.OVERDUE,
        )
        case = CollectionCase.objects.create(
            tenant=tenant_a,
            loan=loan,
            days_overdue=20,
            overdue_amount=Decimal("10000"),
            par_class=CollectionCase.ParClass.PAR1,
        )
        promise = PaymentPromise.objects.create(
            tenant=tenant_a,
            case=case,
            amount=Decimal("10000"),
            promised_date=timezone.localdate(),
            status=PaymentPromise.Status.PENDING,
        )
        refresh_loan_overdue(loan, cbs_status=_cbs(0, settled=True))
        promise.refresh_from_db()
        assert promise.status == PaymentPromise.Status.KEPT


def test_escalation_to_precontentious_and_history(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        ensure_default_escalation_rules(tenant_a)
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            client=client_a,
            product=product_a,
            amount_requested=Decimal("20000"),
            duration_months=1,
            risk_level=1,
            reference="REF-COL-ESC",
            status=CreditApplication.Status.APPROVED,
        )
        loan = Loan.objects.create(
            tenant=tenant_a,
            application=app,
            principal=Decimal("20000"),
            interest_rate=Decimal("10"),
            duration_months=1,
            disbursed_at=date.today() - timedelta(days=50),
            first_due_date=date.today() - timedelta(days=40),
            status=Loan.Status.ACTIVE,
        )
        Installment.objects.create(
            tenant=tenant_a,
            loan=loan,
            number=1,
            due_date=date.today() - timedelta(days=40),
            principal_due=Decimal("20000"),
            interest_due=Decimal("0"),
            total_due=Decimal("20000"),
            status=Installment.Status.OVERDUE,
        )
        case = refresh_loan_overdue(loan, cbs_status=_cbs(40, "20000"))
        assert case is not None
        assert case.days_overdue >= 31
        assert case.stage == CollectionCase.Stage.PRECONTENTIOUS
        assert CollectionStageHistory.objects.filter(
            case=case, to_stage=CollectionCase.Stage.PRECONTENTIOUS
        ).exists()


def test_escalation_rule_can_raise_stage_before_tranche(
    tenant_a, product_a, client_a,
):
    from apps.collections.services import ensure_default_tranches

    with tenant_context(tenant_a.id):
        ensure_default_tranches(tenant_a)
        CollectionEscalationRule.objects.all().delete()
        CollectionEscalationRule.objects.create(
            tenant=tenant_a,
            min_days_overdue=10,
            target_stage=CollectionCase.Stage.PRECONTENTIOUS,
            is_active=True,
            label="Précontentieux anticipé",
        )
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            client=client_a,
            product=product_a,
            amount_requested=Decimal("8000"),
            duration_months=1,
            risk_level=1,
            reference="REF-COL-EARLY",
            status=CreditApplication.Status.APPROVED,
        )
        loan = Loan.objects.create(
            tenant=tenant_a,
            application=app,
            principal=Decimal("8000"),
            interest_rate=Decimal("10"),
            duration_months=1,
            disbursed_at=date.today() - timedelta(days=25),
            first_due_date=date.today() - timedelta(days=15),
            status=Loan.Status.ACTIVE,
        )
        Installment.objects.create(
            tenant=tenant_a,
            loan=loan,
            number=1,
            due_date=date.today() - timedelta(days=15),
            principal_due=Decimal("8000"),
            interest_due=Decimal("0"),
            total_due=Decimal("8000"),
            status=Installment.Status.OVERDUE,
        )
        case = refresh_loan_overdue(loan, cbs_status=_cbs(15, "8000"))
        assert case is not None
        assert case.stage == CollectionCase.Stage.PRECONTENTIOUS


def test_escalation_only_upwards(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        CollectionEscalationRule.objects.create(
            tenant=tenant_a,
            min_days_overdue=10,
            target_stage=CollectionCase.Stage.AMICABLE,
            is_active=True,
        )
        CollectionEscalationRule.objects.create(
            tenant=tenant_a,
            min_days_overdue=31,
            target_stage=CollectionCase.Stage.PRECONTENTIOUS,
            is_active=True,
        )
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            client=client_a,
            product=product_a,
            amount_requested=Decimal("5000"),
            duration_months=1,
            risk_level=1,
            reference="REF-COL-UP",
            status=CreditApplication.Status.APPROVED,
        )
        loan = Loan.objects.create(
            tenant=tenant_a,
            application=app,
            principal=Decimal("5000"),
            interest_rate=Decimal("10"),
            duration_months=1,
            disbursed_at=date.today() - timedelta(days=20),
            first_due_date=date.today() - timedelta(days=15),
            status=Loan.Status.ACTIVE,
        )
        Installment.objects.create(
            tenant=tenant_a,
            loan=loan,
            number=1,
            due_date=date.today() - timedelta(days=15),
            principal_due=Decimal("5000"),
            interest_due=Decimal("0"),
            total_due=Decimal("5000"),
            status=Installment.Status.OVERDUE,
        )
        case = CollectionCase.objects.create(
            tenant=tenant_a,
            loan=loan,
            stage=CollectionCase.Stage.LITIGATION,
            days_overdue=15,
            overdue_amount=Decimal("5000"),
            par_class=CollectionCase.ParClass.PAR1,
        )
        refreshed = refresh_loan_overdue(loan, cbs_status=_cbs(15, "5000"))
        refreshed.refresh_from_db()
        assert refreshed.stage == CollectionCase.Stage.LITIGATION


def test_default_tranches_auto_transfer(tenant_a, product_a, client_a):
    from apps.collections.models import CollectionTranche
    from apps.collections.services import ensure_default_tranches

    with tenant_context(tenant_a.id):
        ensure_default_tranches(tenant_a)
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            client=client_a,
            product=product_a,
            amount_requested=Decimal("20000"),
            duration_months=1,
            risk_level=1,
            reference="REF-COL-TR",
            status=CreditApplication.Status.APPROVED,
        )
        loan = Loan.objects.create(
            tenant=tenant_a,
            application=app,
            principal=Decimal("20000"),
            interest_rate=Decimal("10"),
            duration_months=1,
            disbursed_at=date.today() - timedelta(days=50),
            first_due_date=date.today() - timedelta(days=40),
            status=Loan.Status.ACTIVE,
        )
        Installment.objects.create(
            tenant=tenant_a,
            loan=loan,
            number=1,
            due_date=date.today() - timedelta(days=40),
            principal_due=Decimal("20000"),
            interest_due=Decimal("0"),
            total_due=Decimal("20000"),
            status=Installment.Status.OVERDUE,
        )
        case = refresh_loan_overdue(loan, cbs_status=_cbs(40, "20000"))
        assert case is not None
        case.refresh_from_db()
        assert case.tranche is not None
        assert case.tranche.owner_kind == CollectionTranche.OwnerKind.COLLECTION
        assert case.stage == CollectionCase.Stage.PRECONTENTIOUS
        assert case.assigned_to_id is None


def test_refresh_ignores_local_schedule_without_cbs(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            client=client_a,
            product=product_a,
            amount_requested=Decimal("8000"),
            duration_months=1,
            risk_level=1,
            reference="REF-NO-CBS",
            status=CreditApplication.Status.APPROVED,
        )
        loan = Loan.objects.create(
            tenant=tenant_a,
            application=app,
            principal=Decimal("8000"),
            interest_rate=Decimal("10"),
            duration_months=1,
            disbursed_at=date.today() - timedelta(days=50),
            first_due_date=date.today() - timedelta(days=40),
            status=Loan.Status.ACTIVE,
        )
        Installment.objects.create(
            tenant=tenant_a,
            loan=loan,
            number=1,
            due_date=date.today() - timedelta(days=40),
            principal_due=Decimal("8000"),
            interest_due=Decimal("0"),
            total_due=Decimal("8000"),
            status=Installment.Status.OVERDUE,
        )
        case = refresh_loan_overdue(loan)
        assert case is None
        assert not CollectionCase.objects.filter(loan=loan).exists()


def test_replace_tranches_rejects_gap(tenant_a):
    from rest_framework.exceptions import ValidationError

    from apps.collections.services import replace_collection_tranches

    with tenant_context(tenant_a.id):
        with pytest.raises(ValidationError):
            replace_collection_tranches(
                tenant=tenant_a,
                items=[
                    {
                        "name": "A",
                        "min_days_overdue": 1,
                        "max_days_overdue": 10,
                        "owner_kind": "GESTIONNAIRE",
                    },
                    {
                        "name": "B",
                        "min_days_overdue": 20,
                        "max_days_overdue": None,
                        "owner_kind": "LEGAL",
                    },
                ],
            )


def test_broken_promises_and_next_action(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            client=client_a,
            product=product_a,
            amount_requested=Decimal("8000"),
            duration_months=1,
            risk_level=1,
            reference="REF-COL-PR",
            status=CreditApplication.Status.APPROVED,
        )
        loan = Loan.objects.create(
            tenant=tenant_a,
            application=app,
            principal=Decimal("8000"),
            interest_rate=Decimal("10"),
            duration_months=1,
            disbursed_at=date.today() - timedelta(days=30),
            first_due_date=date.today() - timedelta(days=20),
            status=Loan.Status.ACTIVE,
        )
        case = CollectionCase.objects.create(
            tenant=tenant_a,
            loan=loan,
            days_overdue=20,
            overdue_amount=Decimal("8000"),
        )
        promise = PaymentPromise.objects.create(
            tenant=tenant_a,
            case=case,
            amount=Decimal("1000"),
            promised_date=timezone.localdate() - timedelta(days=2),
            status=PaymentPromise.Status.PENDING,
        )
        assert refresh_broken_promises() >= 1
        promise.refresh_from_db()
        assert promise.status == PaymentPromise.Status.BROKEN
        case.refresh_from_db()
        assert case.next_action_type == "CALL"
        assert "Promesse" in case.next_action_note

        set_next_action(
            case,
            action_date=timezone.localdate() + timedelta(days=3),
            action_type="VISIT",
            note="Visite terrain",
        )
        case.refresh_from_db()
        assert case.next_action_type == "VISIT"
        assert case.next_action_note == "Visite terrain"


def _overdue_loan(tenant, product, client, *, days=40, principal="10000", ref="REF"):
    app = CreditApplication.objects.create(
        tenant=tenant,
        client=client,
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
        loan, cbs_status=_cbs(days, principal)
    )
    return loan, case


def test_apply_restructure_rebuilds_schedule(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        loan, case = _overdue_loan(
            tenant_a, product_a, client_a, days=20, principal="12000", ref="REF-RST"
        )
        before = outstanding_principal(loan)
        assert before == Decimal("12000")
        record = apply_restructure(
            case,
            new_duration_months=3,
            new_rate=Decimal("10"),
            reason="Accord amiable",
        )
        assert record.outstanding_principal == Decimal("12000")
        assert record.status == "PENDING"
        loan.refresh_from_db()
        assert loan.duration_months == 6
        assert loan.interest_rate == Decimal("12")
        unpaid = loan.installments.exclude(status=Installment.Status.PAID)
        assert unpaid.count() == 1
        case.refresh_from_db()
        assert case.days_overdue == 20
        assert loan.status == Loan.Status.ACTIVE
        assert case.restructures.filter(status="PENDING").exists()


def test_write_off_defaults_loan(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        loan, case = _overdue_loan(
            tenant_a, product_a, client_a, days=100, principal="5000", ref="REF-WO"
        )
        wo = write_off_case(case, reason="Irrécouvrable")
        loan.refresh_from_db()
        case.refresh_from_db()
        assert wo.amount == Decimal("5000")
        assert loan.status == Loan.Status.DEFAULTED
        assert case.stage == CollectionCase.Stage.CLOSED


def test_litigation_upsert(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        _, case = _overdue_loan(
            tenant_a, product_a, client_a, days=100, principal="7000", ref="REF-LIT"
        )
        lit = upsert_litigation(
            case,
            data={
                "court_name": "TGI Bamako",
                "case_reference": "RG-1",
                "status": LitigationFile.Status.OPEN,
            },
        )
        assert lit.court_name == "TGI Bamako"
        case.refresh_from_db()
        assert case.stage == CollectionCase.Stage.LITIGATION


def test_reminder_email_skipped_without_client_email(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        prefs = TenantNotificationSettings.for_tenant(tenant_a)
        prefs.notify_collection_email = True
        prefs.enabled = True
        prefs.save()
        client_a.email = ""
        client_a.save(update_fields=["email"])
        _, case = _overdue_loan(
            tenant_a, product_a, client_a, days=15, principal="3000", ref="REF-REM"
        )
        result = send_collection_reminder(case, channel="EMAIL", force=True)
        assert result["status"] == "SKIPPED"
        assert NotificationLog.objects.filter(
            kind=NotificationLog.Kind.COLLECTION_REMINDER
        ).exists()


def test_reminder_sms_stub(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        client_a.phone = "+22370000000"
        client_a.save(update_fields=["phone"])
        _, case = _overdue_loan(
            tenant_a, product_a, client_a, days=15, principal="3000", ref="REF-SMS"
        )
        result = send_collection_reminder(case, channel="SMS", force=True)
        assert result["status"] == "SKIPPED"
        assert result["channel"] == "SMS"


def test_new_overdue_case_auto_assign_and_first_touch(tenant_a, product_a, client_a):
    from apps.accounts.models import User

    with tenant_context(tenant_a.id):
        officer = User.objects.create(username="col_officer", tenant=tenant_a)
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            client=client_a,
            product=product_a,
            amount_requested=Decimal("5000"),
            duration_months=3,
            risk_level=1,
            reference="REF-COL-ASSIGN",
            status=CreditApplication.Status.APPROVED,
            submitted_by=officer,
            created_by=officer,
        )
        loan = Loan.objects.create(
            tenant=tenant_a,
            application=app,
            principal=Decimal("5000"),
            interest_rate=Decimal("12"),
            duration_months=3,
            disbursed_at=date.today() - timedelta(days=20),
            first_due_date=date.today() - timedelta(days=10),
            status=Loan.Status.ACTIVE,
        )
        Installment.objects.create(
            tenant=tenant_a,
            loan=loan,
            number=1,
            due_date=date.today() - timedelta(days=10),
            principal_due=Decimal("5000"),
            interest_due=Decimal("0"),
            total_due=Decimal("5000"),
            status=Installment.Status.OVERDUE,
        )
        case = refresh_loan_overdue(loan, cbs_status=_cbs(10, "5000"))
        assert case is not None
        assert case.assigned_to_id == officer.id
        assert case.next_action_date is not None
        assert case.next_action_type == "CALL"
        assert "Premier contact" in case.next_action_note


def test_agent_dashboard_team_includes_unassigned(tenant_a, product_a, client_a):
    from apps.accounts.models import User
    from apps.collections.services import agent_dashboard

    with tenant_context(tenant_a.id):
        from apps.accounts.models import DataScope

        agent = User.objects.create(
            username="col_agent",
            tenant=tenant_a,
            data_scope=DataScope.TENANT,
        )
        _, case = _overdue_loan(
            tenant_a, product_a, client_a, days=12, principal="4000", ref="REF-DASH"
        )
        case.assigned_to = None
        case.save(update_fields=["assigned_to"])
        mine = agent_dashboard(user=agent, tenant_id=tenant_a.id, scope="mine")
        team = agent_dashboard(user=agent, tenant_id=tenant_a.id, scope="team")
        assert mine["assigned_open"] == 0
        assert team["assigned_open"] >= 1
        assert team["unassigned_open"] >= 1


@patch("apps.notifications.services.send_email_for_tenant")
def test_tranche_transfer_emails_collection_team(
    mock_send, tenant_a, product_a, client_a
):
    from apps.accounts.models import User
    from apps.accounts.services import (
        RESP_RECOUVREMENT_ROLE_NAME,
        ensure_default_role_packs,
        get_or_create_tenant_role,
    )
    from apps.collections.models import CollectionTranche
    from apps.collections.services import ensure_default_tranches
    from apps.notifications.models import NotificationLog, TenantNotificationSettings

    ensure_default_role_packs(tenant_a)
    group, _ = get_or_create_tenant_role(tenant_a, RESP_RECOUVREMENT_ROLE_NAME)
    officer = User.objects.create_user(
        username="reco_mail",
        password="x",
        email="reco@filiale.test",
        tenant=tenant_a,
    )
    officer.groups.add(group)
    TenantNotificationSettings.for_tenant(tenant_a)
    with tenant_context(tenant_a.id):
        ensure_default_tranches(tenant_a)
        _, case = _overdue_loan(
            tenant_a, product_a, client_a, days=40, principal="20000", ref="REF-MAIL-TR"
        )
        assert case.tranche.owner_kind == CollectionTranche.OwnerKind.COLLECTION
        log = NotificationLog.objects.filter(
            kind=NotificationLog.Kind.COLLECTION_TRANSFER
        ).first()
        assert log is not None
        assert "reco@filiale.test" in log.recipients
        mock_send.assert_called()


@patch("apps.notifications.services.send_email_for_tenant")
def test_dialogue_recommendation_emails_assigned_agent(
    mock_send, tenant_a, product_a, client_a
):
    from apps.accounts.models import User
    from apps.collections.models import CollectionDialogueMessage
    from apps.collections.serializers import CollectionDialogueMessageSerializer
    from apps.notifications.models import NotificationLog, TenantNotificationSettings

    agent = User.objects.create_user(
        username="agent_mail",
        password="x",
        email="agent@filiale.test",
        tenant=tenant_a,
    )
    author = User.objects.create_user(
        username="chef_mail",
        password="x",
        email="chef@filiale.test",
        tenant=tenant_a,
    )
    TenantNotificationSettings.for_tenant(tenant_a)
    with tenant_context(tenant_a.id):
        _, case = _overdue_loan(
            tenant_a, product_a, client_a, days=12, principal="4000", ref="REF-MAIL-DL"
        )
        case.assigned_to = agent
        case.save(update_fields=["assigned_to"])
        serializer = CollectionDialogueMessageSerializer(
            data={
                "case": str(case.id),
                "kind": CollectionDialogueMessage.Kind.RECOMMENDATION,
                "body": "Relancer le client cette semaine.",
            }
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(
            tenant_id=tenant_a.id, case=case, created_by=author, updated_by=author
        )
        log = NotificationLog.objects.filter(
            kind=NotificationLog.Kind.COLLECTION_DIALOGUE
        ).first()
        assert log is not None
        assert "agent@filiale.test" in log.recipients
        assert "chef@filiale.test" not in log.recipients
        mock_send.assert_called()
