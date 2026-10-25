"""Habilitations, paramètres et fenêtres d'action : même règle en API et métier."""

from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Delegation, User
from apps.accounts.services import (
    CHARGE_AFFAIRE_ROLE_NAME,
    FILIALE_ADMIN_ROLE_NAME,
    LECTEUR_ROLE_NAME,
    create_tenant_role,
    ensure_default_role_packs,
    get_or_create_tenant_role,
)
from apps.common.tenancy import tenant_context
from apps.credits.access import can_contribute
from apps.credits.governance import evidence_fingerprint, freeze_approval, setup_checks
from apps.credits.instruction_policy import build_readiness
from apps.credits.models import CreditApplication, CreditInstructionPolicy
from apps.sureties.models import Surety, SuretyEngagement
from apps.tenants.models import Agency
from apps.workflow.models import (
    ApprovalStep,
    ApprovalTask,
    WorkflowDefinition,
    WorkflowInstance,
)
from apps.workflow.serializers import ApprovalStepSerializer
from apps.workflow.services import effective_group_ids, user_can_act

pytestmark = pytest.mark.django_db


@pytest.fixture
def configuration(tenant_a, tenant_b, client_a, product_a):
    ensure_default_role_packs(tenant_a)
    agency = Agency.objects.create(tenant=tenant_a, code="VERIFY", name="Agence")
    other_agency = Agency.objects.create(tenant=tenant_b, code="OTHER", name="Autre")
    admin = User.objects.create(
        username="verify_admin", tenant=tenant_a, agency=agency, data_scope="TENANT"
    )
    admin.groups.add(get_or_create_tenant_role(tenant_a, FILIALE_ADMIN_ROLE_NAME)[0])
    with tenant_context(tenant_a.pk):
        application = CreditApplication.objects.create(
            tenant=tenant_a,
            client=client_a,
            product=product_a,
            reference="VERIFY",
            amount_requested=Decimal("100000"),
            duration_months=12,
            agency=agency,
            created_by=admin,
            status="APPROVED",
            decision_date=timezone.localdate(),
        )
    api = APIClient()
    api.force_authenticate(admin)
    return admin, agency, other_agency, application, api


@pytest.mark.parametrize(
    "attack", ["create_group", "create_foreign", "elevate", "move"]
)
def test_filiale_admin_cannot_escape_account_scope(configuration, tenant_b, attack):
    admin, agency, other_agency, _, api = configuration
    if attack.startswith("create"):
        data = {
            "username": "escape",
            "email": "demo@example.com",
            "password_delivery": "manual",
            "password": "TestLocal2026!",
            "password_confirm": "TestLocal2026!",
        }
        if attack == "create_group":
            data.update(is_group_level=True)
        else:
            data.update(tenant=str(tenant_b.pk), agency=str(other_agency.pk))
        response = api.post("/api/v1/users/", data, format="json")
        assert not User.objects.filter(username="escape").exists()
    else:
        data = (
            {"is_group_level": True, "tenant": None}
            if attack == "elevate"
            else {"tenant": str(tenant_b.pk), "agency": str(other_agency.pk)}
        )
        response = api.patch(f"/api/v1/users/{admin.pk}/", data, format="json")
        admin.refresh_from_db()
        assert admin.tenant_id == agency.tenant_id and not admin.is_group_level
    assert response.status_code == 400, response.content


