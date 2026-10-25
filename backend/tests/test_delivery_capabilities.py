"""Recette des fonctions explicites, des rôles libres et de leur isolation."""
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Permission
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.capabilities import (
    AGENCY_MANAGER, CREDIT_ADMIN, CREDIT_ANALYST, CREDIT_COMMITTEE,
    INTERNAL_CONTROL, OPERATIONS, TENANT_ADMIN,
    group_capabilities, group_has_capability, user_capabilities, user_has_capability,
)
from apps.accounts.models import TenantRole, User
from apps.accounts.serializers import TenantRoleSerializer
from apps.accounts.services import (
    CREDIT_ADMIN_ROLE_NAME, DEFAULT_ROLE_PACKS, ensure_filiale_admin_role,
    ensure_role_pack, create_tenant_role, capability_permissions,
    validate_sod_role_assignment,
)
from apps.accounts.views import GroupViewSet
from apps.common.tenancy import tenant_context

pytestmark = pytest.mark.django_db


def role(tenant, name, codes):
    item = create_tenant_role(tenant, name)
    item.group.permissions.add(*capability_permissions(codes))
    return item


def member(tenant, name, *roles):
    user = User.objects.create_user(username=name, tenant=tenant, data_scope="TENANT")
    user.groups.add(*(item.group for item in roles))
    return user


def test_name_never_grants_business_privilege(tenant_a):
    item = create_tenant_role(tenant_a, CREDIT_ADMIN_ROLE_NAME)
    user = member(tenant_a, "name_only", item)
    assert not user_has_capability(user, CREDIT_ADMIN)
    assert group_capabilities(item.group) == set()


def test_role_rename_keeps_capabilities(tenant_a):
    item = role(tenant_a, "Gestion crédit", {CREDIT_ADMIN})
    user = member(tenant_a, "renamed", item)
    serializer = TenantRoleSerializer(item, data={"name": "Contrôle des concours"}, partial=True)
    assert serializer.is_valid(), serializer.errors
    changed = serializer.save()
    assert serializer.data["capabilities"] == [CREDIT_ADMIN]
    assert changed.name == "Contrôle des concours"
    assert user_has_capability(user, CREDIT_ADMIN)


def test_foreign_tenant_and_inactive_users_have_no_function(tenant_a, tenant_b):
    item = role(tenant_b, "Contrôle", {CREDIT_ADMIN})
    user = member(tenant_a, "foreign", item)
    assert user_capabilities(user) == set()
    local = role(tenant_a, "Contrôle local", {CREDIT_ADMIN})
    user.groups.add(local.group)
    assert user_has_capability(user, CREDIT_ADMIN)
    user.is_active = False
    assert user_capabilities(user) == set()


def test_permission_alone_does_not_imply_function(tenant_a):
    item = create_tenant_role(tenant_a, "Traitement")
    item.group.permissions.add(Permission.objects.get(content_type__app_label="credits", codename="authorize_setup_creditapplication"))
    user = member(tenant_a, "permission_only", item)
    assert user.has_perm("credits.authorize_setup_creditapplication")
    assert not user_has_capability(user, CREDIT_ADMIN)


def test_standard_identity_survives_rename_and_sync(tenant_a):
    group = ensure_role_pack(tenant_a, CREDIT_ADMIN_ROLE_NAME, DEFAULT_ROLE_PACKS[CREDIT_ADMIN_ROLE_NAME])
    item = TenantRole.objects.get(group=group)
    item.name = "Administration des engagements"
    item.save(update_fields=["name"])
    group.permissions.remove(*capability_permissions({CREDIT_ADMIN}))
    fake = create_tenant_role(tenant_a, CREDIT_ADMIN_ROLE_NAME)
    same = ensure_role_pack(tenant_a, CREDIT_ADMIN_ROLE_NAME, DEFAULT_ROLE_PACKS[CREDIT_ADMIN_ROLE_NAME])
    assert same.pk == group.pk
    assert not group_has_capability(group, CREDIT_ADMIN)  # retrait explicite conservé
    assert group_capabilities(fake.group) == set()


