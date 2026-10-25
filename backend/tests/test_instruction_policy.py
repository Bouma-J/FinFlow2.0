"""Politique d'instruction crédit — contrôles paramétrables."""
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.catalog.models import ChecklistItem, CreditProduct
from apps.clients.models import Client
from apps.common.tenancy import tenant_context
from apps.credits.access import can_attach_collateral
from apps.credits.instruction_policy import (
    assert_coverage_for_approval,
    assert_policy_submit_gates,
    build_readiness,
)
from apps.credits.models import (
    AnalysisThreshold,
    CreditApplication,
    CreditInstructionPolicy,
    FieldVisit,
    FinancialAnalysis,
)
from apps.credits.services import cancel_application, submit_application
from apps.guarantees.models import Guarantee
from apps.tenants.models import Tenant
from apps.workflow.models import ApprovalStep, ApprovalTask, WorkflowDefinition
from apps.workflow.services import WorkflowError, process_decision

pytestmark = pytest.mark.django_db


def _ready_app(tenant, client, product, *, ref="POL-APP", submitter=None):
    app = CreditApplication.objects.create(
        tenant=tenant,
        reference=ref,
        client=client,
        product=product,
        amount_requested=Decimal("500000"),
        duration_months=12,
        risk_level=1,
        submitted_by=submitter,
        created_by=submitter,
    )
    FinancialAnalysis.objects.create(
        tenant=tenant,
        application=app,
        is_reference=True,
        recommendation=FinancialAnalysis.Recommendation.FAVORABLE,
        salary_income=Decimal("300000"),
        client_type=getattr(client, "client_type", "") or "INDIVIDUAL",
    )
    return app


def _ensure_workflow(tenant, role):
    definition = WorkflowDefinition.objects.create(
        tenant=tenant, code="WF-POL", version=1, is_active=True
    )
    ApprovalStep.objects.create(
        tenant=tenant,
        definition=definition,
        name="Validation",
        order=1,
        required_group=role,
        sla_hours=24,
        step_kind=ApprovalStep.StepKind.DECISIONAL,
    )
    return definition