def test_policy_read_is_business_permission_and_write_is_admin_only(configuration):
    _, agency, _, _, _ = configuration
    user = User.objects.create(
        username="reader_policy", tenant=agency.tenant, agency=agency
    )
    user.groups.add(
        get_or_create_tenant_role(agency.tenant, CHARGE_AFFAIRE_ROLE_NAME)[0]
    )
    api = APIClient()
    api.force_authenticate(user)
    assert api.get("/api/v1/credit-instruction-policy/current/").status_code == 200
    assert (
        api.patch(
            "/api/v1/credit-instruction-policy/current/",
            {"require_setup_request": True},
            format="json",
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "action",
    ["submit", "disburse", "request-disburse", "setup-review", "reexamine", "cancel"],
)
def test_reader_cannot_perform_credit_mutations(configuration, action):
    _, agency, _, application, _ = configuration
    user = User.objects.create(
        username="read_only", tenant=agency.tenant, agency=agency, data_scope="TENANT"
    )
    user.groups.add(get_or_create_tenant_role(agency.tenant, LECTEUR_ROLE_NAME)[0])
    api = APIClient()
    api.force_authenticate(user)
    response = api.post(
        f"/api/v1/credit-applications/{application.pk}/{action}/", {}, format="json"
    )
    assert response.status_code == 403, response.content


def test_readiness_exposes_every_business_policy_field(configuration):
    _, agency, _, application, _ = configuration
    with tenant_context(agency.tenant_id):
        policy = CreditInstructionPolicy.objects.create(
            tenant=agency.tenant,
            require_setup_request=True,
            require_setup_four_eyes=True,
            require_final_review=True,
        )
        result = build_readiness(application)["policy"]
        expected = {field.name for field in policy._meta.fields} - {
            "id",
            "tenant",
            "created_at",
            "updated_at",
        }
        assert set(result) == expected
        assert result["require_setup_request"] and result["require_setup_four_eyes"]


def test_profile_does_not_serve_revoked_permission_from_cache(configuration):
    _, agency, _, _, _ = configuration
    user = User.objects.create(
        username="revoke_live", tenant=agency.tenant, agency=agency
    )
    permission = Permission.objects.get(
        content_type__app_label="credits", codename="disburse_creditapplication"
    )
    user.user_permissions.add(permission)
    api = APIClient()
    api.force_authenticate(user)
    assert (
        "credits.disburse_creditapplication"
        in api.get("/api/v1/users/me/").json()["permissions"]
    )
    user.user_permissions.remove(permission)
    api.force_authenticate(User.objects.get(pk=user.pk))
    assert (
        "credits.disburse_creditapplication"
        not in api.get("/api/v1/users/me/").json()["permissions"]
    )


def test_step_rejects_foreign_role_and_moving_between_definitions(
    configuration, tenant_b
):
    _, agency, _, _, _ = configuration
    foreign = create_tenant_role(tenant_b, "Étranger")
    with tenant_context(agency.tenant_id):
        definition = WorkflowDefinition.objects.create(
            tenant=agency.tenant, code="VERIFY"
        )
        serializer = ApprovalStepSerializer(
            data={
                "definition": str(definition.pk),
                "name": "Décision",
                "required_group": foreign.group_id,
                "order": 1,
            }
        )
        assert not serializer.is_valid()
        assert "required_group" in serializer.errors


def test_scoped_delegation_consistent_in_inbox_contribution_and_decision(configuration):
    owner, agency, _, application, _ = configuration
    role = create_tenant_role(agency.tenant, "Valideur recette")
    owner.groups.add(role.group)
    deputy = User.objects.create(
        username="deputy", tenant=agency.tenant, agency=agency, data_scope="TENANT"
    )
    deputy.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="workflow", codename="view_approvaltask"
        )
    )
    today = timezone.localdate()
    grant = Delegation.objects.create(
        delegator=owner,
        delegate=deputy,
        start_date=today,
        end_date=today + timedelta(days=1),
        max_amount=Decimal("50000"),
    )
    with tenant_context(agency.tenant_id):
        application.status = "IN_APPROVAL"
        application.save(update_fields=["status"])
        definition = WorkflowDefinition.objects.create(
            tenant=agency.tenant, code="DELEGATE"
        )
        step = ApprovalStep.objects.create(
            tenant=agency.tenant,
            definition=definition,
            name="Décision",
            required_group=role.group,
            order=1,
        )
        instance = WorkflowInstance.objects.create(
            tenant=agency.tenant,
            definition=definition,
            content_type=ContentType.objects.get_for_model(application),
            object_id=application.pk,
            current_order=1,
            amount=Decimal("100000"),
        )
        ApprovalTask.objects.create(tenant=agency.tenant, instance=instance, step=step)
        assert not user_can_act(deputy, step, application, instance.amount)
        assert not can_contribute(application, deputy)
    api = APIClient()
    api.force_authenticate(deputy)
    assert api.get("/api/v1/approval-tasks/my_pending/").json()["count"] == 0
    grant.max_amount = Decimal("200000")
    grant.save(update_fields=["max_amount"])
    with tenant_context(agency.tenant_id):
        assert can_contribute(application, deputy)
    assert api.get("/api/v1/approval-tasks/my_pending/").json()["count"] == 1
    owner.is_active = False
    owner.save(update_fields=["is_active"])
    assert role.group_id not in effective_group_ids(deputy)


