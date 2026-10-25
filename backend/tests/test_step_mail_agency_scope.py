"""Ciblage des mails d'étape : Chef d'agence limité à l'agence du dossier."""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.contenttypes.models import ContentType

from apps.accounts.models import User
from apps.accounts.services import (
    CHEF_AGENCE_ROLE_NAME,
    CREDIT_COMMITTEE_FILIALE_ROLE_NAME,
    ensure_default_role_packs,
    get_or_create_tenant_role,
)
from apps.common.tenancy import tenant_context
from apps.credits.models import CreditApplication
from apps.notifications.models import TenantNotificationSettings
from apps.notifications.services import (
    _emails,
    _target_agency_id,
    _users_for_step,
    notify_step_opened,
)
from apps.tenants.models import Agency
from apps.workflow.models import ApprovalStep, WorkflowDefinition, WorkflowInstance

pytestmark = pytest.mark.django_db


def _chef(tenant, username, email, agency):
    ensure_default_role_packs(tenant)
    group, _ = get_or_create_tenant_role(tenant, CHEF_AGENCE_ROLE_NAME)
    user = User.objects.create_user(
        username=username,
        password="x",
        email=email,
        tenant=tenant,
        agency=agency,
        is_staff=True,
    )
    user.groups.add(group)
    user.agencies.add(agency)
    return user, group


def _app(tenant, client, product, agency, *, ref):
    return CreditApplication.objects.create(
        tenant=tenant,
        reference=ref,
        client=client,
        product=product,
        agency=agency,
        amount_requested=Decimal("1000000"),
        duration_months=12,
        status=CreditApplication.Status.IN_APPROVAL,
    )


def test_step_mail_only_chef_of_dossier_agency(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        ag_a = Agency.objects.create(tenant=tenant_a, code="AGA", name="Agence A")
        ag_b = Agency.objects.create(tenant=tenant_a, code="AGB", name="Agence B")
        chef_a, group = _chef(tenant_a, "chef_a", "chef.a@example.com", ag_a)
        chef_b, _ = _chef(tenant_a, "chef_b", "chef.b@example.com", ag_b)
        app = _app(tenant_a, client_a, product_a, ag_a, ref="DOS-MAIL-AG")
        definition = WorkflowDefinition.objects.create(
            tenant=tenant_a,
            code="WF-MAIL",
            name="Circuit mail",
            version=1,
            is_active=True,
            target_type=WorkflowDefinition.TargetType.CREDIT,
        )
        step = ApprovalStep.objects.create(
            tenant=tenant_a,
            definition=definition,
            name="Chef",
            order=1,
            required_group=group,
            sla_hours=24,
            step_kind=ApprovalStep.StepKind.DECISIONAL,
        )
        ct = ContentType.objects.get_for_model(CreditApplication)
        instance = WorkflowInstance.objects.create(
            tenant=tenant_a,
            definition=definition,
            content_type=ct,
            object_id=app.id,
            amount=app.amount_requested,
            risk_level=1,
            current_order=1,
            status=WorkflowInstance.Status.IN_PROGRESS,
        )
        prefs = TenantNotificationSettings.for_tenant(tenant_a)
        prefs.enabled = True
        prefs.notify_on_step = True
        prefs.save()

        users = list(_users_for_step(instance, step))
        emails = _emails(users)
        assert chef_a.email in emails
        assert chef_b.email not in emails
        assert _target_agency_id(instance) == ag_a.id

        with patch(
            "apps.notifications.services.send_email_for_tenant",
            return_value=None,
        ) as send:
            notify_step_opened(instance, step)
        assert send.called
        assert send.call_args.kwargs["recipients"] == ["chef.a@example.com"]


def test_committee_step_not_filtered_by_agency(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        ag_a = Agency.objects.create(tenant=tenant_a, code="AGA2", name="Agence A2")
        ag_b = Agency.objects.create(tenant=tenant_a, code="AGB2", name="Agence B2")
        ensure_default_role_packs(tenant_a)
        group, _ = get_or_create_tenant_role(tenant_a, CREDIT_COMMITTEE_FILIALE_ROLE_NAME)
        u1 = User.objects.create_user(
            username="com1",
            password="x",
            email="com1@example.com",
            tenant=tenant_a,
            agency=ag_a,
        )
        u2 = User.objects.create_user(
            username="com2",
            password="x",
            email="com2@example.com",
            tenant=tenant_a,
            agency=ag_b,
        )
        u1.groups.add(group)
        u2.groups.add(group)
        app = _app(tenant_a, client_a, product_a, ag_a, ref="DOS-MAIL-COM")
        definition = WorkflowDefinition.objects.create(
            tenant=tenant_a,
            code="WF-COM",
            name="Circuit comité",
            version=1,
            is_active=True,
            target_type=WorkflowDefinition.TargetType.CREDIT,
        )
        step = ApprovalStep.objects.create(
            tenant=tenant_a,
            definition=definition,
            name="Comité",
            order=1,
            required_group=group,
            sla_hours=24,
            step_kind=ApprovalStep.StepKind.DECISIONAL,
        )
        ct = ContentType.objects.get_for_model(CreditApplication)
        instance = WorkflowInstance.objects.create(
            tenant=tenant_a,
            definition=definition,
            content_type=ct,
            object_id=app.id,
            amount=app.amount_requested,
            risk_level=1,
            current_order=1,
            status=WorkflowInstance.Status.IN_PROGRESS,
        )
        emails = set(_emails(_users_for_step(instance, step)))
        assert emails == {"com1@example.com", "com2@example.com"}


def test_chef_agency_fallback_when_none_match(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        ag_a = Agency.objects.create(tenant=tenant_a, code="AGA3", name="Agence A3")
        ag_b = Agency.objects.create(tenant=tenant_a, code="AGB3", name="Agence B3")
        chef_b, group = _chef(tenant_a, "chef_only_b", "chef.only.b@example.com", ag_b)
        app = _app(tenant_a, client_a, product_a, ag_a, ref="DOS-MAIL-FB")
        definition = WorkflowDefinition.objects.create(
            tenant=tenant_a,
            code="WF-FB",
            name="Circuit fallback",
            version=1,
            is_active=True,
            target_type=WorkflowDefinition.TargetType.CREDIT,
        )
        step = ApprovalStep.objects.create(
            tenant=tenant_a,
            definition=definition,
            name="Chef",
            order=1,
            required_group=group,
            sla_hours=24,
            step_kind=ApprovalStep.StepKind.DECISIONAL,
        )
        ct = ContentType.objects.get_for_model(CreditApplication)
        instance = WorkflowInstance.objects.create(
            tenant=tenant_a,
            definition=definition,
            content_type=ct,
            object_id=app.id,
            amount=app.amount_requested,
            risk_level=1,
            current_order=1,
            status=WorkflowInstance.Status.IN_PROGRESS,
        )
        emails = _emails(_users_for_step(instance, step))
        assert emails == [chef_b.email]