def test_bootstrap_does_not_promote_custom_role_with_same_name(tenant_a):
    custom = create_tenant_role(tenant_a, CREDIT_ADMIN_ROLE_NAME)
    standard = ensure_role_pack(tenant_a, CREDIT_ADMIN_ROLE_NAME, DEFAULT_ROLE_PACKS[CREDIT_ADMIN_ROLE_NAME])
    assert standard.pk != custom.group_id
    assert group_has_capability(standard, CREDIT_ADMIN)
    assert not group_has_capability(custom.group, CREDIT_ADMIN)


def test_tenant_admin_not_automatically_credit_admin(tenant_a):
    group = ensure_filiale_admin_role(tenant_a)
    assert group_capabilities(group) == {TENANT_ADMIN}
    assert group.permissions.filter(codename="authorize_setup_creditapplication").exists()


def test_sod_is_independent_of_labels(tenant_a):
    analyst = role(tenant_a, "Équipe A", {CREDIT_ANALYST})
    committee = role(tenant_a, "Équipe B", {CREDIT_COMMITTEE})
    with pytest.raises(ValueError, match="Séparation des tâches"):
        validate_sod_role_assignment([analyst.group, committee.group])


def test_edit_role_cannot_bypass_sod_for_existing_users(tenant_a):
    analyst = role(tenant_a, "Analyse", {CREDIT_ANALYST})
    other = role(tenant_a, "Autre", set())
    member(tenant_a, "existing_member", analyst, other)
    serializer = TenantRoleSerializer(other, data={"capabilities": [CREDIT_COMMITTEE]}, partial=True)
    assert serializer.is_valid(), serializer.errors
    with pytest.raises(Exception, match="Séparation des tâches"):
        serializer.save()
    assert group_capabilities(other.group) == set()


def test_sod_rejects_incoherent_function_in_one_role(tenant_a):
    item = role(tenant_a, "Réservé", set())
    serializer = TenantRoleSerializer(item, data={"capabilities": [OPERATIONS, INTERNAL_CONTROL]}, partial=True)
    assert serializer.is_valid()
    with pytest.raises(Exception, match="Séparation des tâches"):
        serializer.save()


def test_permission_edit_preserves_functions_unless_explicit(tenant_a):
    item = role(tenant_a, "Contrôle", {CREDIT_ADMIN})
    serializer = TenantRoleSerializer(item, data={"permissions": []}, partial=True)
    assert serializer.is_valid()
    serializer.save()
    assert group_has_capability(item.group, CREDIT_ADMIN)
    serializer = TenantRoleSerializer(item, data={"capabilities": []}, partial=True)
    assert serializer.is_valid()
    serializer.save()
    assert group_capabilities(item.group) == set()


def test_unknown_capability_refused(tenant_a):
    serializer = TenantRoleSerializer(data={"name": "Inconnu", "capabilities": ["invented"]})
    assert not serializer.is_valid()
    assert "capabilities" in serializer.errors


def test_role_api_model_right_and_tenant_isolation(tenant_a, tenant_b):
    local = role(tenant_a, "Local", set())
    foreign = role(tenant_b, "Étranger", set())
    actor = member(tenant_a, "api_actor")
    actor.user_permissions.add(Permission.objects.get(content_type__app_label="accounts", codename="view_tenantrole"))
    factory = APIRequestFactory()
    request = factory.get("/api/roles/capabilities/")
    force_authenticate(request, actor)
    with tenant_context(tenant_a.pk):
        response = GroupViewSet.as_view({"get": "capabilities"})(request)
    assert response.status_code == 200
    assert any(row["code"] == CREDIT_ADMIN for row in response.data)
    for item, expected in ((local, 403), (foreign, 403)):
        request = factory.patch(f"/api/roles/{item.group_id}/", {"capabilities": [CREDIT_ADMIN]}, format="json")
        force_authenticate(request, actor)
        with tenant_context(tenant_a.pk):
            response = GroupViewSet.as_view({"patch": "partial_update"})(request, pk=str(item.group_id))
        assert response.status_code == expected
    actor.user_permissions.add(Permission.objects.get(content_type__app_label="accounts", codename="change_tenantrole"))
    actor = User.objects.get(pk=actor.pk)
    request = factory.patch(f"/api/roles/{foreign.group_id}/", {"name": "Invisible"}, format="json")
    force_authenticate(request, actor)
    with tenant_context(tenant_a.pk):
        response = GroupViewSet.as_view({"patch": "partial_update"})(request, pk=str(foreign.group_id))
    assert response.status_code == 404
    request = factory.patch(f"/api/roles/{local.group_id}/", {"name": "Local modifié"}, format="json")
    force_authenticate(request, actor)
    with tenant_context(tenant_a.pk):
        response = GroupViewSet.as_view({"patch": "partial_update"})(request, pk=str(local.group_id))
    assert response.status_code == 403