def test_expired_identity_and_missing_decision_date_obey_policy(configuration):
    _, agency, _, application, _ = configuration
    with tenant_context(agency.tenant_id):
        policy = CreditInstructionPolicy.objects.create(
            tenant=agency.tenant, approval_validity_days=30
        )
        application.client.id_document_expiry_date = timezone.localdate() - timedelta(
            days=1
        )
        application.client.save(update_fields=["id_document_expiry_date"])
        assert any("identité" in failure for failure in setup_checks(application))
        policy.recheck_kyc_on_setup = False
        policy.save()
        assert not any("identité" in failure for failure in setup_checks(application))
        application.decision_date = None
        assert any(
            "date de décision" in failure for failure in setup_checks(application)
        )


def test_reduced_surety_invalidates_approval_and_final_review(configuration):
    _, agency, _, application, _ = configuration
    with tenant_context(agency.tenant_id):
        surety = Surety.objects.create(tenant=agency.tenant, last_name="Caution")
        grant = SuretyEngagement.objects.create(
            tenant=agency.tenant,
            application=application,
            surety=surety,
            amount=Decimal("100000"),
        )
        freeze_approval(application)
        before = evidence_fingerprint(application)
        # Ce test is centré sur l'engagement de caution. Les prérequis de
        # connecteur et de référentiel CBS relèvent d'autres scénarios.
        assert not any("caution" in failure.casefold() for failure in setup_checks(application))
        grant.amount = Decimal("50000")
        grant.save(update_fields=["amount"])
        assert any("caution" in failure for failure in setup_checks(application))
        assert evidence_fingerprint(application) != before


def test_audit_command_is_read_only(configuration):
    import json

    before = (User.objects.count(), CreditInstructionPolicy.all_tenants.count())
    output = StringIO()
    call_command("audit_business_configuration", stdout=output)
    assert json.loads(output.getvalue())["tenants"]
    assert before == (User.objects.count(), CreditInstructionPolicy.all_tenants.count())


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/credit-instruction-policy/current/",
        "/api/v1/analysis-thresholds/current/",
        "/api/v1/notification-settings/current/",
    ],
)
def test_group_scope_does_not_grant_configuration_write(configuration, path):
    _, agency, _, _, _ = configuration
    user = User.objects.create(username="group_consultation", is_group_level=True)
    api = APIClient()
    api.force_authenticate(user)
    response = api.patch(
        path, {}, format="json", HTTP_X_TENANT_ID=str(agency.tenant_id)
    )
    assert response.status_code == 403, response.content


@pytest.mark.parametrize(
    "path", ["/api/v1/tenants/", "/api/v1/users/provision-filiale-admin/"]
)
def test_group_reader_cannot_create_tenant_or_provision_admin(path):
    user = User.objects.create(username="group_read_only", is_group_level=True)
    api = APIClient()
    api.force_authenticate(user)
    assert api.post(path, {}, format="json").status_code == 403


def test_decision_respects_agency_scope(configuration):
    owner, agency, _, application, _ = configuration
    alternate = Agency.objects.create(
        tenant=agency.tenant, code="SECOND", name="Autre agence"
    )
    role = create_tenant_role(agency.tenant, "Validateur agence")
    actor = User.objects.create(
        username="other_branch",
        tenant=agency.tenant,
        agency=alternate,
        data_scope="AGENCY",
    )
    actor.groups.add(role.group)
    with tenant_context(agency.tenant_id):
        definition = WorkflowDefinition.objects.create(
            tenant=agency.tenant, code="AGENCY"
        )
        step = ApprovalStep.objects.create(
            tenant=agency.tenant,
            definition=definition,
            name="Décision",
            required_group=role.group,
        )
        assert not user_can_act(actor, step, application, Decimal("100000"))
        actor.agencies.add(agency)
        assert user_can_act(actor, step, application, Decimal("100000"))


