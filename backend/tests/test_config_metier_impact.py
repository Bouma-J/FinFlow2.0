"""
Config → impact métier : paramètres filiale / env / CBS et effets observés.
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.catalog.models import CreditProduct
from apps.common.tenancy import tenant_context
from apps.corebanking.disbursement import disbursement_mode
from apps.corebanking.models import CoreBankingConnector
from apps.credits.collateral import build_collateral_summary, retained_value
from apps.credits.instruction_policy import assert_policy_submit_gates
from apps.credits.models import (
    AnalysisThreshold,
    CreditApplication,
    CreditInstructionPolicy,
    FinancialAnalysis,
)
from apps.credits.services import submit_application
from apps.documents.models import Document, DocumentCategory
from apps.documents.quotas import assert_ged_quota
from apps.documents.tasks import purge_soft_deleted_documents
from apps.guarantees.models import Guarantee, PledgeCategory
from apps.notifications.models import TenantNotificationSettings
from apps.workflow.services import WorkflowError

pytestmark = pytest.mark.django_db


def test_ged_quota_blocks_when_exceeded(tenant_a):
    tenant_a.ged_quota_bytes = 1000
    tenant_a.ged_used_bytes = 900
    tenant_a.save(update_fields=["ged_quota_bytes", "ged_used_bytes"])
    with pytest.raises(ValidationError, match="Quota GED"):
        assert_ged_quota(tenant_a, 200)
    # Sous le plafond : OK
    assert_ged_quota(tenant_a, 50)


def test_ged_quota_unlimited_when_zero(tenant_a):
    tenant_a.ged_quota_bytes = 0
    tenant_a.ged_used_bytes = 10**12
    tenant_a.save(update_fields=["ged_quota_bytes", "ged_used_bytes"])
    assert_ged_quota(tenant_a, 10**9)  # no raise


@override_settings(GED_SOFT_DELETE_RETENTION_DAYS=30)
def test_purge_respects_retention_days(tenant_a):
    with tenant_context(tenant_a.id):
        cat = DocumentCategory.objects.create(
            tenant=tenant_a, code="RET", label="Retention"
        )
        old = Document(
            tenant=tenant_a,
            category=cat,
            name="old.pdf",
            is_deleted=True,
            deleted_at=timezone.now() - timedelta(days=45),
            size_bytes=100,
        )
        old.file.save(
            "old.pdf",
            SimpleUploadedFile("old.pdf", b"%PDF-old", content_type="application/pdf"),
            save=True,
        )
        recent = Document(
            tenant=tenant_a,
            category=cat,
            name="recent.pdf",
            is_deleted=True,
            deleted_at=timezone.now() - timedelta(days=5),
            size_bytes=50,
        )
        recent.file.save(
            "recent.pdf",
            SimpleUploadedFile(
                "recent.pdf", b"%PDF-new", content_type="application/pdf"
            ),
            save=True,
        )
        old_id, recent_id = old.id, recent.id

    purged = purge_soft_deleted_documents()
    assert purged >= 1
    assert not Document.including_deleted.filter(pk=old_id).exists()
    assert Document.including_deleted.filter(pk=recent_id, is_deleted=True).exists()


@override_settings(FEATURE_SMS=False)
def test_feature_sms_off_skips_reminder(tenant_a, product_a, client_a):
    from apps.collections.services import send_collection_reminder
    from apps.credits.models import Installment, Loan
    from datetime import date

    with tenant_context(tenant_a.id):
        client_a.phone = "+22370000001"
        client_a.save(update_fields=["phone"])
        prefs = TenantNotificationSettings.for_tenant(tenant_a)
        prefs.notify_collection_sms = True
        prefs.enabled = True
        prefs.save()
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            client=client_a,
            product=product_a,
            amount_requested=Decimal("3000"),
            duration_months=3,
            reference="CFG-SMS-OFF",
            status=CreditApplication.Status.DISBURSED,
        )
        loan = Loan.objects.create(
            tenant=tenant_a,
            application=app,
            principal=Decimal("3000"),
            interest_rate=Decimal("12"),
            duration_months=3,
            disbursed_at=date.today() - timedelta(days=40),
            first_due_date=date.today() - timedelta(days=20),
            status=Loan.Status.ACTIVE,
        )
        Installment.objects.create(
            tenant=tenant_a,
            loan=loan,
            number=1,
            due_date=date.today() - timedelta(days=20),
            principal_due=Decimal("1000"),
            interest_due=Decimal("30"),
            total_due=Decimal("1030"),
            status=Installment.Status.OVERDUE,
        )
        from apps.collections.models import CollectionCase

        case = CollectionCase.objects.create(
            tenant=tenant_a,
            loan=loan,
            stage=CollectionCase.Stage.AMICABLE,
            days_overdue=20,
        )
        result = send_collection_reminder(case, channel="SMS", force=True)
        assert result["status"] == "SKIPPED"
        assert result["channel"] == "SMS"
        assert "FEATURE_SMS" in result.get("reason", "")


@override_settings(FEATURE_SMS=True)
def test_feature_sms_on_runs_stub(tenant_a, product_a, client_a):
    from datetime import date

    from apps.collections.models import CollectionCase
    from apps.collections.services import send_collection_reminder
    from apps.credits.models import Installment, Loan

    with tenant_context(tenant_a.id):
        client_a.phone = "+22370000002"
        client_a.save(update_fields=["phone"])
        prefs = TenantNotificationSettings.for_tenant(tenant_a)
        prefs.notify_collection_sms = True
        prefs.enabled = True
        prefs.save()
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            client=client_a,
            product=product_a,
            amount_requested=Decimal("3000"),
            duration_months=3,
            reference="CFG-SMS-ON",
            status=CreditApplication.Status.DISBURSED,
        )
        loan = Loan.objects.create(
            tenant=tenant_a,
            application=app,
            principal=Decimal("3000"),
            interest_rate=Decimal("12"),
            duration_months=3,
            disbursed_at=date.today() - timedelta(days=40),
            first_due_date=date.today() - timedelta(days=20),
            status=Loan.Status.ACTIVE,
        )
        Installment.objects.create(
            tenant=tenant_a,
            loan=loan,
            number=1,
            due_date=date.today() - timedelta(days=20),
            principal_due=Decimal("1000"),
            interest_due=Decimal("30"),
            total_due=Decimal("1030"),
            status=Installment.Status.OVERDUE,
        )
        case = CollectionCase.objects.create(
            tenant=tenant_a,
            loan=loan,
            stage=CollectionCase.Stage.AMICABLE,
            days_overdue=20,
        )
        result = send_collection_reminder(case, channel="SMS", force=True)
        assert result["channel"] == "SMS"
        assert result["status"] in ("SKIPPED", "SENT", "FAILED")
        # Avec FEATURE_SMS=True le stub provider s'exécute (pas le short-circuit flag)
        assert "FEATURE_SMS=0" not in result.get("reason", "")


def test_coverage_threshold_change_affects_summary(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        th = AnalysisThreshold.for_tenant(tenant_a.id)
        th.min_guarantee_coverage = Decimal("100")
        th.haircut_vehicle = Decimal("0")
        th.save()
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="CFG-COV",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("1000000"),
            duration_months=12,
        )
        Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            application=app,
            guarantee_type=Guarantee.GuaranteeType.PLEDGE,
            pledge_category=PledgeCategory.VEHICLE,
            description="Véhicule",
            current_value=Decimal("800000"),
            status=Guarantee.Status.ACTIVE,
            reference="GAR-CFG-1",
        )
        summary = build_collateral_summary(app)
        assert summary["guarantee_coverage_pct"] == "80.00"
        assert summary["guarantee_ok"] is False  # seuil 100%

        th.min_guarantee_coverage = Decimal("80")
        th.save(update_fields=["min_guarantee_coverage"])
        summary2 = build_collateral_summary(app)
        assert summary2["guarantee_ok"] is True

        th.haircut_vehicle = Decimal("50")
        th.save(update_fields=["haircut_vehicle"])
        g = Guarantee.objects.get(reference="GAR-CFG-1")
        assert retained_value(g, th) == Decimal("400000.00")
        summary3 = build_collateral_summary(app)
        assert summary3["guarantee_coverage_pct"] == "40.00"
        assert summary3["guarantee_ok"] is False


def test_block_submit_coverage_mode_blocks(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        CreditInstructionPolicy.objects.update_or_create(
            tenant=tenant_a,
            defaults={
                "collateral_coverage_mode": "BLOCK_SUBMIT",
                "require_field_visit": False,
                "allow_unfavorable_analysis_submit": True,
                "require_product_checklist": False,
                "match_product_client_type": False,
            },
        )
        th = AnalysisThreshold.for_tenant(tenant_a.id)
        th.min_guarantee_coverage = Decimal("100")
        th.save()
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="CFG-BLK",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("1000000"),
            duration_months=12,
            status=CreditApplication.Status.DRAFT,
        )
        FinancialAnalysis.objects.create(
            tenant=tenant_a,
            application=app,
            is_reference=True,
            recommendation=FinancialAnalysis.Recommendation.FAVORABLE,
            salary_income=Decimal("300000"),
            client_type=client_a.client_type,
        )
        # Pas de garantie → couverture 0 → BLOCK_SUBMIT
        with pytest.raises(WorkflowError):
            assert_policy_submit_gates(app)


def test_alert_mode_allows_submit_gates(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        CreditInstructionPolicy.objects.update_or_create(
            tenant=tenant_a,
            defaults={
                "collateral_coverage_mode": "ALERT",
                "require_field_visit": False,
                "allow_unfavorable_analysis_submit": True,
                "require_product_checklist": False,
                "match_product_client_type": False,
            },
        )
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="CFG-ALRT",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("1000000"),
            duration_months=12,
            status=CreditApplication.Status.DRAFT,
        )
        FinancialAnalysis.objects.create(
            tenant=tenant_a,
            application=app,
            is_reference=True,
            recommendation=FinancialAnalysis.Recommendation.FAVORABLE,
            salary_income=Decimal("300000"),
            client_type=client_a.client_type,
        )
        # ALERT : ne lève pas sur couverture insuffisante
        assert_policy_submit_gates(app)


def test_cbs_disbursement_mode_from_mapping_rules(tenant_a):
    c = CoreBankingConnector(
        tenant=tenant_a,
        name="Cfg",
        protocol=CoreBankingConnector.Protocol.REST,
        base_url="https://cbs.example.com",
        is_active=True,
        mapping_rules={"disbursement": {"mode": "LOCAL"}},
    )
    assert disbursement_mode(c) == "LOCAL"
    c.mapping_rules = {"disbursement": {"mode": "CBS"}}
    assert disbursement_mode(c) == "CBS"
    # force_simulate n'override PAS un mode CBS explicite (comportement actuel)
    c.mapping_rules = {"force_simulate": True, "disbursement": {"mode": "CBS"}}
    assert disbursement_mode(c) == "CBS"
    # Sans mode explicite, force_simulate → LOCAL
    c.mapping_rules = {"force_simulate": True}
    assert disbursement_mode(c) == "LOCAL"
    c.base_url = ""
    c.mapping_rules = {}
    assert disbursement_mode(c) == "LOCAL"


def test_product_bounds_gate_on_submit(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        product_a.amount_max = Decimal("100000")
        product_a.amount_min = Decimal("10000")
        product_a.save(update_fields=["amount_max", "amount_min"])
        CreditInstructionPolicy.objects.update_or_create(
            tenant=tenant_a,
            defaults={
                "collateral_coverage_mode": "ALERT",
                "require_field_visit": False,
                "allow_unfavorable_analysis_submit": True,
                "require_product_checklist": False,
                "match_product_client_type": False,
            },
        )
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="CFG-BND",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("500000"),  # > max
            duration_months=12,
            status=CreditApplication.Status.DRAFT,
        )
        FinancialAnalysis.objects.create(
            tenant=tenant_a,
            application=app,
            is_reference=True,
            recommendation=FinancialAnalysis.Recommendation.FAVORABLE,
            salary_income=Decimal("300000"),
            client_type=client_a.client_type,
        )
        with pytest.raises(Exception):
            submit_application(app)


def test_notification_prefs_skip_collection_email(tenant_a, product_a, client_a):
    from datetime import date

    from apps.collections.models import CollectionCase
    from apps.collections.services import send_collection_reminder
    from apps.credits.models import Installment, Loan

    with tenant_context(tenant_a.id):
        client_a.email = "cfg@example.com"
        client_a.save(update_fields=["email"])
        prefs = TenantNotificationSettings.for_tenant(tenant_a)
        prefs.enabled = True
        prefs.notify_collection_email = False
        prefs.save()
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            client=client_a,
            product=product_a,
            amount_requested=Decimal("3000"),
            duration_months=3,
            reference="CFG-MAIL-OFF",
            status=CreditApplication.Status.DISBURSED,
        )
        loan = Loan.objects.create(
            tenant=tenant_a,
            application=app,
            principal=Decimal("3000"),
            interest_rate=Decimal("12"),
            duration_months=3,
            disbursed_at=date.today() - timedelta(days=40),
            first_due_date=date.today() - timedelta(days=20),
            status=Loan.Status.ACTIVE,
        )
        Installment.objects.create(
            tenant=tenant_a,
            loan=loan,
            number=1,
            due_date=date.today() - timedelta(days=20),
            principal_due=Decimal("1000"),
            interest_due=Decimal("30"),
            total_due=Decimal("1030"),
            status=Installment.Status.OVERDUE,
        )
        case = CollectionCase.objects.create(
            tenant=tenant_a,
            loan=loan,
            stage=CollectionCase.Stage.AMICABLE,
            days_overdue=20,
        )
        result = send_collection_reminder(case, channel="EMAIL", force=False)
        assert result["status"] == "SKIPPED"


def test_live_demo_policy_endpoint_reachable(tenant_a):
    """Smoke structure API politique (tenant de test)."""
    from apps.accounts.models import User

    admin = User.objects.create_user(
        username="cfg_pol_api",
        password="x",
        is_staff=True,
        tenant=tenant_a,
    )
    from django.contrib.auth.models import Permission

    for codename in (
        "view_creditinstructionpolicy",
        "view_analysisthreshold",
    ):
        perm = Permission.objects.filter(
            content_type__app_label="credits",
            codename=codename,
        ).first()
        if perm:
            admin.user_permissions.add(perm)
    api = APIClient()
    api.force_authenticate(admin)
    res = api.get(
        "/api/v1/credit-instruction-policy/current/",
        HTTP_X_TENANT_ID=str(tenant_a.id),
        HTTP_HOST="localhost",
    )
    assert res.status_code == 200
    body = res.json()
    assert "collateral_coverage_mode" in body
    assert "require_surety_signed_contracts" in body
    assert "require_formalization_before_disbursement" in body

    th = api.get(
        "/api/v1/analysis-thresholds/current/",
        HTTP_X_TENANT_ID=str(tenant_a.id),
        HTTP_HOST="localhost",
    )
    assert th.status_code == 200
    assert "min_guarantee_coverage" in th.json()
    assert "haircut_vehicle" in th.json()
