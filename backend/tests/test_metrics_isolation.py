"""Cloisonnement des métriques d'exploitation et de Django admin.

`is_staff` ouvre les menus Administration SPA d'une filiale. Il ne donne
ni les agrégats inter-filiales (`/metrics/`) ni l'accès à `/django-admin/`,
dont les ModelAdmin ne sont pas scopés.
"""
from django.test import Client, override_settings
from rest_framework.test import APIClient

import pytest

from apps.accounts.models import User
from apps.common.tenancy import tenant_context
from apps.documents.models import Document, DocumentCategory

pytestmark = pytest.mark.django_db


def _staff_filiale(username, tenant):
    return User.objects.create_user(
        username=username,
        password="FinFlow2026!",
        tenant=tenant,
        is_staff=True,
        is_group_level=False,
        data_scope="TENANT",
    )


def _group_admin(username):
    return User.objects.create_user(
        username=username,
        password="FinFlow2026!",
        is_staff=True,
        is_group_level=True,
    )


def _soft_deleted_doc(tenant, name):
    with tenant_context(tenant.id):
        category = DocumentCategory.objects.create(
            tenant=tenant, code=f"ISO-{name[:8]}", label=name
        )
        doc = Document.objects.create(
            tenant=tenant,
            category=category,
            name=name,
            size_bytes=10,
        )
        doc.is_deleted = True
        doc.save(update_fields=["is_deleted"])
    return doc


@override_settings(ALLOWED_HOSTS=["*"])
def test_filiale_staff_cannot_read_cross_tenant_metrics(tenant_a, tenant_b):
    _soft_deleted_doc(tenant_a, "doc-a.pdf")
    _soft_deleted_doc(tenant_b, "doc-b.pdf")
    staff = _staff_filiale("iso_staff_a", tenant_a)

    api = APIClient()
    api.force_authenticate(staff)
    res = api.get("/api/v1/metrics/", HTTP_HOST="localhost")
    assert res.status_code == 403, res.content
    body = res.json()
    assert "applications_total" not in body
    assert "tenants_active" not in body


@override_settings(ALLOWED_HOSTS=["*"])
def test_group_operator_still_reads_global_metrics(tenant_a, tenant_b):
    _soft_deleted_doc(tenant_a, "doc-a2.pdf")
    _soft_deleted_doc(tenant_b, "doc-b2.pdf")
    admin = _group_admin("iso_grp")

    api = APIClient()
    api.force_authenticate(admin)
    res = api.get("/api/v1/metrics/", HTTP_HOST="localhost")
    assert res.status_code == 200, res.content
    data = res.json()
    assert data["tenants_active"] >= 2
    assert data["applications_total"] >= 0
    assert data["documents_soft_deleted"] >= 2
    assert "celery" in data


@override_settings(ALLOWED_HOSTS=["*"])
def test_ops_status_scopes_soft_delete_to_caller_tenant(tenant_a, tenant_b):
    _soft_deleted_doc(tenant_a, "only-a.pdf")
    _soft_deleted_doc(tenant_b, "only-b.pdf")
    staff = _staff_filiale("iso_ops_a", tenant_a)

    api = APIClient()
    api.force_authenticate(staff)
    res = api.get("/api/v1/ops/status/", HTTP_HOST="localhost")
    assert res.status_code == 200, res.content
    data = res.json()
    assert "celery" in data
    assert "applications_total" not in data
    assert "tenants_active" not in data
    assert data["documents_soft_deleted"] == 1


@override_settings(ALLOWED_HOSTS=["*"])
def test_ops_status_group_without_header_sees_all_soft_deletes(tenant_a, tenant_b):
    _soft_deleted_doc(tenant_a, "grp-a.pdf")
    _soft_deleted_doc(tenant_b, "grp-b.pdf")
    admin = _group_admin("iso_ops_grp")

    api = APIClient()
    api.force_authenticate(admin)
    res = api.get("/api/v1/ops/status/", HTTP_HOST="localhost")
    assert res.status_code == 200, res.content
    assert res.json()["documents_soft_deleted"] >= 2


@override_settings(ALLOWED_HOSTS=["*"])
def test_ops_status_group_header_scopes_to_target_tenant(tenant_a, tenant_b):
    _soft_deleted_doc(tenant_a, "hdr-a.pdf")
    _soft_deleted_doc(tenant_b, "hdr-b.pdf")
    admin = _group_admin("iso_ops_hdr")

    api = APIClient()
    api.force_authenticate(admin)
    res = api.get(
        "/api/v1/ops/status/",
        HTTP_HOST="localhost",
        HTTP_X_TENANT_ID=str(tenant_a.id),
    )
    assert res.status_code == 200, res.content
    assert res.json()["documents_soft_deleted"] == 1


@override_settings(ALLOWED_HOSTS=["*"])
def test_plain_user_cannot_read_ops_status(tenant_a):
    user = User.objects.create_user(
        username="iso_plain",
        password="FinFlow2026!",
        tenant=tenant_a,
        is_staff=False,
    )
    api = APIClient()
    api.force_authenticate(user)
    assert api.get("/api/v1/ops/status/", HTTP_HOST="localhost").status_code == 403
    assert api.get("/api/v1/metrics/", HTTP_HOST="localhost").status_code == 403


@override_settings(ALLOWED_HOSTS=["*"])
def test_filiale_staff_cannot_open_django_admin(tenant_a):
    staff = _staff_filiale("iso_dj_staff", tenant_a)
    client = Client()
    client.force_login(staff)
    res = client.get("/django-admin/", HTTP_HOST="localhost")
    assert res.status_code in (302, 403)
    if res.status_code == 302:
        assert "/django-admin/login" in res["Location"]


@override_settings(ALLOWED_HOSTS=["*"])
def test_group_staff_can_open_django_admin():
    admin = _group_admin("iso_dj_grp")
    client = Client()
    client.force_login(admin)
    res = client.get("/django-admin/", HTTP_HOST="localhost")
    assert res.status_code == 200