def test_role_options_are_compact_and_tenant_scoped(tenant_a, tenant_b):
    local = role(tenant_a, "Local", {CREDIT_ADMIN})
    role(tenant_b, "Foreign", {CREDIT_ADMIN})
    actor = member(tenant_a, "options_reader")
    actor.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="accounts", codename="view_tenantrole"
        )
    )
    request = APIRequestFactory().get("/api/roles/options/")
    force_authenticate(request, actor)
    with tenant_context(tenant_a.pk):
        response = GroupViewSet.as_view({"get": "options"})(request)

    assert response.status_code == 200
    rows = response.data["results"]
    assert len(rows) == 1
    assert rows[0]["id"] == local.group_id
    assert rows[0]["permission_count"] == local.group.permissions.count()
    assert "permissions" not in rows[0]
    assert "permissions_detail" not in rows[0]


def test_notifications_recognize_renamed_agency_function(tenant_a):
    from apps.notifications.services import _group_is_chef_agence
    item = role(tenant_a, "Responsable point de vente", {AGENCY_MANAGER})
    assert _group_is_chef_agence(item.group)
    fake = create_tenant_role(tenant_a, "Chef d'agence")
    assert not _group_is_chef_agence(fake.group)


def test_group_reader_is_not_collection_administrator():
    from apps.collections.access import is_finflow_admin
    user = User.objects.create_user(username="group_reader", is_group_level=True, is_staff=False)
    assert not is_finflow_admin(user)


def test_collection_function_obeys_tenant_and_rename(tenant_a, tenant_b):
    from apps.accounts.capabilities import COLLECTION_OFFICER
    from apps.collections.access import can_operate_collection_case
    from apps.collections.models import CollectionTranche
    item = role(tenant_a, "Recouvrement amiable", {COLLECTION_OFFICER})
    user = member(tenant_a, "collector", item)
    case = SimpleNamespace(tenant_id=tenant_a.pk, stage="AMICABLE", tranche=SimpleNamespace(owner_kind=CollectionTranche.OwnerKind.COLLECTION))
    assert can_operate_collection_case(user, case)
    case.tenant_id = tenant_b.pk
    assert not can_operate_collection_case(user, case)


def test_upgrade_preserves_custom_setup_permissions(tenant_a):
    import importlib
    from django.apps import apps
    from django.db import connection
    reviewer = create_tenant_role(tenant_a, "Back office crédit renommé")
    reviewer.group.permissions.add(Permission.objects.get(content_type__app_label="credits", codename="review_setup_creditapplication"))
    operations = create_tenant_role(tenant_a, "Cellule intégration")
    operations.group.permissions.add(Permission.objects.get(content_type__app_label="credits", codename="execute_setup_operations"))
    migration = importlib.import_module("apps.accounts.migrations.0011_provision_business_capabilities")
    migration.provision(apps, SimpleNamespace(connection=connection))
    assert group_has_capability(reviewer.group, CREDIT_ADMIN)
    assert group_has_capability(operations.group, OPERATIONS)


def test_django_admin_rejects_sod_and_foreign_roles(tenant_a, tenant_b):
    from apps.accounts.admin import AccountChangeForm, BusinessGroupForm
    analyst = role(tenant_a, "Analyste", {CREDIT_ANALYST})
    committee = role(tenant_a, "Comité", set())
    user = member(tenant_a, "admin_sod", analyst, committee)
    permissions = list(capability_permissions({CREDIT_COMMITTEE}).values_list("pk", flat=True))
    form = BusinessGroupForm(instance=committee.group, data={"name": committee.group.name, "permissions": permissions})
    assert not form.is_valid()
    assert "permissions" in form.errors
    foreign = role(tenant_b, "Autre filiale", {OPERATIONS})
    form = AccountChangeForm(instance=user, data={"username": user.username, "tenant": str(tenant_a.pk), "data_scope": "TENANT", "groups": [foreign.group_id], "date_joined": user.date_joined, "is_active": True})
    assert not form.is_valid()
    assert any("n'appartient pas" in error for error in form.non_field_errors())
