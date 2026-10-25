"""Quick wins — IDOR Groupe, async-tasks, callback secret query."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.clients.models import Client
from apps.common.scoped import get_for_tenant, track_async_task
from apps.common.tenancy import tenant_context
from apps.corebanking.models import CoreBankingConnector
from apps.credits.models import CreditApplication
from apps.tenants.models import Agency

pytestmark = pytest.mark.django_db
User = get_user_model()


def _group_user(**extra):
    return User.objects.create_user(
        username=extra.pop("username", "group_qw"),
        password="x",
        is_group_level=True,
        is_staff=True,
        **extra,
    )


@pytest.fixture
def client_b(tenant_b):
    with tenant_context(tenant_b.id):
        return Client.objects.create(
            tenant=tenant_b,
            reference="CLIB",
            client_type=Client.ClientType.INDIVIDUAL,
            first_name="Other",
            last_name="Tenant",
            kyc_status=Client.KycStatus.VALIDATED,
        )


def test_get_for_tenant_blocks_cross_filiale(tenant_a, client_a, client_b):
    with tenant_context(tenant_a.id, group=True):
        with pytest.raises(Exception):
            get_for_tenant(Client, client_b.id, error_field="client")


def test_group_release_client_context_idor(tenant_a, client_b):
    admin = _group_user()
    api = APIClient()
    api.force_authenticate(admin)
    resp = api.get(
        "/api/v1/guarantee-releases/client-context/",
        {"client": str(client_b.id)},
        HTTP_X_TENANT_ID=str(tenant_a.id),
    )
    assert resp.status_code in (400, 403, 404)


def test_group_agencies_empty_without_tenant_header(tenant_a, tenant_b):
    with tenant_context(tenant_a.id):
        Agency.objects.create(tenant=tenant_a, code="AG-A", name="Agence A")
    with tenant_context(tenant_b.id):
        Agency.objects.create(tenant=tenant_b, code="AG-B", name="Agence B")

    admin = User.objects.create_superuser(
        username="group_qw_ag", password="x", email="ag@test.local"
    )
    admin.is_group_level = True
    admin.save(update_fields=["is_group_level"])
    api = APIClient()
    api.force_authenticate(admin)
    resp = api.get("/api/v1/agencies/")
    assert resp.status_code == 200
    results = resp.data.get("results", resp.data)
    assert len(results) == 0


def test_async_task_status_owner_gate():
    owner = _group_user(username="group_qw_owner")
    other = User.objects.create_user(username="other_qw", password="x")
    track_async_task("task-qw-1", owner.id)

    api = APIClient()
    api.force_authenticate(other)
    assert api.get("/api/v1/async-tasks/task-qw-1/").status_code == 403

    api.force_authenticate(owner)
    resp = api.get("/api/v1/async-tasks/task-qw-1/")
    assert resp.status_code == 200
    assert resp.data["task_id"] == "task-qw-1"
    assert "state" in resp.data


def test_callback_rejects_query_secret(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="CBSCB",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("100000"),
            duration_months=12,
            status=CreditApplication.Status.APPROVED,
        )
        CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="Perfect",
            protocol=CoreBankingConnector.Protocol.REST,
            is_active=True,
            mapping_rules={"callback_secret": "super-secret-callback"},
        )

    api = APIClient()
    resp = api.post(
        f"/api/v1/cbs/callbacks/crd/{app.id}/?secret=super-secret-callback",
        {"status": "OK"},
        format="json",
    )
    assert resp.status_code == 400
