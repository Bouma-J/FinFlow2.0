"""Garde-fous paramétrables et preuves de mise en place."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User, Delegation
from apps.audit.models import AuditLog
from apps.common.tenancy import tenant_context
from apps.contracts.models import ContractTemplate, GeneratedContract
from apps.contracts.services import missing_required_contracts
from apps.credits.models import CreditApplication, CreditInstructionPolicy, FinancialAnalysis
from apps.credits.governance import freeze_approval, setup_checks, verified_checklist
from apps.credits.risk import risk_level_from_analysis
from apps.credits.services import disburse_application
from apps.documents.models import Document, DocumentCategory
from apps.workflow.models import WorkflowDefinition, ApprovalStep
from apps.workflow.services import WorkflowError, user_can_act

pytestmark = pytest.mark.django_db


@pytest.fixture
def app(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.pk):
        return CreditApplication.objects.create(tenant=tenant_a, client=client_a, product=product_a,
            reference="GOV", status="APPROVED", amount_requested=100000, amount_approved=100000,
            duration_months=12, interest_rate=10, decision_date=timezone.now().date())


def test_contract_requirement_and_signature_switches(tenant_a, app):
    with tenant_context(tenant_a.pk):
        template = ContractTemplate.objects.create(tenant=tenant_a, name="Prêt", is_required=True)
        assert missing_required_contracts(app) == ["Prêt"]
        policy = CreditInstructionPolicy.objects.create(tenant=tenant_a, require_credit_contracts=False)
        assert missing_required_contracts(app) == []
        policy.require_credit_contracts = True
        policy.require_credit_signed_contracts = True
        policy.save()
        contract = GeneratedContract.objects.create(tenant=tenant_a, application=app, template=template)
        assert missing_required_contracts(app) == ["Prêt"]
        contract.status, contract.signed_file = "SIGNED", "signed.pdf"
        contract.save()
        assert missing_required_contracts(app) == []


def test_setup_request_and_four_eyes_switches(tenant_a, app, monkeypatch):
    from tests.setup_helpers import configure_local_cbs
    configure_local_cbs(app)
    with tenant_context(tenant_a.pk):
        actor = User.objects.create(username="operator", tenant=tenant_a, data_scope="TENANT")
        policy = CreditInstructionPolicy.objects.create(tenant=tenant_a, require_setup_request=True)
        with pytest.raises(WorkflowError, match="préalable"):
            disburse_application(app, skip_cbs=True, user=actor)
        app.status = "DISBURSEMENT_PENDING"
        app.disbursement_requested_by = actor
        app.save()
        policy.require_setup_four_eyes = True
        policy.save()
        with pytest.raises(WorkflowError, match="initiateur"):
            disburse_application(app, skip_cbs=True, user=actor)
        policy.require_setup_four_eyes = False
        policy.save()
        from tests.setup_helpers import prepare_setup
        prepare_setup(app, executor=actor)
        monkeypatch.setattr("apps.corebanking.disbursement.submit_credit_to_cbs", lambda application: {"num_contrat": "GOV-TEST"})
        assert disburse_application(app, user=actor).application_id == app.pk


@pytest.mark.parametrize("mode,expected", [("RECOMMENDATION", 2), ("SCORE", 5), ("CONSERVATIVE", 5)])
def test_configurable_risk(tenant_a, app, mode, expected):
    with tenant_context(tenant_a.pk):
        CreditInstructionPolicy.objects.create(tenant=tenant_a, risk_mode=mode)
        analysis = FinancialAnalysis(tenant=tenant_a, application=app, recommendation="FAVORABLE", internal_score=10)
        assert risk_level_from_analysis(analysis) == expected


def test_approval_evidence_and_expiration(tenant_a, app):
    with tenant_context(tenant_a.pk):
        CreditInstructionPolicy.objects.create(tenant=tenant_a, approval_validity_days=30)
        freeze_approval(app)
        before = app.approval_snapshot
        app.duration_months = 18
        app.save()
        assert any("conditions" in error for error in setup_checks(app))
        assert before["application"]["duration_months"] == 12
        app.decision_date = timezone.now().date() - timedelta(days=31)
        assert any("expiré" in error for error in setup_checks(app))


def test_delegation_scope_and_approval(tenant_a, app):
    with tenant_context(tenant_a.pk):
        owner = User.objects.create(username="owner", tenant=tenant_a)
        substitute = User.objects.create(username="substitute", tenant=tenant_a)
        approver = User.objects.create(username="admin", tenant=tenant_a)
        role = Group.objects.create(name="GOV_ROLE")
        owner.groups.add(role)
        definition = WorkflowDefinition.objects.create(tenant=tenant_a, code="GOV")
        step = ApprovalStep.objects.create(tenant=tenant_a, definition=definition, required_group=role, name="Décision", step_kind="DECISIONAL")
        grant = Delegation.objects.create(delegator=owner, delegate=substitute,
            start_date=timezone.now().date(), end_date=timezone.now().date(),
            approval_required=True, max_amount=50000)
        assert not user_can_act(substitute, step, app, Decimal("40000"))
        grant.approved_by = approver
        grant.save()
        assert user_can_act(substitute, step, app, Decimal("40000"))
        assert not user_can_act(substitute, step, app, Decimal("100000"))
        assert AuditLog.objects.filter(model_label="accounts.Delegation", object_id=str(grant.pk), changes__has_key="before").exists()


def test_verified_documents_are_real_and_current(tenant_a, app):
    from apps.catalog.models import ChecklistItem
    with tenant_context(tenant_a.pk):
        ChecklistItem.objects.create(tenant=tenant_a, product=app.product, label="Bulletin")
        app.document_checklist = [{"label": "Bulletin", "provided": True}]
        assert verified_checklist(app) == ["Bulletin"]
        category = DocumentCategory.objects.create(tenant=tenant_a, code="BUL", label="Bulletin")
        doc = Document.objects.create(tenant=tenant_a, name="Bulletin", category=category,
            content_type=ContentType.objects.get_for_model(app), object_id=app.pk,
            file="bulletin.pdf", verification_status="VERIFIED")
        assert verified_checklist(app) == []
        doc.expiry_date = timezone.now().date() - timedelta(days=1)
        doc.save()
        assert verified_checklist(app) == ["Bulletin"]


def test_access_audit_excludes_secrets(tenant_a):
    actor = User.objects.create(username="audited", tenant=tenant_a, password="secret-hash")
    actor.is_staff = True
    actor.save()
    entry = AuditLog.objects.filter(model_label="accounts.User", object_id=str(actor.pk), action="UPDATE").first()
    assert entry.changes["before"]["is_staff"] == "False"
    assert entry.changes["after"]["is_staff"] == "True"
    assert "password" not in entry.changes["before"]
    assert "secret-hash" not in str(entry.changes)


def test_final_review_is_required_and_invalidated_by_evidence(tenant_a, app):
    from tests.setup_helpers import configure_local_cbs
    configure_local_cbs(app)
    from apps.credits.governance import assert_setup_review
    with tenant_context(tenant_a.pk):
        CreditInstructionPolicy.objects.create(tenant=tenant_a, require_final_review=True)
        reviewer = User.objects.create(username="reviewer", tenant=tenant_a, is_superuser=True, data_scope="TENANT")
        freeze_approval(app)
        with pytest.raises(WorkflowError, match="contrôle final"):
            assert_setup_review(app)
        api = APIClient()
        api.force_authenticate(reviewer)
        response = api.post(f"/api/v1/credit-applications/{app.pk}/setup-review/", {
            "comment": "Pièces, apport et conditions vérifiés.",
            "checks": {key: True for key in ("kyc", "contribution", "collateral", "terms", "insurance")},
        }, format="json")
        assert response.status_code == 200, response.content
        app.refresh_from_db()
        assert_setup_review(app)
        category = DocumentCategory.objects.create(tenant=tenant_a, code="EVIDENCE", label="Preuve")
        Document.objects.create(tenant=tenant_a, category=category, name="Nouvelle preuve", file="proof.pdf",
            content_type=ContentType.objects.get_for_model(app), object_id=app.pk)
        with pytest.raises(WorkflowError, match="contrôle final"):
            assert_setup_review(app)


def test_committee_quorum_and_conflicts(tenant_a, app):
    from apps.workflow.committee import validate_committee
    from apps.workflow.services import start_workflow
    with tenant_context(tenant_a.pk):
        group = Group.objects.create(name="Committee-test")
        members = [User.objects.create(username=f"member-{index}", tenant=tenant_a) for index in range(2)]
        for member in members:
            member.groups.add(group)
        definition = WorkflowDefinition.objects.create(tenant=tenant_a, code="COMMITTEE")
        step = ApprovalStep.objects.create(tenant=tenant_a, definition=definition, name="Comité",
            required_group=group, committee_quorum=2, step_kind="DECISIONAL")
        instance = start_workflow(app, Decimal("100000"), definition=definition)
        task = instance.tasks.get()
        record = {"participants": [{"user": str(member.pk), "vote": "FOR", "conflict": False} for member in members]}
        assert len(validate_committee(task, members[0], record)["participants"]) == 2
        record["participants"][1].update(conflict=True, vote="ABSTAIN")
        with pytest.raises(WorkflowError, match="quorum"):
            validate_committee(task, members[0], record)


def test_independent_delegation_approval_api(tenant_a):
    owner = User.objects.create(username="grant-owner", tenant=tenant_a)
    substitute = User.objects.create(username="grant-substitute", tenant=tenant_a)
    admin = User.objects.create(username="grant-admin", tenant=tenant_a, is_superuser=True)
    grant = Delegation.objects.create(delegator=owner, delegate=substitute, approval_required=True,
        start_date=timezone.now().date(), end_date=timezone.now().date())
    api = APIClient()
    owner.is_superuser = True
    owner.save()
    api.force_authenticate(owner)
    response = api.post(f"/api/v1/delegations/{grant.pk}/approve/")
    assert response.status_code == 403
    api.force_authenticate(admin)
    response = api.post(f"/api/v1/delegations/{grant.pk}/approve/")
    assert response.status_code == 200, response.content
    grant.refresh_from_db()
    assert grant.approved_by_id == admin.pk
    assert grant.is_currently_valid
