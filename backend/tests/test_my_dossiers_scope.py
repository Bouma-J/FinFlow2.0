"""Périmètre Mes validations : CA / chef d'agence / file / étape."""
from decimal import Decimal

import pytest
from django.contrib.contenttypes.models import ContentType
from rest_framework.test import APIClient

from apps.accounts.models import DataScope, User
from apps.accounts.services import (
    CHARGE_AFFAIRE_ROLE_NAME,
    CHEF_AGENCE_ROLE_NAME,
    ensure_default_role_packs,
    get_or_create_tenant_role,
)
from apps.common.tenancy import tenant_context
from apps.credits.models import CreditApplication
from apps.tenants.models import Agency
from apps.workflow.models import (
    ApprovalStep,
    ApprovalTask,
    WorkflowDefinition,
    WorkflowInstance,
)

pytestmark = pytest.mark.django_db


def _auth(user, tenant):
    api = APIClient()
    api.force_authenticate(user)
    return api, {"HTTP_X_TENANT_ID": str(tenant.id), "HTTP_HOST": "localhost"}


def _role_user(tenant, username, role_name, *, agency=None):
    ensure_default_role_packs(tenant)
    group, _ = get_or_create_tenant_role(tenant, role_name)
    user = User.objects.create_user(
        username=username,
        password="x",
        tenant=tenant,
        agency=agency,
        data_scope=DataScope.AGENCY if agency else DataScope.TENANT,
        is_staff=True,
    )
    user.groups.add(group)
    if agency is not None:
        user.agencies.add(agency)
    return user, group


def _dossier(tenant, client, product, *, ref, agency, submitter, status="IN_APPROVAL"):
    return CreditApplication.objects.create(
        tenant=tenant,
        reference=ref,
        client=client,
        product=product,
        agency=agency,
        amount_requested=Decimal("1000000"),
        duration_months=12,
        status=status,
        created_by=submitter,
        submitted_by=submitter,
    )


def test_my_dossiers_scopes_ca_chef_and_queue(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        ag_a = Agency.objects.create(tenant=tenant_a, code="VA", name="Val A")
        ag_b = Agency.objects.create(tenant=tenant_a, code="VB", name="Val B")
        ca, _ = _role_user(tenant_a, "ca_val", CHARGE_AFFAIRE_ROLE_NAME, agency=ag_a)
        chef, chef_group = _role_user(
            tenant_a, "chef_val", CHEF_AGENCE_ROLE_NAME, agency=ag_a
        )
        other_ca, _ = _role_user(
            tenant_a, "ca_other", CHARGE_AFFAIRE_ROLE_NAME, agency=ag_b
        )

        definition = WorkflowDefinition.objects.create(
            tenant=tenant_a,
            code="WF-VAL",
            name="Circuit validations",
            version=1,
            is_active=True,
            target_type=WorkflowDefinition.TargetType.CREDIT,
        )
        step = ApprovalStep.objects.create(
            tenant=tenant_a,
            definition=definition,
            name="Validation chef",
            order=1,
            required_group=chef_group,
            sla_hours=24,
            step_kind=ApprovalStep.StepKind.DECISIONAL,
        )

        mine = _dossier(
            tenant_a, client_a, product_a, ref="DOS-CA-1", agency=ag_a, submitter=ca
        )
        other = _dossier(
            tenant_a,
            client_a,
            product_a,
            ref="DOS-CA-2",
            agency=ag_b,
            submitter=other_ca,
        )
        draft = _dossier(
            tenant_a,
            client_a,
            product_a,
            ref="DOS-DRAFT",
            agency=ag_a,
            submitter=ca,
            status="DRAFT",
        )
        ct = ContentType.objects.get_for_model(CreditApplication)
        for app in (mine, other, draft):
            inst = WorkflowInstance.objects.create(
                tenant=tenant_a,
                definition=definition,
                content_type=ct,
                object_id=app.id,
                amount=app.amount_requested,
                current_order=1,
                status=WorkflowInstance.Status.IN_PROGRESS,
            )
            if app.status != "DRAFT":
                ApprovalTask.objects.create(
                    tenant=tenant_a,
                    instance=inst,
                    step=step,
                    status=ApprovalTask.Status.PENDING,
                )

    ca_api, ca_headers = _auth(ca, tenant_a)
    ca_all = ca_api.get(
        "/api/v1/approval-tasks/my_dossiers/", {"queue": "all"}, **ca_headers
    )
    assert ca_all.status_code == 200, ca_all.content
    ca_refs = {r["reference"] for r in ca_all.json()["results"]}
    assert ca_refs == {"DOS-CA-1"}
    assert "DOS-DRAFT" not in ca_refs

    chef_api, chef_headers = _auth(chef, tenant_a)
    chef_all = chef_api.get(
        "/api/v1/approval-tasks/my_dossiers/", {"queue": "all"}, **chef_headers
    )
    assert chef_all.status_code == 200, chef_all.content
    chef_refs = {r["reference"] for r in chef_all.json()["results"]}
    assert chef_refs == {"DOS-CA-1"}

    chef_todo = chef_api.get(
        "/api/v1/approval-tasks/my_dossiers/",
        {"queue": "actionable"},
        **chef_headers,
    )
    assert {r["reference"] for r in chef_todo.json()["results"]} == {"DOS-CA-1"}
    row = chef_todo.json()["results"][0]
    assert row["is_actionable"] is True
    assert row["current_step_role"] == CHEF_AGENCE_ROLE_NAME
    assert "Chef" in (row["current_step_label"] or row["current_step_role"])

    by_step = chef_api.get(
        "/api/v1/approval-tasks/my_dossiers/",
        {"queue": "all", "step_role": CHEF_AGENCE_ROLE_NAME},
        **chef_headers,
    )
    assert {r["reference"] for r in by_step.json()["results"]} == {"DOS-CA-1"}
    assert any(
        opt["value"] == CHEF_AGENCE_ROLE_NAME
        for opt in by_step.json().get("step_options", [])
    )
