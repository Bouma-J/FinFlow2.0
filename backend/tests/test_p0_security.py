"""Non-régression P0 audit prod — KYC, CBS retry, filename, secrets, délégations."""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient

import pytest

from apps.accounts.models import Delegation, User
from apps.clients.models import Client
from apps.common.files import safe_filename
from apps.common.storage_urls import sign_client_file_token
from apps.common.tenancy import tenant_context
from apps.corebanking.models import CoreBankingConnector, IntegrationLog
from apps.corebanking.serializers import CoreBankingConnectorSerializer
from apps.corebanking.services import send_operation
from apps.corebanking.tasks import retry_cbs_integrations

pytestmark = pytest.mark.django_db


@override_settings(ALLOWED_HOSTS=["*"])
def test_client_kyc_files_reject_anonymous_uuid_only(client_a, tenant_a):
    with tenant_context(tenant_a.id):
        client_a.photo = SimpleUploadedFile(
            "face.jpg", b"\xff\xd8\xfffakejpeg", content_type="image/jpeg"
        )
        client_a.save(update_fields=["photo"])

    api = APIClient()
    # Sans JWT ni token : interdit
    res = api.get(
        f"/api/v1/clients/{client_a.id}/files/photo/",
        HTTP_HOST="localhost",
    )
    assert res.status_code in (401, 403), res.content

    # UUID seul + faux token : interdit
    res_bad = api.get(
        f"/api/v1/clients/{client_a.id}/files/photo/?token=invalid",
        HTTP_HOST="localhost",
    )
    assert res_bad.status_code == 403, res_bad.content

    # Jeton signé valide : OK
    token = sign_client_file_token(client_a.id, "photo")
    res_ok = api.get(
        f"/api/v1/clients/{client_a.id}/files/photo/?token={token}",
        HTTP_HOST="localhost",
    )
    assert res_ok.status_code == 200, res_ok.content


def test_safe_filename_blocks_path_traversal():
    assert safe_filename("../../etc/passwd") == "passwd"
    assert "/" not in safe_filename("a/b/c.pdf")
    assert safe_filename("../../evil.exe") == "evil.exe"
    assert safe_filename("rapport final (1).PDF").endswith(".PDF")
    assert safe_filename("") == "file"
    assert safe_filename("...") == "file"


def test_cbs_retry_reuses_idempotency_row(tenant_a, monkeypatch):
    with tenant_context(tenant_a.id):
        connector = CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="CBS-A",
            protocol=CoreBankingConnector.Protocol.REST,
            base_url="http://example.invalid",
            max_retries=3,
            is_active=True,
        )
        log = IntegrationLog.objects.create(
            tenant=tenant_a,
            connector=connector,
            operation="DISBURSE",
            direction=IntegrationLog.Direction.OUTBOUND,
            idempotency_key="idem-p0-1",
            request_payload={"x": 1},
            status=IntegrationLog.Status.RETRY,
            attempts=1,
            error_message="timeout",
        )

    class _OkAdapter:
        def send(self, operation, payload):
            return {"external_reference": "EXT-1", "ok": True}

    monkeypatch.setattr(
        "apps.corebanking.services.get_adapter",
        lambda _c: _OkAdapter(),
    )

    with tenant_context(tenant_a.id):
        result = send_operation(
            connector, "DISBURSE", {"x": 1}, "idem-p0-1"
        )
        assert result.id == log.id
        assert result.status == IntegrationLog.Status.SUCCESS
        assert (
            IntegrationLog.objects.filter(
                connector=connector, idempotency_key="idem-p0-1"
            ).count()
            == 1
        )

        # Beat task ne doit pas planter
        assert retry_cbs_integrations(limit=10) >= 0


def test_callback_secret_redacted_in_connector_api(tenant_a):
    with tenant_context(tenant_a.id):
        connector = CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="CBS-SEC",
            protocol=CoreBankingConnector.Protocol.REST,
            mapping_rules={
                "disbursement": {
                    "mode": "CBS",
                    "callback_secret": "super-secret-value",
                }
            },
            is_active=True,
        )
    data = CoreBankingConnectorSerializer(connector).data
    disbursement = data["mapping_rules"]["disbursement"]
    assert disbursement.get("callback_secret") == ""
    assert disbursement.get("callback_secret_configured") is True


@override_settings(ALLOWED_HOSTS=["*"])
def test_delegation_revoke_scoped_to_tenant(tenant_a, tenant_b):
    user_a = User.objects.create_user(
        username="p0_del_a", password="FinFlow2026!", tenant=tenant_a
    )
    user_a2 = User.objects.create_user(
        username="p0_del_a2", password="FinFlow2026!", tenant=tenant_a
    )
    user_b = User.objects.create_user(
        username="p0_del_b", password="FinFlow2026!", tenant=tenant_b
    )
    user_b2 = User.objects.create_user(
        username="p0_del_b2", password="FinFlow2026!", tenant=tenant_b
    )
    from django.utils import timezone
    from datetime import timedelta

    today = timezone.localdate()
    del_b = Delegation.objects.create(
        delegator=user_b,
        delegate=user_b2,
        start_date=today,
        end_date=today + timedelta(days=3),
        is_active=True,
    )

    api = APIClient()
    api.force_authenticate(user_a)
    # Utilisateur filiale A ne peut pas révoquer une délégation de B
    res = api.post(
        f"/api/v1/delegations/{del_b.id}/revoke/",
        HTTP_X_TENANT_ID=str(tenant_a.id),
        HTTP_HOST="localhost",
    )
    assert res.status_code == 404, res.content
    del_b.refresh_from_db()
    assert del_b.is_active is True

    # Contrôle positif : révocation dans la même filiale
    del_a = Delegation.objects.create(
        delegator=user_a,
        delegate=user_a2,
        start_date=today,
        end_date=today + timedelta(days=3),
        is_active=True,
    )
    res_ok = api.post(
        f"/api/v1/delegations/{del_a.id}/revoke/",
        HTTP_X_TENANT_ID=str(tenant_a.id),
        HTTP_HOST="localhost",
    )
    assert res_ok.status_code == 200, res_ok.content
    del_a.refresh_from_db()
    assert del_a.is_active is False
