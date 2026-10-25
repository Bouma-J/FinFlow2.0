"""Branding public (écran de connexion)."""

import pytest
from rest_framework.test import APIClient

from apps.tenants.models import Tenant


@pytest.mark.django_db
def test_public_branding_by_code():
    Tenant.objects.create(
        code="FIL01",
        name="Filiale Démo",
        country="CI",
        currency="XOF",
        brand_primary="#112233",
        brand_secondary="#223344",
        brand_accent="#aabb00",
        is_active=True,
    )
    client = APIClient()
    res = client.get("/api/v1/tenants/branding/", {"code": "fil01"})
    assert res.status_code == 200
    data = res.json()
    # Enveloppe API éventuelle
    payload = data.get("data", data) if isinstance(data, dict) else data
    if "success" in data and "data" in data:
        payload = data["data"]
    assert payload["code"] == "FIL01"
    assert payload["name"] == "Filiale Démo"
    assert payload["brand_primary"] == "#112233"
    assert "logo_url" in payload


@pytest.mark.django_db
def test_public_branding_unknown_code():
    client = APIClient()
    res = client.get("/api/v1/tenants/branding/", {"code": "UNKNOWN"})
    assert res.status_code == 404


@pytest.mark.django_db
def test_public_branding_inactive_hidden():
    Tenant.objects.create(
        code="OFF",
        name="Inactive",
        country="CI",
        currency="XOF",
        is_active=False,
    )
    client = APIClient()
    res = client.get("/api/v1/tenants/branding/", {"code": "OFF"})
    assert res.status_code == 404
