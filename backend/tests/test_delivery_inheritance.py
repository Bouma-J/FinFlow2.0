"""Héritage Groupe / filiale : résolution réelle, droits et preuves conservées."""
from copy import deepcopy
from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.capabilities import TENANT_ADMIN
from apps.accounts.services import capability_permissions, create_tenant_role
from apps.common.tenancy import tenant_context
from apps.configuration.models import ConfigurationProfile
from apps.configuration.services import application_configuration, freeze_configuration, resolve_context
from apps.credits.models import CreditApplication

pytestmark = pytest.mark.django_db


def published(tenant, code, overrides, **kwargs):
    return ConfigurationProfile.all_tenants.create(tenant=tenant, code=code, name=code,
        overrides=overrides, status="PUBLISHED", effective_from=timezone.now() - timedelta(days=1), **kwargs)


def authenticated(user):
    user.user_permissions.add(*Permission.objects.filter(content_type__app_label="configuration"))
    api = APIClient()
    api.force_authenticate(user)
    return api


def grant_tenant_admin(user):
    role = create_tenant_role(user.tenant, f"Configuration admin {user.username}")
    role.group.permissions.add(*capability_permissions({TENANT_ADMIN}))
    user.groups.add(role.group)


def test_group_defaults_then_tenant_overrides_and_locks(tenant_a, tenant_b):
    published(None, "group", {"policy": {"approval_validity_days": 45, "max_analysis_age_days": 30}},
              locked_keys=["policy.approval_validity_days"])
    published(tenant_a, "local", {"policy": {"approval_validity_days": 99, "max_analysis_age_days": 90}})
    a, b = resolve_context(tenant_a.pk, {}), resolve_context(tenant_b.pk, {})
    assert a["policy"]["approval_validity_days"] == b["policy"]["approval_validity_days"] == 45
    assert a["policy"]["max_analysis_age_days"] == 90
    assert b["policy"]["max_analysis_age_days"] == 30
    assert a["locked_keys"]["policy.approval_validity_days"].startswith("Groupe")
    assert a["ignored_overrides"][0]["key"] == "policy.approval_validity_days"
    assert a["sources"][0]["level"] == "GROUP"


def test_group_profile_not_bound_to_selected_tenant_on_save(tenant_a):
    with tenant_context(tenant_a.pk):
        obj = published(None, "group", {})
    obj.refresh_from_db()
    assert obj.tenant_id is None


def test_group_scope_and_candidate_preserve_tenant_series(tenant_a):
    published(None, "same-code", {"analysis": {"minimum_bank_statement_months": 3}})
    published(tenant_a, "same-code", {"policy": {"approval_validity_days": 18}})
    candidate = ConfigurationProfile(tenant=None, code="same-code", name="new-group", version=2,
                                   overrides={"analysis": {"minimum_bank_statement_months": 6}})
    result = resolve_context(tenant_a.pk, {}, candidate=candidate)
    assert result["analysis"]["minimum_bank_statement_months"] == 6
    assert result["policy"]["approval_validity_days"] == 18


def test_group_locks_only_apply_matching_client_scope(tenant_a):
    published(None, "salary", {"analysis": {"minimum_bank_statement_months": 6}},
              client_type="INDIVIDUAL", individual_profile="SALARIE", locked_keys=["analysis.minimum_bank_statement_months"])
    assert resolve_context(tenant_a.pk, {"client_type": "CORPORATE"})["locked_keys"] == {}
    assert resolve_context(tenant_a.pk, {"client_type": "INDIVIDUAL", "individual_profile": "SALARIE"})["analysis"]["minimum_bank_statement_months"] == 6


def test_local_user_cannot_read_or_mutate_group(tenant_a, django_user_model):
    user = django_user_model.objects.create(username="local-inheritance", tenant=tenant_a)
    grant_tenant_admin(user)
    api = authenticated(user)
    obj = published(None, "group", {})
    assert api.get("/api/v1/configuration-profiles/?scope=group").status_code == 403
    assert api.get(f"/api/v1/configuration-profiles/{obj.pk}/").status_code == 404
    assert api.post("/api/v1/configuration-profiles/?scope=group", {"code": "attack", "name": "Attack"}, format="json").status_code == 403


def test_group_publishing_four_eyes_and_local_reference_rejected(tenant_a, product_a, django_user_model):
    author = django_user_model.objects.create(username="group-author", is_group_level=True, is_staff=True)
    reviewer = django_user_model.objects.create(username="group-reviewer", is_group_level=True, is_staff=True)
    api = authenticated(author)
    path = "/api/v1/configuration-profiles/"
    payload = {"code": "group", "name": "Groupe", "reason": "Harmonisation", "overrides": {"policy": {"approval_validity_days": 30}}, "locked_keys": ["policy.approval_validity_days"]}
    response = api.post(path + "?scope=group", {**payload, "product": str(product_a.pk)}, format="json")
    assert response.status_code == 400
    response = api.post(path + "?scope=group", payload, format="json", HTTP_X_TENANT_ID=str(tenant_a.pk))
    assert response.status_code == 201, response.data
    obj = ConfigurationProfile.all_tenants.get(pk=response.data["id"])
    assert obj.tenant_id is None
    url = f"{path}{obj.pk}/"
    assert api.post(url + "submit/?scope=group", {}, format="json").status_code == 200
    assert api.post(url + "publish/?scope=group", {}, format="json").status_code == 403
    api = authenticated(reviewer)
    response = api.post(url + "publish/?scope=group", {}, format="json")
    assert response.status_code == 200, response.data
    assert resolve_context(tenant_a.pk, {})["policy"]["approval_validity_days"] == 30