def test_committee_pv_requires_real_current_and_policy_verified_file(configuration):
    from apps.documents.models import Document, DocumentCategory
    from apps.workflow.services import application_has_committee_pv

    _, agency, _, application, _ = configuration
    with tenant_context(agency.tenant_id):
        category = DocumentCategory.objects.get(tenant=agency.tenant, code="PV_COMITE")
        document = Document.objects.create(
            tenant=agency.tenant,
            name="PV",
            category=category,
            content_type=ContentType.objects.get_for_model(application),
            object_id=application.pk,
        )
        assert not application_has_committee_pv(application)
        document.file = "pv.pdf"
        document.save()
        assert application_has_committee_pv(application)
        policy = CreditInstructionPolicy.objects.create(
            tenant=agency.tenant, require_verified_documents=True
        )
        assert not application_has_committee_pv(application)
        document.verification_status = "VERIFIED"
        document.save()
        assert application_has_committee_pv(application)
        document.expiry_date = timezone.localdate() - timedelta(days=1)
        document.save()
        assert not application_has_committee_pv(application)


def test_demo_actors_have_distinct_compatible_roles(configuration):
    from apps.common.demo_users import ensure_demo_business_users
    from apps.accounts.services import validate_sod_role_assignment

    _, agency, _, _, _ = configuration
    names = ensure_demo_business_users(agency.tenant, agency)
    assert len(names) == 10
    for user in User.objects.filter(username__in=names):
        validate_sod_role_assignment(user.groups.all())
        assert user.groups.count() == 1


def test_named_cbs_configuration_is_applied_to_requested_connector(configuration):
    from apps.corebanking.models import CoreBankingConnector
    from apps.corebanking.perfect_defaults import ensure_perfect_connector

    _, agency, _, _, _ = configuration
    with tenant_context(agency.tenant_id):
        live = CoreBankingConnector.objects.create(
            tenant=agency.tenant, name="Existant", protocol="REST"
        )
        target, created = ensure_perfect_connector(
            agency.tenant, name="Demo ciblée", demo=True
        )
        assert created and target.pk != live.pk
        assert target.name == "Demo ciblée"
        assert target.mapping_rules["force_simulate"] is True
        live.refresh_from_db()
        assert live.mapping_rules == {}


@pytest.mark.parametrize(
    "resource", ["workflow-instances", "approval-tasks", "approval-conditions"]
)
def test_workflow_reads_cannot_bypass_credit_agency_scope(configuration, resource):
    from apps.workflow.models import ApprovalCondition

    owner, agency, _, application, _ = configuration
    other = Agency.objects.create(
        tenant=agency.tenant, code="HIDDEN", name="Autre agence"
    )
    reader = User.objects.create(
        username="workflow_reader",
        tenant=agency.tenant,
        agency=other,
        data_scope="AGENCY",
    )
    role = get_or_create_tenant_role(agency.tenant, LECTEUR_ROLE_NAME)[0]
    reader.groups.add(role)
    with tenant_context(agency.tenant_id):
        definition = WorkflowDefinition.objects.create(
            tenant=agency.tenant, code="SCOPED-READ"
        )
        step = ApprovalStep.objects.create(
            tenant=agency.tenant,
            definition=definition,
            name="Étape",
            required_group=role,
        )
        instance = WorkflowInstance.objects.create(
            tenant=agency.tenant,
            definition=definition,
            content_type=ContentType.objects.get_for_model(application),
            object_id=application.pk,
        )
        task = ApprovalTask.objects.create(
            tenant=agency.tenant, step=step, instance=instance
        )
        condition = ApprovalCondition.objects.create(
            tenant=agency.tenant,
            application=application,
            task=task,
            description="Réserve",
        )
    obj = {
        "workflow-instances": instance,
        "approval-tasks": task,
        "approval-conditions": condition,
    }[resource]
    api = APIClient()
    api.force_authenticate(reader)
    assert api.get(f"/api/v1/{resource}/").json()["count"] == 0
    assert api.get(f"/api/v1/{resource}/{obj.pk}/").status_code == 404
    reader.agencies.add(agency)
    assert api.get(f"/api/v1/{resource}/").json()["count"] == 1
