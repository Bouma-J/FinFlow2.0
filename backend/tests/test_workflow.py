"""Test du moteur de workflow (approbation d'un dossier)."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.utils import timezone

from apps.accounts.models import Delegation, User
from apps.credits.models import CreditApplication, FinancialAnalysis
from apps.credits.services import submit_application
from apps.common.tenancy import tenant_context
from apps.workflow.models import (
    ApprovalCondition,
    ApprovalStep,
    ApprovalTask,
    WorkflowDefinition,
    WorkflowInstance,
)
from apps.workflow.services import (
    WorkflowError,
    lift_condition,
    process_decision,
    user_can_act,
    validate_condition,
)

pytestmark = pytest.mark.django_db


def _ready_application(tenant, client, product, *, reference, submitter=None):
    application = CreditApplication.objects.create(
        tenant=tenant,
        reference=reference,
        client=client,
        product=product,
        amount_requested=Decimal("500000"),
        duration_months=12,
        risk_level=1,
        submitted_by=submitter,
    )
    FinancialAnalysis.objects.create(
        tenant=tenant,
        application=application,
        is_reference=True,
        recommendation=FinancialAnalysis.Recommendation.FAVORABLE,
        salary_income=Decimal("300000"),
        client_type=getattr(client, "client_type", "") or "INDIVIDUAL",
    )
    return application


def test_single_step_approval(tenant_a, product_a, client_a):
    role = Group.objects.create(name="Validateur A")
    validator = User.objects.create(username="val_a", tenant=tenant_a)
    validator.groups.add(role)

    submitter = User.objects.create(username="sub_a", tenant=tenant_a)

    with tenant_context(tenant_a.id):
        definition = WorkflowDefinition.objects.create(
            tenant=tenant_a, code="WF", version=1, is_active=True
        )
        ApprovalStep.objects.create(
            tenant=tenant_a, definition=definition, name="Validation",
            order=1, required_group=role, sla_hours=24,
            step_kind=ApprovalStep.StepKind.DECISIONAL,
        )
        application = _ready_application(
            tenant_a, client_a, product_a, reference="D1", submitter=submitter,
        )

        submit_application(application, submitter)
        application.refresh_from_db()
        assert application.status == CreditApplication.Status.IN_APPROVAL

        task = ApprovalTask.objects.get(instance__object_id=application.id)
        process_decision(
            task, validator, ApprovalTask.Status.APPROVED,
            opinion=ApprovalTask.Opinion.FAVORABLE,
        )

        application.refresh_from_db()
        assert application.status == CreditApplication.Status.APPROVED


def test_self_validation_blocked(tenant_a, product_a, client_a):
    role = Group.objects.create(name="Validateur B")
    user = User.objects.create(username="val_b", tenant=tenant_a)
    user.groups.add(role)

    with tenant_context(tenant_a.id):
        definition = WorkflowDefinition.objects.create(
            tenant=tenant_a, code="WF2", version=1, is_active=True
        )
        ApprovalStep.objects.create(
            tenant=tenant_a, definition=definition, name="Validation",
            order=1, required_group=role, sla_hours=24,
            step_kind=ApprovalStep.StepKind.DECISIONAL,
        )
        application = _ready_application(
            tenant_a, client_a, product_a, reference="D2",
        )
        submit_application(application, user)
        task = ApprovalTask.objects.get(instance__object_id=application.id)

        with pytest.raises(WorkflowError):
            process_decision(
                task, user, ApprovalTask.Status.APPROVED,
                opinion=ApprovalTask.Opinion.FAVORABLE,
            )


def test_reserve_blocks_final_approval(tenant_a, product_a, client_a):
    role = Group.objects.create(name="Validateur C")
    validator = User.objects.create(username="val_c", tenant=tenant_a)
    validator.groups.add(role)
    submitter = User.objects.create(username="sub_c", tenant=tenant_a)

    with tenant_context(tenant_a.id):
        definition = WorkflowDefinition.objects.create(
            tenant=tenant_a, code="WF3", version=1, is_active=True
        )
        ApprovalStep.objects.create(
            tenant=tenant_a, definition=definition, name="Comité",
            order=1, required_group=role, sla_hours=24,
            step_kind=ApprovalStep.StepKind.DECISIONAL,
        )
        application = _ready_application(
            tenant_a, client_a, product_a, reference="D3", submitter=submitter,
        )
        submit_application(application, submitter)
        task = ApprovalTask.objects.get(instance__object_id=application.id)

        process_decision(
            task, validator, ApprovalTask.Status.APPROVED,
            opinion=ApprovalTask.Opinion.FAVORABLE_SOUS_RESERVE,
            reserves=["Fournir garantie complémentaire"],
        )

        application.refresh_from_db()
        assert application.status == CreditApplication.Status.IN_APPROVAL
        instance = WorkflowInstance.objects.get(object_id=application.id)
        assert instance.status == WorkflowInstance.Status.AWAITING_CONDITIONS

        condition = ApprovalCondition.objects.get(application=application)
        lift_condition(condition, submitter, comment="Garantie fournie")
        validate_condition(condition, validator, comment="Conforme")

        application.refresh_from_db()
        assert application.status == CreditApplication.Status.APPROVED


def test_submit_requires_validated_kyc(tenant_a, product_a, client_a):
    from apps.clients.models import Client

    client_a.kyc_status = Client.KycStatus.PENDING
    client_a.save(update_fields=["kyc_status"])
    submitter = User.objects.create(username="sub_kyc", tenant=tenant_a)

    with tenant_context(tenant_a.id):
        WorkflowDefinition.objects.create(
            tenant=tenant_a, code="WF_KYC", version=1, is_active=True
        )
        application = _ready_application(
            tenant_a, client_a, product_a, reference="D_KYC", submitter=submitter,
        )
        with pytest.raises(WorkflowError, match="KYC"):
            submit_application(application, submitter)


def test_submit_rejects_amount_outside_product_bounds(tenant_a, product_a, client_a):
    submitter = User.objects.create(username="sub_bounds", tenant=tenant_a)

    with tenant_context(tenant_a.id):
        WorkflowDefinition.objects.create(
            tenant=tenant_a, code="WF_BOUNDS", version=1, is_active=True
        )
        application = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="D_BOUNDS",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("50"),  # < amount_min 1000
            duration_months=12,
            risk_level=1,
            submitted_by=submitter,
        )
        FinancialAnalysis.objects.create(
            tenant=tenant_a, application=application, is_reference=True,
        )
        with pytest.raises(WorkflowError, match="minimum"):
            submit_application(application, submitter)


def test_delegation_allows_user_can_act(tenant_a):
    role = Group.objects.create(name="Comité délégation")
    delegator = User.objects.create(username="delegator", tenant=tenant_a)
    delegator.groups.add(role)
    delegate = User.objects.create(username="delegate", tenant=tenant_a)
    outsider = User.objects.create(username="outsider", tenant=tenant_a)

    today = timezone.localdate()
    Delegation.objects.create(
        delegator=delegator,
        delegate=delegate,
        start_date=today - timedelta(days=1),
        end_date=today + timedelta(days=7),
        is_active=True,
    )

    with tenant_context(tenant_a.id):
        definition = WorkflowDefinition.objects.create(
            tenant=tenant_a, code="WF_DEL", version=1, is_active=True
        )
        step = ApprovalStep.objects.create(
            tenant=tenant_a,
            definition=definition,
            name="Comité",
            order=1,
            required_group=role,
            sla_hours=24,
        )

    assert user_can_act(delegator, step) is True
    assert user_can_act(delegate, step) is True
    assert user_can_act(outsider, step) is False


def test_apply_proposed_amount_updates_workflow_instance(
    tenant_a, product_a, client_a,
):
    from django.contrib.contenttypes.models import ContentType

    from apps.workflow.services import _apply_proposed_amount

    with tenant_context(tenant_a.id):
        definition = WorkflowDefinition.objects.create(
            tenant=tenant_a, code="WF_AMT", version=1, is_active=True
        )
        application = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="D-AMT",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("15000000"),
            duration_months=12,
            risk_level=1,
        )
        instance = WorkflowInstance.objects.create(
            tenant=tenant_a,
            definition=definition,
            content_type=ContentType.objects.get_for_model(CreditApplication),
            object_id=application.id,
            amount=application.amount_requested,
            risk_level=1,
        )
        _apply_proposed_amount(instance, Decimal("5000000"))
        instance.refresh_from_db()
        application.refresh_from_db()
        assert instance.amount == Decimal("5000000")
        assert application.amount_proposed == Decimal("5000000")
