"""Comité de crédit filiale / groupe : rôles, PV obligatoire."""
from decimal import Decimal

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import TenantRole
from apps.accounts.services import (
    CREDIT_COMMITTEE_FILIALE_ROLE_NAME,
    CREDIT_COMMITTEE_GROUP_ROLE_NAME,
    CREDIT_COMMITTEE_ROLE_NAME,
    GROUP_CREDIT_COMMITTEE_DJANGO_GROUP,
    ensure_default_role_packs,
    ensure_group_credit_committee_role,
    get_or_create_tenant_role,
    migrate_legacy_committee_role,
)
from apps.common.tenancy import tenant_context
from apps.documents.category_seed import ensure_committee_document_categories
from apps.documents.models import Document, DocumentCategory
from apps.workflow.models import ApprovalStep, ApprovalTask, WorkflowDefinition
from apps.workflow.services import (
    WorkflowError,
    application_has_committee_pv,
    is_credit_committee_step,
    process_decision,
    start_workflow,
    user_can_act,
)


@pytest.mark.django_db
def test_migrate_legacy_committee_renames_to_filiale(tenant_a):
    group, _ = get_or_create_tenant_role(tenant_a, CREDIT_COMMITTEE_ROLE_NAME)
    migrate_legacy_committee_role(tenant_a)
    assert not TenantRole.objects.filter(
        tenant=tenant_a, name=CREDIT_COMMITTEE_ROLE_NAME
    ).exists()
    role = TenantRole.objects.get(
        tenant=tenant_a, name=CREDIT_COMMITTEE_FILIALE_ROLE_NAME
    )
    assert role.group_id == group.id


@pytest.mark.django_db
def test_ensure_default_packs_creates_both_committees(tenant_a):
    ensure_default_role_packs(tenant_a)
    assert TenantRole.objects.filter(
        tenant=tenant_a, name=CREDIT_COMMITTEE_FILIALE_ROLE_NAME
    ).exists()
    assert TenantRole.objects.filter(
        tenant=tenant_a, name=CREDIT_COMMITTEE_GROUP_ROLE_NAME
    ).exists()
    g = ensure_group_credit_committee_role()
    assert g.name == GROUP_CREDIT_COMMITTEE_DJANGO_GROUP
    assert g.permissions.filter(codename="add_document").exists()


@pytest.mark.django_db
def test_committee_pv_required_on_approve(
    tenant_a, product_a, client_a, django_user_model
):
    ensure_default_role_packs(tenant_a)
    ensure_committee_document_categories(tenant_a)
    committee_g, _ = get_or_create_tenant_role(
        tenant_a, CREDIT_COMMITTEE_FILIALE_ROLE_NAME
    )
    user = django_user_model.objects.create_user(
        username="comite_fil",
        password="x",
        tenant=tenant_a,
    )
    user.groups.add(committee_g)
    submitter = django_user_model.objects.create_user(
        username="submitter_pv",
        password="x",
        tenant=tenant_a,
    )

    from apps.credits.models import CreditApplication

    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            client=client_a,
            product=product_a,
            amount_requested=Decimal("15000000"),
            duration_months=12,
            currency="XOF",
            status=CreditApplication.Status.IN_APPROVAL,
            created_by=submitter,
            submitted_by=submitter,
        )

        definition = WorkflowDefinition.objects.create(
            tenant=tenant_a,
            code="WF-COMITE-PV",
            name="Circuit comité PV",
            version=1,
            is_active=True,
        )
        step = ApprovalStep.objects.create(
            tenant=tenant_a,
            definition=definition,
            name="Comité de crédit filiale",
            order=1,
            required_group=committee_g,
            step_kind=ApprovalStep.StepKind.DECISIONAL,
            sla_hours=24,
        )
        assert is_credit_committee_step(step)

        instance = start_workflow(
            app, amount=app.amount_requested, definition=definition
        )
        task = instance.tasks.get(status=ApprovalTask.Status.PENDING)

        with pytest.raises(WorkflowError, match="PV_COMITE"):
            process_decision(
                task=task,
                user=user,
                decision=ApprovalTask.Status.APPROVED,
                opinion=ApprovalTask.Opinion.FAVORABLE,
                comment="ok",
            )

        cat = DocumentCategory.objects.get(tenant=tenant_a, code="PV_COMITE")
        ct = ContentType.objects.get_for_model(CreditApplication)
        Document.objects.create(
            tenant=tenant_a,
            category=cat,
            name="PV séance",
            file=SimpleUploadedFile("pv.pdf", b"%PDF-1.4 demo"),
            content_type=ct,
            object_id=app.pk,
            uploaded_by=user,
        )
        assert application_has_committee_pv(app)

        task.refresh_from_db()
        instance = process_decision(
            task=task,
            user=user,
            decision=ApprovalTask.Status.APPROVED,
            opinion=ApprovalTask.Opinion.FAVORABLE,
            comment="validé avec PV",
        )
        assert instance.status == instance.Status.APPROVED


@pytest.mark.django_db
def test_group_committee_user_can_act_on_filiale_step(
    tenant_a, django_user_model
):
    ensure_default_role_packs(tenant_a)
    filiale_group, _ = get_or_create_tenant_role(
        tenant_a, CREDIT_COMMITTEE_GROUP_ROLE_NAME
    )
    global_g = ensure_group_credit_committee_role()
    user = django_user_model.objects.create_user(
        username="comite_grp",
        password="x",
        is_group_level=True,
        is_staff=False,
    )
    user.groups.add(global_g)

    step = ApprovalStep(
        required_group=filiale_group,
        name="Comité de crédit groupe",
    )
    # Attach tenant_role reverse for detection
    assert user_can_act(user, step)
