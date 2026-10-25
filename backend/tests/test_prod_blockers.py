"""Non-régression des deux défauts bloquants relevés en simulation de production.

1. `user_role_label` concaténait les noms *techniques* des groupes Django
   (`__ff_<filiale>__<hash>`, 55 caractères) : au-delà de 2 rôles le libellé
   dépassait la colonne `varchar(150)` et la création d'une analyse financière
   renvoyait 500 (`DataError`) sous PostgreSQL.
2. La suppression d'une filiale échouait en 500 (`IntegrityError`) : la cascade
   auditait chaque entité fille en pointant sur une filiale absente au COMMIT.
"""
from decimal import Decimal

from django.contrib.auth.models import Group
from rest_framework.test import APIClient

import pytest

from apps.accounts.models import TenantRole, User
from apps.accounts.services import create_tenant_role
from apps.accounts.utils import user_role_label
from apps.audit.models import AuditLog
from apps.catalog.models import ProductCategory
from apps.clients.models import Client
from apps.common.tenancy import tenant_context
from apps.credits.models import CreditApplication, FinancialAnalysis
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db

AUTHOR_ROLE_MAX = FinancialAnalysis._meta.get_field("author_role").max_length


def _fits_column(label):
    return len(label) <= AUTHOR_ROLE_MAX


def test_role_label_uses_business_names_not_technical_groups(tenant_a):
    role = create_tenant_role(tenant_a, "Analyste crédit et risque")
    user = User.objects.create_user(
        username="lbl_one", password="FinFlow2026!", tenant=tenant_a
    )
    user.groups.add(role.group)

    label = user_role_label(user)
    assert label == "Analyste crédit et risque"
    assert "__ff_" not in label


def test_role_label_fits_column_with_many_roles(tenant_a):
    """4 rôles représentaient 226 caractères de noms techniques avant correctif."""
    names = [
        "Analyste crédit et risque",
        "Chargé d'affaire",
        "Chef d'agence",
        "Responsable crédit et risque",
    ]
    user = User.objects.create_user(
        username="lbl_many", password="FinFlow2026!", tenant=tenant_a
    )
    for name in names:
        user.groups.add(create_tenant_role(tenant_a, name).group)

    label = user_role_label(user)
    assert _fits_column(label)
    assert "__ff_" not in label
    for name in names:
        assert name in label


def test_role_label_caps_and_counts_omitted_roles(tenant_a):
    user = User.objects.create_user(
        username="lbl_flood", password="FinFlow2026!", tenant=tenant_a
    )
    for index in range(12):
        role = create_tenant_role(tenant_a, f"Responsable métier numéro {index:02d}")
        user.groups.add(role.group)

    label = user_role_label(user)
    assert _fits_column(label)
    # Les rôles non retenus sont comptés plutôt que silencieusement perdus.
    assert label.endswith(")")
    assert "(+" in label


def test_role_label_keeps_groups_without_tenant_role(tenant_a):
    """Un groupe Django hors référentiel filiale reste lisible."""
    user = User.objects.create_user(
        username="lbl_plain", password="FinFlow2026!", tenant=tenant_a
    )
    user.groups.add(Group.objects.create(name="Support niveau 2"))

    assert user_role_label(user) == "Support niveau 2"


def test_role_label_falls_back_on_group_level_and_superuser():
    admin = User.objects.create_user(
        username="lbl_su", password="FinFlow2026!", is_superuser=True
    )
    assert user_role_label(admin) == "Administrateur"

    group_user = User.objects.create_user(
        username="lbl_grp", password="FinFlow2026!", is_group_level=True
    )
    assert user_role_label(group_user) == "Responsable Groupe"


def test_financial_analysis_author_role_never_overflows(
    tenant_a, product_a, client_a
):
    """Le profil figé à la création tient dans la colonne, quel que soit l'auteur."""
    user = User.objects.create_user(
        username="fa_multi", password="FinFlow2026!", tenant=tenant_a
    )
    for index in range(6):
        user.groups.add(
            create_tenant_role(tenant_a, f"Responsable transverse {index}").group
        )

    with tenant_context(tenant_a.id):
        application = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="FA-ROLE-1",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("500000"),
            duration_months=12,
        )
        analysis = FinancialAnalysis.objects.create(
            tenant=tenant_a,
            application=application,
            author_role=user_role_label(user),
            created_by=user,
        )

    assert _fits_column(analysis.author_role)
    assert "__ff_" not in analysis.author_role


def test_deleting_tenant_detaches_audit_entries(tenant_b):
    """La cascade d'audit ne doit plus violer la clé étrangère filiale."""
    with tenant_context(tenant_b.id):
        category = ProductCategory.objects.create(
            tenant=tenant_b, code="DELCAT", label="Catégorie à supprimer"
        )
    category_pk = str(category.pk)
    tenant_pk = tenant_b.pk

    tenant_b.delete()

    assert not Tenant.objects.filter(pk=tenant_pk).exists()
    entry = AuditLog.objects.filter(
        action=AuditLog.Action.DELETE,
        model_label="catalog.ProductCategory",
        object_id=category_pk,
    ).first()
    assert entry is not None, "la suppression doit rester auditée"
    assert entry.tenant_id is None
    # L'appartenance reste tracée dans les données de l'entrée.
    assert entry.changes.get("tenant_id") == str(tenant_pk)
    assert not AuditLog.objects.filter(tenant_id=tenant_pk).exists()


def _group_admin_client(username):
    admin = User.objects.create_user(
        username=username, password="FinFlow2026!", is_group_level=True, is_staff=True
    )
    api = APIClient()
    api.force_authenticate(admin)
    return api


def test_delete_empty_tenant_via_api(tenant_a):
    api = _group_admin_client("del_grp_ok")

    res = api.delete(f"/api/v1/tenants/{tenant_a.id}/", HTTP_HOST="localhost")
    assert res.status_code == 204, res.content
    assert not Tenant.objects.filter(pk=tenant_a.id).exists()


def test_tenant_role_referential_alone_does_not_block_deletion(tenant_a):
    """Une filiale simplement provisionnée (rôles, référentiels) reste supprimable."""
    create_tenant_role(tenant_a, "Chef d'agence")
    assert TenantRole.objects.filter(tenant=tenant_a).exists()

    api = _group_admin_client("del_grp_boot")
    res = api.delete(f"/api/v1/tenants/{tenant_a.id}/", HTTP_HOST="localhost")
    assert res.status_code == 204, res.content


def test_tenant_with_business_data_is_not_deletable(tenant_a, client_a):
    api = _group_admin_client("del_grp_ko")

    res = api.delete(f"/api/v1/tenants/{tenant_a.id}/", HTTP_HOST="localhost")
    assert res.status_code == 400, res.content
    body = res.content.decode()
    assert "clients" in body and "sactivez" in body
    assert Tenant.objects.filter(pk=tenant_a.id).exists()
    with tenant_context(tenant_a.id):
        assert Client.objects.filter(pk=client_a.pk).exists()
