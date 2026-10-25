"""Correctifs restants — health, refs, GED origin, callback terminal."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.common.tenancy import tenant_context
from apps.corebanking.disbursement import apply_cbs_callback
from apps.corebanking.models import CoreBankingConnector
from apps.corebanking.services import CoreBankingError
from apps.credits.models import CreditApplication
from apps.guarantees.process_services import _next_reference
from apps.guarantees.models import GuaranteeReleaseRequest

pytestmark = pytest.mark.django_db
User = get_user_model()


def test_health_hides_error_detail_when_not_debug(settings):
    settings.DEBUG = False
    api = APIClient()
    # Force cache failure path is hard ; vérifier structure sans fuite
    # si un check est ko. On mocke via monkeypatch du check storage.
    from apps.common import health as health_mod

    original = health_mod._check_storage

    def boom():
        return {"ok": False, "backend": "s3", "error": "AccessDenied secret-xyz"}

    health_mod._check_storage = boom
    try:
        resp = api.get("/api/v1/health/")
        assert resp.status_code == 503
        err = resp.data["checks"]["storage"].get("error")
        assert err == "unavailable"
        assert "secret" not in str(resp.data).lower()
        assert "AccessDenied" not in str(resp.data)
    finally:
        health_mod._check_storage = original


def test_next_reference_under_lock(tenant_a):
    """Le verrou tenant s'exécute sans erreur (anti-course)."""
    with tenant_context(tenant_a.id):
        r1 = _next_reference("ML", GuaranteeReleaseRequest, tenant_a.id)
    assert r1.startswith("ML-")
    assert r1.count("-") >= 2


def test_callback_ignored_on_terminal_status(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="TERM1",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("100000"),
            duration_months=12,
            status=CreditApplication.Status.CLOSED,
        )
        CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="Perfect",
            protocol=CoreBankingConnector.Protocol.REST,
            is_active=True,
            mapping_rules={
                "disbursement": {"callback_secret": "cb-secret-ok"}
            },
        )

    result = apply_cbs_callback(
        str(app.id), {"status": "LATE"}, secret="cb-secret-ok"
    )
    assert result.get("ignored") is True
    app.refresh_from_db()
    assert app.status == CreditApplication.Status.CLOSED


def test_callback_bad_secret(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="TERM2",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("100000"),
            duration_months=12,
            status=CreditApplication.Status.DISBURSEMENT_PENDING,
        )
        CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="Perfect2",
            protocol=CoreBankingConnector.Protocol.REST,
            is_active=True,
            mapping_rules={
                "disbursement": {"callback_secret": "cb-secret-ok"}
            },
        )

    with pytest.raises(CoreBankingError):
        apply_cbs_callback(str(app.id), {"status": "OK"}, secret="wrong")