def test_policy_defaults_and_current_endpoint():
    tenant = Tenant.objects.create(
        code="POL1", name="Pol Test", country="CI", currency="XOF"
    )
    admin = User.objects.create_user(
        username="pol_admin",
        password="FinFlow2026!",
        is_staff=True,
        is_group_level=True,
    )
    client = APIClient()
    client.force_authenticate(admin)
    res = client.get(
        "/api/v1/credit-instruction-policy/current/",
        HTTP_X_TENANT_ID=str(tenant.id),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["collateral_coverage_mode"] == "ALERT"
    assert data["require_field_visit"] is False
    assert data["show_readiness_checklist"] is True
    assert data["enable_cancel_status"] is False

    res_patch = client.patch(
        "/api/v1/credit-instruction-policy/current/",
        {"require_field_visit": True, "collateral_coverage_mode": "BLOCK_SUBMIT"},
        format="json",
        HTTP_X_TENANT_ID=str(tenant.id),
    )
    assert res_patch.status_code == 400
    assert "versionn" in str(res_patch.data)
    # La même évolution doit passer par rédaction puis publication indépendante.
    from django.contrib.auth.models import Permission
    permissions = Permission.objects.filter(content_type__app_label="configuration")
    admin.user_permissions.add(*permissions)
    for cache in ("_perm_cache", "_group_perm_cache", "_user_perm_cache"):
        admin.__dict__.pop(cache, None)
    headers = {"HTTP_X_TENANT_ID": str(tenant.pk)}
    created = client.post("/api/v1/configuration-profiles/", {
        "code": "policy-recette", "name": "Politique recette", "reason": "Révision des contrôles",
        "overrides": {"policy": {"require_field_visit": True, "collateral_coverage_mode": "BLOCK_SUBMIT"}},
    }, format="json", **headers)
    assert created.status_code == 201, created.content
    url = f"/api/v1/configuration-profiles/{created.data['id']}/"
    assert client.post(url + "submit/", {}, format="json", **headers).status_code == 200
    reviewer = User.objects.create_user(username="pol_reviewer", is_group_level=True, is_staff=True)
    reviewer.user_permissions.add(*permissions)
    client.force_authenticate(reviewer)
    published = client.post(url + "publish/", {}, format="json", **headers)
    assert published.status_code == 200, published.content
    resolved = client.get("/api/v1/credit-instruction-policy/current/", **headers)
    assert resolved.status_code == 200
    assert resolved.data["require_field_visit"] is True
    assert resolved.data["collateral_coverage_mode"] == "BLOCK_SUBMIT"


def test_unfavorable_blocked_when_policy_forbids(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        CreditInstructionPolicy.objects.create(
            tenant=tenant_a,
            allow_unfavorable_analysis_submit=False,
        )
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            client=client_a,
            product=product_a,
            amount_requested=product_a.amount_min,
            duration_months=product_a.duration_min_months,
        )
        FinancialAnalysis.objects.create(
            tenant=tenant_a,
            application=app,
            recommendation=FinancialAnalysis.Recommendation.UNFAVORABLE,
            is_reference=True,
        )
        with pytest.raises(WorkflowError, match="défavorable"):
            assert_policy_submit_gates(app)


def test_unfavorable_allowed_by_default(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            client=client_a,
            product=product_a,
            amount_requested=product_a.amount_min,
            duration_months=12,
        )
        FinancialAnalysis.objects.create(
            tenant=tenant_a,
            application=app,
            recommendation=FinancialAnalysis.Recommendation.UNFAVORABLE,
            is_reference=True,
        )
        # Ne lève pas — politique souple par défaut
        assert_policy_submit_gates(app)


def test_field_visit_required(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        CreditInstructionPolicy.objects.create(
            tenant=tenant_a, require_field_visit=True
        )
        app = _ready_app(tenant_a, client_a, product_a, ref="POL-VIS")
        with pytest.raises(WorkflowError, match="visite terrain"):
            assert_policy_submit_gates(app)

        FieldVisit.objects.create(
            tenant=tenant_a,
            application=app,
            visit_date="2026-01-15",
            report="OK",
            geo_coordinates="5.35, -4.00",
        )
        assert_policy_submit_gates(app)


def test_product_checklist_required(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        CreditInstructionPolicy.objects.create(
            tenant=tenant_a, require_product_checklist=True
        )
        ChecklistItem.objects.create(
            tenant=tenant_a,
            product=product_a,
            label="CNI",
            is_mandatory=True,
            order=1,
        )
        app = _ready_app(tenant_a, client_a, product_a, ref="POL-CHK")
        with pytest.raises(WorkflowError, match="Pièces obligatoires"):
            assert_policy_submit_gates(app)

        app.document_checklist = [{"label": "CNI", "provided": True}]
        app.save(update_fields=["document_checklist"])
        assert_policy_submit_gates(app)


def test_match_client_type_product(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        CreditInstructionPolicy.objects.create(
            tenant=tenant_a, match_product_client_type=True
        )
        product_a.client_type = CreditProduct.ClientType.CORPORATE
        product_a.save(update_fields=["client_type"])
        app = _ready_app(tenant_a, client_a, product_a, ref="POL-TYPE")
        # client_a is INDIVIDUAL
        with pytest.raises(WorkflowError, match="type de client"):
            assert_policy_submit_gates(app)


def test_corporate_product_accepts_groupement(tenant_a, product_a):
    with tenant_context(tenant_a.id):
        CreditInstructionPolicy.objects.create(
            tenant=tenant_a, match_product_client_type=True
        )
        product_a.client_type = CreditProduct.ClientType.CORPORATE
        product_a.save(update_fields=["client_type"])
        group = Client.objects.create(
            tenant=tenant_a,
            reference="CLI-GIE-POL",
            client_type=Client.ClientType.PROFESSIONAL,
            company_name="GIE Politique",
            kyc_status=Client.KycStatus.VALIDATED,
        )
        app = _ready_app(tenant_a, group, product_a, ref="POL-GIE")
        assert_policy_submit_gates(app)


def test_coverage_block_submit(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        CreditInstructionPolicy.objects.create(
            tenant=tenant_a,
            collateral_coverage_mode=CreditInstructionPolicy.CoverageMode.BLOCK_SUBMIT,
        )
        AnalysisThreshold.objects.create(
            tenant=tenant_a, min_guarantee_coverage=Decimal("100")
        )
        product_a.requires_guarantee = True
        product_a.save(update_fields=["requires_guarantee"])
        app = _ready_app(tenant_a, client_a, product_a, ref="POL-COV")
        Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            application=app,
            guarantee_type=Guarantee.GuaranteeType.OTHER,
            status=Guarantee.Status.ACTIVE,
            description="Faible",
            current_value=Decimal("1000"),
            reference="GAR-WEAK-SUB",
        )
        with pytest.raises(WorkflowError, match="Couverture"):
            assert_policy_submit_gates(app)


def test_coverage_block_approve(tenant_a, client_a, product_a):
    role = Group.objects.create(name="Val Pol Cov")
    validator = User.objects.create(username="val_pol_cov", tenant=tenant_a)
    validator.groups.add(role)
    submitter = User.objects.create(username="sub_pol_cov", tenant=tenant_a)

    with tenant_context(tenant_a.id):
        CreditInstructionPolicy.objects.create(
            tenant=tenant_a,
            collateral_coverage_mode=CreditInstructionPolicy.CoverageMode.BLOCK_APPROVE,
        )
        AnalysisThreshold.objects.create(
            tenant=tenant_a, min_guarantee_coverage=Decimal("100")
        )
        _ensure_workflow(tenant_a, role)
        app = _ready_app(
            tenant_a, client_a, product_a, ref="POL-APPV", submitter=submitter
        )
        Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            application=app,
            guarantee_type=Guarantee.GuaranteeType.OTHER,
            status=Guarantee.Status.ACTIVE,
            description="Faible",
            current_value=Decimal("1000"),
            reference="GAR-WEAK-APP",
        )
        submit_application(app, submitter)
        task = ApprovalTask.objects.get(instance__object_id=app.id)
        with pytest.raises(WorkflowError, match="Couverture"):
            process_decision(
                task,
                validator,
                ApprovalTask.Status.APPROVED,
                opinion=ApprovalTask.Opinion.FAVORABLE,
            )


def test_collateral_during_approval_policy(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        app = _ready_app(tenant_a, client_a, product_a, ref="POL-ATT")
        app.status = CreditApplication.Status.IN_APPROVAL
        app.save(update_fields=["status"])
        assert can_attach_collateral(app) is False

        CreditInstructionPolicy.objects.create(
            tenant=tenant_a, allow_collateral_during_approval=True
        )
        assert can_attach_collateral(app) is True


def test_cancel_application_gated(tenant_a, client_a, product_a):
    submitter = User.objects.create(username="sub_cancel", tenant=tenant_a)
    with tenant_context(tenant_a.id):
        app = _ready_app(
            tenant_a, client_a, product_a, ref="POL-CAN", submitter=submitter
        )
        with pytest.raises(WorkflowError, match="n'est pas activée"):
            cancel_application(app, submitter)

        CreditInstructionPolicy.objects.create(
            tenant=tenant_a, enable_cancel_status=True
        )
        cancel_application(app, submitter)
        app.refresh_from_db()
        assert app.status == CreditApplication.Status.CANCELLED


def test_amount_approved_forbid_on_decision(tenant_a, client_a, product_a):
    role = Group.objects.create(name="Val Pol Amt")
    validator = User.objects.create(username="val_pol_amt", tenant=tenant_a)
    validator.groups.add(role)
    submitter = User.objects.create(username="sub_pol_amt", tenant=tenant_a)

    with tenant_context(tenant_a.id):
        CreditInstructionPolicy.objects.create(
            tenant=tenant_a,
            amount_approved_mode=CreditInstructionPolicy.AmountApprovedMode.FORBID,
        )
        _ensure_workflow(tenant_a, role)
        app = _ready_app(
            tenant_a, client_a, product_a, ref="POL-AMT", submitter=submitter
        )
        app.amount_approved = Decimal("999")
        app.amount_proposed = Decimal("400000")
        app.save(update_fields=["amount_approved", "amount_proposed"])

        submit_application(app, submitter)
        task = ApprovalTask.objects.get(instance__object_id=app.id)
        process_decision(
            task,
            validator,
            ApprovalTask.Status.APPROVED,
            opinion=ApprovalTask.Opinion.FAVORABLE,
        )
        app.refresh_from_db()
        assert app.status == CreditApplication.Status.APPROVED
        # FORBID écrase le 999 pré-saisi par proposed/requested
        assert app.amount_approved == Decimal("400000")


def test_readiness_endpoint(tenant_a, client_a, product_a):
    user = User.objects.create_user(
        username="ready_user",
        password="FinFlow2026!",
        tenant=tenant_a,
        is_staff=True,
        is_superuser=True,
        data_scope="TENANT",
    )
    with tenant_context(tenant_a.id):
        CreditInstructionPolicy.objects.create(
            tenant=tenant_a, require_field_visit=True, show_readiness_checklist=True
        )
        app = _ready_app(tenant_a, client_a, product_a, ref="POL-RDY")

    api = APIClient()
    api.force_authenticate(user)
    res = api.get(
        f"/api/v1/credit-applications/{app.id}/readiness/",
        HTTP_X_TENANT_ID=str(tenant_a.id),
    )
    assert res.status_code == 200, res.content
    body = res.json()
    assert body["show_checklist"] is True
    assert body["ready"] is False
    keys = {c["key"] for c in body["checks"]}
    assert "field_visit" in keys
    visit_check = next(c for c in body["checks"] if c["key"] == "field_visit")
    assert visit_check["ok"] is False
    assert visit_check["blocking"] is True


def test_readiness_structure(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            client=client_a,
            product=product_a,
            amount_requested=product_a.amount_min,
            duration_months=12,
        )
        payload = build_readiness(app)
        assert "checks" in payload
        assert "ready" in payload
        assert payload["policy"]["collateral_coverage_mode"] == "ALERT"


def test_assert_coverage_for_approval_noop_on_alert(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        app = _ready_app(tenant_a, client_a, product_a, ref="POL-NOOP")
        # Mode ALERT (défaut) : ne bloque pas
        assert_coverage_for_approval(app)
