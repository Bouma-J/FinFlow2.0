"""Circuits — délégations inbox, clone, SoD processus, avis sous réserve."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Delegation, User
from apps.common.tenancy import tenant_context
from apps.guarantees.models import Guarantee, GuaranteeReleaseRequest
from apps.workflow.models import (
    ApprovalStep,
    ApprovalTask,
    WorkflowDefinition,
    WorkflowInstance,
)
from apps.workflow.services import (
    WorkflowError,
    clone_workflow_definition,
    effective_group_ids,
    process_decision,
    start_workflow,
)

pytestmark = pytest.mark.django_db


def test_effective_group_ids_includes_delegated_groups(tenant_a):
    role = Group.objects.create(name="Comité inbox")
    delegator = User.objects.create(username="del_inbox_a", tenant=tenant_a)
    delegator.groups.add(role)
    delegate = User.objects.create(username="del_inbox_b", tenant=tenant_a)
    today = timezone.localdate()
    Delegation.objects.create(
        delegator=delegator,
        delegate=delegate,
        start_date=today - timedelta(days=1),
        end_date=today + timedelta(days=7),
        is_active=True,
    )
    assert role.id in effective_group_ids(delegate)
    assert role.id not in effective_group_ids(
        User.objects.create(username="del_inbox_c", tenant=tenant_a)
    )


def test_my_pending_includes_delegate_tasks(tenant_a, product_a, client_a):
    from django.contrib.auth.models import Permission

    from apps.credits.models import CreditApplication, FinancialAnalysis
    from apps.credits.services import submit_application

    role = Group.objects.create(name="Validateur dél")
    delegator = User.objects.create(
        username="val_del_a", tenant=tenant_a, password="x"
    )
    delegator.groups.add(role)
    delegate = User.objects.create(
        username="val_del_b",
        tenant=tenant_a,
        password="x",
        data_scope="TENANT",
    )
    perm = Permission.objects.get(
        content_type__app_label="workflow",
        codename="view_approvaltask",
    )
    delegate.user_permissions.add(perm)
    today = timezone.localdate()
    Delegation.objects.create(
        delegator=delegator,
        delegate=delegate,
        start_date=today - timedelta(days=1),
        end_date=today + timedelta(days=7),
        is_active=True,
    )
    submitter = User.objects.create(username="sub_del", tenant=tenant_a)

    with tenant_context(tenant_a.id):
        definition = WorkflowDefinition.objects.create(
            tenant=tenant_a, code="WF_INBOX", version=1, is_active=True
        )
        ApprovalStep.objects.create(
            tenant=tenant_a,
            definition=definition,
            name="Validation",
            order=1,
            required_group=role,
            sla_hours=24,
            step_kind=ApprovalStep.StepKind.DECISIONAL,
        )
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="DEL-INBOX-1",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("500000"),
            duration_months=12,
            risk_level=1,
            submitted_by=submitter,
        )
        FinancialAnalysis.objects.create(
            tenant=tenant_a,
            application=app,
            is_reference=True,
            recommendation=FinancialAnalysis.Recommendation.FAVORABLE,
            salary_income=Decimal("300000"),
            client_type="INDIVIDUAL",
        )
        submit_application(app, submitter)

    api = APIClient()
    api.force_authenticate(delegate)
    res = api.get(
        "/api/v1/approval-tasks/my_pending/",
        HTTP_X_TENANT_ID=str(tenant_a.id),
    )
    assert res.status_code == 200
    data = res.json()
    results = data.get("results", data)
    assert len(results) >= 1


def test_clone_workflow_definition_bumps_version(tenant_a):
    role = Group.objects.create(name="Clone rôle")
    with tenant_context(tenant_a.id):
        source = WorkflowDefinition.objects.create(
            tenant=tenant_a,
            code="WF_CLONE",
            name="Circuit clone",
            version=1,
            is_active=True,
        )
        ApprovalStep.objects.create(
            tenant=tenant_a,
            definition=source,
            name="Étape 1",
            order=1,
            required_group=role,
            sla_hours=24,
            allow_return=False,
            step_kind=ApprovalStep.StepKind.DECISIONAL,
        )
        clone = clone_workflow_definition(source, deactivate_source=True)
        source.refresh_from_db()
        assert source.is_active is False
        assert clone.version == 2
        assert clone.is_active is True
        assert clone.steps.count() == 1
        step = clone.steps.get()
        assert step.allow_return is False
        assert step.name == "Étape 1"


def test_process_self_validation_blocked(tenant_a, client_a):
    role = Group.objects.create(name="Chef ML")
    initiator = User.objects.create(username="ml_init", tenant=tenant_a)
    initiator.groups.add(role)

    with tenant_context(tenant_a.id):
        guarantee = Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
            description="Bien test",
            expertise_value=Decimal("1000000"),
            current_value=Decimal("1000000"),
            status=Guarantee.Status.ACTIVE,
            reference="GAR-SOD-1",
            created_by=initiator,
        )
        definition = WorkflowDefinition.objects.create(
            tenant=tenant_a,
            code="WF_ML_SOD",
            version=1,
            is_active=True,
            target_type=WorkflowDefinition.TargetType.MAIN_LEVEE,
        )
        ApprovalStep.objects.create(
            tenant=tenant_a,
            definition=definition,
            name="Validation ML",
            order=1,
            required_group=role,
            sla_hours=24,
            step_kind=ApprovalStep.StepKind.DECISIONAL,
        )
        req = GuaranteeReleaseRequest.objects.create(
            tenant=tenant_a,
            guarantee=guarantee,
            reference="ML-SOD-1",
            created_by=initiator,
            status=GuaranteeReleaseRequest.Status.DRAFT,
        )
        instance = start_workflow(
            req,
            amount=Decimal("1000000"),
            definition=definition,
            target_type=WorkflowDefinition.TargetType.MAIN_LEVEE,
        )
        task = ApprovalTask.objects.get(instance=instance)
        with pytest.raises(WorkflowError, match="initié"):
            process_decision(
                task,
                initiator,
                ApprovalTask.Status.APPROVED,
                opinion=ApprovalTask.Opinion.FAVORABLE,
            )


def test_sous_reserve_rejected_for_process(tenant_a, client_a):
    role = Group.objects.create(name="Chef ML 2")
    initiator = User.objects.create(username="ml_init2", tenant=tenant_a)
    validator = User.objects.create(username="ml_val2", tenant=tenant_a)
    validator.groups.add(role)

    with tenant_context(tenant_a.id):
        guarantee = Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
            description="Bien test 2",
            expertise_value=Decimal("1000000"),
            current_value=Decimal("1000000"),
            status=Guarantee.Status.ACTIVE,
            reference="GAR-RES-1",
            created_by=initiator,
        )
        definition = WorkflowDefinition.objects.create(
            tenant=tenant_a,
            code="WF_ML_RES",
            version=1,
            is_active=True,
            target_type=WorkflowDefinition.TargetType.MAIN_LEVEE,
        )
        ApprovalStep.objects.create(
            tenant=tenant_a,
            definition=definition,
            name="Validation ML",
            order=1,
            required_group=role,
            sla_hours=24,
            step_kind=ApprovalStep.StepKind.DECISIONAL,
        )
        req = GuaranteeReleaseRequest.objects.create(
            tenant=tenant_a,
            guarantee=guarantee,
            reference="ML-RES-1",
            created_by=initiator,
            status=GuaranteeReleaseRequest.Status.DRAFT,
        )
        instance = start_workflow(
            req,
            amount=Decimal("1000000"),
            definition=definition,
            target_type=WorkflowDefinition.TargetType.MAIN_LEVEE,
        )
        task = ApprovalTask.objects.get(instance=instance)
        with pytest.raises(WorkflowError, match="réserves"):
            process_decision(
                task,
                validator,
                ApprovalTask.Status.APPROVED,
                opinion=ApprovalTask.Opinion.FAVORABLE_SOUS_RESERVE,
                reserves=["Acte notarié"],
            )
