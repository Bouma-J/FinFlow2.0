"""API délégations — admin CRUD + self-service give / mine / revoke."""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Delegation, User
from apps.common.tenancy import tenant_context

pytestmark = pytest.mark.django_db


def test_give_mine_revoke_self_service(tenant_a):
    delegator = User.objects.create_user(
        username="del_give_a",
        password="FinFlow2026!",
        tenant=tenant_a,
    )
    delegate = User.objects.create_user(
        username="del_give_b",
        password="FinFlow2026!",
        tenant=tenant_a,
    )
    api = APIClient()
    api.force_authenticate(delegator)

    today = timezone.localdate()
    res = api.post(
        "/api/v1/delegations/give/",
        {
            "delegate": str(delegate.id),
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=5)).isoformat(),
            "reason": "Congé",
        },
        format="json",
        HTTP_X_TENANT_ID=str(tenant_a.id),
    )
    assert res.status_code == 201, res.content
    data = res.json()
    assert data["delegator"] == str(delegator.id)
    assert data["delegate"] == str(delegate.id)
    assert data["is_currently_valid"] is False
    assert data["approval_required"] is True
    del_id = data["id"]

    mine = api.get(
        "/api/v1/delegations/mine/",
        HTTP_X_TENANT_ID=str(tenant_a.id),
    )
    assert mine.status_code == 200
    assert any(row["id"] == del_id for row in mine.json())

    colleagues = api.get(
        "/api/v1/delegations/colleagues/",
        HTTP_X_TENANT_ID=str(tenant_a.id),
    )
    assert colleagues.status_code == 200
    assert any(row["id"] == str(delegate.id) for row in colleagues.json())

    rev = api.post(
        f"/api/v1/delegations/{del_id}/revoke/",
        HTTP_X_TENANT_ID=str(tenant_a.id),
    )
    assert rev.status_code == 200
    assert rev.json()["is_active"] is False


def test_cannot_delegate_to_self(tenant_a):
    user = User.objects.create_user(
        username="del_self",
        password="FinFlow2026!",
        tenant=tenant_a,
    )
    api = APIClient()
    api.force_authenticate(user)
    today = timezone.localdate()
    res = api.post(
        "/api/v1/delegations/give/",
        {
            "delegate": str(user.id),
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=1)).isoformat(),
        },
        format="json",
        HTTP_X_TENANT_ID=str(tenant_a.id),
    )
    assert res.status_code == 400


def test_admin_create_validates_dates(tenant_a):
    admin = User.objects.create_user(
        username="del_admin",
        password="FinFlow2026!",
        tenant=tenant_a,
        is_staff=True,
        is_group_level=True,
    )
    from django.contrib.auth.models import Permission

    for codename in ("add_delegation", "view_delegation", "change_delegation"):
        admin.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="accounts", codename=codename
            )
        )
    a = User.objects.create_user(
        username="del_a2", password="x", tenant=tenant_a
    )
    b = User.objects.create_user(
        username="del_b2", password="x", tenant=tenant_a
    )
    api = APIClient()
    api.force_authenticate(admin)
    today = timezone.localdate()
    with tenant_context(tenant_a.id):
        res = api.post(
            "/api/v1/delegations/",
            {
                "delegator": str(a.id),
                "delegate": str(b.id),
                "start_date": today.isoformat(),
                "end_date": (today - timedelta(days=1)).isoformat(),
                "is_active": True,
            },
            format="json",
            HTTP_X_TENANT_ID=str(tenant_a.id),
        )
    assert res.status_code == 400