@pytest.mark.parametrize("locked_keys", [["policy.unknown"], [True], "policy.approval_validity_days"])
def test_invalid_group_locks_rejected(locked_keys, django_user_model):
    user = django_user_model.objects.create(username="group-lock-test", is_group_level=True, is_staff=True)
    api = authenticated(user)
    response = api.post("/api/v1/configuration-profiles/?scope=group", {
        "code": "group", "name": "Groupe", "locked_keys": locked_keys,
        "overrides": {"policy": {"approval_validity_days": 30}},
    }, format="json")
    assert response.status_code == 400


def test_tenant_cannot_publish_locked_override(tenant_a, django_user_model):
    published(None, "group", {"policy": {"approval_validity_days": 30}}, locked_keys=["policy.approval_validity_days"])
    user = django_user_model.objects.create(username="tenant-publisher", tenant=tenant_a)
    grant_tenant_admin(user)
    api = authenticated(user)
    obj = ConfigurationProfile.all_tenants.create(tenant=tenant_a, code="local", name="Local", status="REVIEW",
                                                 overrides={"policy": {"approval_validity_days": 90}})
    response = api.post(f"/api/v1/configuration-profiles/{obj.pk}/publish/", {}, format="json")
    assert response.status_code == 400, response.data


def test_future_group_lock_blocks_local_publication(tenant_a, django_user_model):
    group = published(None, "future-group", {"policy": {"approval_validity_days": 30}}, locked_keys=["policy.approval_validity_days"])
    group.effective_from = timezone.now() + timedelta(days=30)
    group.save()
    user = django_user_model.objects.create(username="future-local-publisher", tenant=tenant_a)
    grant_tenant_admin(user)
    obj = ConfigurationProfile.all_tenants.create(tenant=tenant_a, code="local", name="Local", status="REVIEW",
                                                 overrides={"policy": {"approval_validity_days": 90}})
    response = authenticated(user).post(f"/api/v1/configuration-profiles/{obj.pk}/publish/", {}, format="json")
    assert response.status_code == 400, response.data


def test_preview_does_not_count_credit_without_view_permission(tenant_a, client_a, product_a, django_user_model):
    CreditApplication.all_tenants.create(tenant=tenant_a, client=client_a, product=product_a,
        reference="NO-COUNT", amount_requested="100000", duration_months=12)
    obj = ConfigurationProfile.all_tenants.create(tenant=tenant_a, code="local", name="Local", overrides={})
    user = django_user_model.objects.create(username="config-only", tenant=tenant_a, data_scope="TENANT")
    grant_tenant_admin(user)
    response = authenticated(user).post(f"/api/v1/configuration-profiles/{obj.pk}/preview/", {}, format="json")
    assert response.status_code == 200, response.data
    assert response.data["impact"]["editable_matching"] == response.data["impact"]["frozen_matching"] == 0


def test_group_revision_retains_locks(tenant_a, django_user_model):
    obj = published(None, "group", {"policy": {"approval_validity_days": 30}}, locked_keys=["policy.approval_validity_days"])
    user = django_user_model.objects.create(username="group-revise", is_group_level=True, is_staff=True)
    response = authenticated(user).post(f"/api/v1/configuration-profiles/{obj.pk}/revise/?scope=group", {}, format="json")
    assert response.status_code == 201, response.data
    assert response.data["locked_keys"] == obj.locked_keys


def test_frozen_group_values_survive_new_version_except_operational(tenant_a, client_a, product_a):
    published(None, "group", {"policy": {"approval_validity_days": 30, "setup_execution_role": "OPERATIONS"}})
    dossier = CreditApplication.all_tenants.create(tenant=tenant_a, client=client_a, product=product_a,
        reference="INHERIT", amount_requested="100000", duration_months=12)
    freeze_configuration(dossier)
    frozen = deepcopy(dossier.configuration_snapshot)
    dossier.status = "SUBMITTED"
    published(None, "group", {"policy": {"approval_validity_days": 90, "setup_execution_role": "CREDIT_ADMIN"}}, version=2)
    effective = application_configuration(dossier)
    assert effective["policy"]["approval_validity_days"] == 30
    assert effective["policy"]["setup_execution_role"] == "CREDIT_ADMIN"
    assert effective["fingerprint"] == frozen["fingerprint"]
    assert dossier.configuration_snapshot == frozen


def test_group_preview_uses_selected_tenant_and_is_read_only(tenant_a, django_user_model):
    published(tenant_a, "local", {"policy": {"max_analysis_age_days": 88}})
    obj = ConfigurationProfile.all_tenants.create(tenant=None, code="group", name="Group",
          overrides={"policy": {"max_analysis_age_days": 20}}, locked_keys=["policy.max_analysis_age_days"])
    user = django_user_model.objects.create(username="group-preview", is_group_level=True, is_staff=True)
    response = authenticated(user).post(f"/api/v1/configuration-profiles/{obj.pk}/preview/?scope=group", {},
                                       format="json", HTTP_X_TENANT_ID=str(tenant_a.pk))
    assert response.status_code == 200, response.data
    assert response.data["before"]["policy"]["max_analysis_age_days"] == 88
    assert response.data["after"]["policy"]["max_analysis_age_days"] == 20
    obj.refresh_from_db()
    assert obj.status == "DRAFT"
