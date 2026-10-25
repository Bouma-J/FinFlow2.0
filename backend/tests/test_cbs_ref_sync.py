"""Synchronisation des référentiels Perfect (ref/*) vers FinFlow."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import TenantRole, User
from apps.accounts.services import FILIALE_ADMIN_ROLE_NAME, ensure_filiale_admin_role
from apps.catalog.defaults import ensure_catalog_defaults
from apps.catalog.models import (
    CbsManager,
    CbsProfession,
    Currency,
    DecisionMotif,
    FinancingObject,
    FinancingSource,
    LoanPeriodicity,
    ServicePoint,
)
from apps.common.tenancy import tenant_context
from apps.corebanking.models import CoreBankingConnector
from apps.corebanking.perfect_defaults import perfect_mapping_rules
from apps.corebanking.ref_sync import sync_cbs_referentials
from apps.corebanking.services import CoreBankingError, RestAdapter
from apps.tenants.models import Agency

pytestmark = pytest.mark.django_db


def _connector(tenant):
    return CoreBankingConnector.all_tenants.create(
        tenant=tenant,
        name="CBS Test",
        protocol=CoreBankingConnector.Protocol.REST,
        base_url="https://cbs.test",
        auth_config={"access_token": "tok-test"},
        mapping_rules=perfect_mapping_rules(demo=False),
        is_active=True,
    )


def _admin(tenant):
    ensure_filiale_admin_role(tenant)
    user = User.objects.create_user(
        username=f"admin_{tenant.code}",
        password="x",
        tenant=tenant,
        is_staff=True,
    )
    role = TenantRole.objects.filter(
        tenant=tenant, name=FILIALE_ADMIN_ROLE_NAME
    ).first()
    if role and role.group_id:
        user.groups.add(role.group)
    return user


def _ref_response(datas):
    resp = MagicMock()
    resp.status_code = 200
    resp.content = b'{"datas":[]}'
    resp.json.return_value = {
        "responseCode": 200,
        "message": "ok",
        "datas": datas,
    }
    return resp


def test_fetch_ref_list_parses_datas(tenant_a):
    connector = _connector(tenant_a)
    adapter = RestAdapter(connector)
    with patch.object(
        adapter,
        "_http_get",
        return_value=_ref_response(
            [{"id": "1", "code": "XOF", "libelle": "Franc CFA"}]
        ),
    ) as get:
        rows = adapter.fetch_ref_list(
            "ref_devise_list",
            default_path="gateway-perfect/ref/devise-list",
        )
    assert rows == [{"id": "1", "code": "XOF", "libelle": "Franc CFA"}]
    assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer tok-test"


def test_fetch_ref_list_null_datas_is_empty(tenant_a):
    connector = _connector(tenant_a)
    adapter = RestAdapter(connector)
    resp = MagicMock()
    resp.status_code = 200
    resp.content = b'{"datas":null}'
    resp.json.return_value = {
        "responseCode": 200,
        "message": "Success !",
        "datas": None,
    }
    with patch.object(adapter, "_http_get", return_value=resp):
        rows = adapter.fetch_ref_list(
            "ref_profession_list",
            default_path="gateway-perfect/ref/profession-list",
        )
    assert rows == []


def test_sync_cbs_referentials_wave1(tenant_a):
    ensure_catalog_defaults(tenant_a)
    connector = _connector(tenant_a)
    Agency.objects.create(
        tenant=tenant_a, code="AG-PRINCIPALE", name="Agence Principale Centre-Ville"
    )

    responses = {
        "gateway-perfect/ref/devise-list": _ref_response(
            [{"id": "1", "code": "XOF", "libelle": "Franc CFA"}]
        ),
        "gateway-perfect/ref/periodicite-list": _ref_response(
            [
                {"id": "M", "code": "M", "libelle": "Mensuelle"},
                {"id": "T", "code": "T", "libelle": "Trimestrielle"},
            ]
        ),
        "gateway-perfect/ref/object-fin-list": _ref_response(
            [
                {"id": "30", "code": "CONSO", "libelle": "Crédit à la consommation"},
                {"id": "1", "code": "IMMO", "libelle": "Achat Immobilier"},
            ]
        ),
        "gateway-perfect/ref/point-service-list": _ref_response(
            [
                {
                    "id": "PS01",
                    "code": "AG-PRINCIPALE",
                    "libelle": "Agence Principale Centre-Ville",
                },
                {"id": "PS99", "code": "UNKNOWN", "libelle": "Inconnue"},
            ]
        ),
        "gateway-perfect/ref/gestionnaire-list": _ref_response(
            [
                {"id": "GEST001", "code": "JDUPONT", "libelle": "Jean Dupont"},
                {"id": "GEST999", "code": "OTHER", "libelle": "Autre"},
            ]
        ),
        "gateway-perfect/ref/source-fin-list": _ref_response(
            [
                {"id": "1", "code": "SAL", "libelle": "Salaire"},
                {"id": "2", "code": "REV_LOC", "libelle": "Revenus Locatifs"},
            ]
        ),
        "gateway-perfect/ref/motif-decision-list": _ref_response(
            [
                {"id": "1", "code": "ACC", "libelle": "Accepté"},
                {
                    "id": "2",
                    "code": "REF_SOLV",
                    "libelle": "Refus - Solvabilité insuffisante",
                },
            ]
        ),
        "gateway-perfect/ref/profession-list": _ref_response(
            [
                {"id": "1", "code": "001", "libelle": "Chauffeur"},
                {"id": "2", "code": "002", "libelle": "Marchand"},
            ]
        ),
    }

    def fake_get(url, **kwargs):
        for path, resp in responses.items():
            if url.endswith(path):
                return resp
        raise AssertionError(f"Unexpected URL {url}")

    with tenant_context(tenant_a.id):
        with patch(
            "apps.corebanking.services.RestAdapter._http_get",
            side_effect=fake_get,
        ):
            report = sync_cbs_referentials(tenant_a.id, connector=connector)

    assert report["results"]["currencies"]["updated"] == 1
    assert report["results"]["periodicities"]["updated"] == 2
    assert report["results"]["financing_objects"]["created"] == 2
    assert report["results"]["service_points"]["created"] == 2
    assert report["results"]["service_points"]["linked"] == 1
    assert report["results"]["managers"]["created"] == 2
    assert report["results"]["financing_sources"]["created"] == 2
    assert report["results"]["decision_motifs"]["created"] == 2
    assert report["results"]["professions"]["created"] == 2

    with tenant_context(tenant_a.id):
        assert Currency.objects.get(code="XOF").cbs_code == "XOF"
        assert LoanPeriodicity.objects.get(code="MONTHLY").cbs_code == "M"
        assert LoanPeriodicity.objects.get(code="QUARTERLY").cbs_code == "T"
        conso = FinancingObject.objects.get(code="CONSO")
        assert conso.cbs_code == "30"
        assert conso.purpose_type == "CONSUMPTION"
        assert ServicePoint.objects.filter(cbs_code="PS01").exists()
        assert ServicePoint.objects.filter(cbs_code="PS99").exists()
        assert CbsManager.objects.get(code="JDUPONT").cbs_code == "GEST001"
        assert FinancingSource.objects.get(code="SAL").cbs_code == "1"
        assert DecisionMotif.objects.get(code="ACC").cbs_code == "1"
        assert CbsProfession.objects.get(code="001").cbs_code == "1"
        assert CbsProfession.objects.get(code="001").label == "Chauffeur"

    connector.refresh_from_db()
    purpose_map = (connector.mapping_rules or {}).get("disbursement", {}).get(
        "purpose_map"
    ) or {}
    assert purpose_map["CONSUMPTION"] == "30"
    assert purpose_map["REAL_ESTATE"] == "1"

    agency = Agency.objects.get(tenant=tenant_a, code="AG-PRINCIPALE")
    assert agency.cbs_point_of_service_id == "PS01"


def test_currency_api_is_read_only(tenant_a):
    ensure_catalog_defaults(tenant_a)
    admin = _admin(tenant_a)
    client = APIClient()
    client.force_authenticate(user=admin)
    r = client.post(
        "/api/v1/currencies/",
        {"code": "ZZZ", "label": "Fake", "cbs_code": "9"},
        format="json",
        HTTP_X_TENANT_ID=str(tenant_a.id),
    )
    assert r.status_code in (403, 405)


def test_agency_rejects_unknown_service_point(tenant_a):
    admin = _admin(tenant_a)
    client = APIClient()
    client.force_authenticate(user=admin)
    r = client.post(
        "/api/v1/agencies/",
        {
            "code": "AGX",
            "name": "Agence X",
            "cbs_point_of_service_id": "UNKNOWN-PS",
        },
        format="json",
        HTTP_X_TENANT_ID=str(tenant_a.id),
    )
    assert r.status_code == 400
    assert "Point de service" in str(r.data)


def test_user_accepts_synced_manager(tenant_a):
    admin = _admin(tenant_a)
    with tenant_context(tenant_a.id):
        CbsManager.objects.create(
            code="JDUPONT",
            label="Jean Dupont",
            cbs_code="GEST001",
            is_active=True,
        )
        agency = Agency.objects.create(
            tenant=tenant_a, code="AG1", name="Agence 1"
        )

    client = APIClient()
    client.force_authenticate(user=admin)
    r = client.post(
        "/api/v1/users/",
        {
            "username": "agent1",
            "email": "agent1@example.com",
            "agency": str(agency.id),
            "cbs_id": "GEST001",
            "password_delivery": "manual",
            "password": "FinFlow2026!",
            "password_confirm": "FinFlow2026!",
            "group_ids": [],
        },
        format="json",
        HTTP_X_TENANT_ID=str(tenant_a.id),
    )
    assert r.status_code in (200, 201), r.data
    user = User.objects.get(username="agent1")
    assert user.cbs_id == "GEST001"


def test_sync_cbs_referentials_propagates_http_error(tenant_a):
    connector = _connector(tenant_a)
    bad = MagicMock()
    bad.status_code = 404
    bad.content = b"{}"
    bad.json.return_value = {"message": "Not Found"}

    with tenant_context(tenant_a.id):
        with patch(
            "apps.corebanking.services.RestAdapter._http_get",
            return_value=bad,
        ):
            report = sync_cbs_referentials(
                tenant_a.id,
                connector=connector,
                scopes=["currencies"],
            )
    assert report["results"]["currencies"]["error"]
    assert "404" in report["results"]["currencies"]["error"] or "Not Found" in (
        report["results"]["currencies"]["error"] or ""
    )


def test_sync_unknown_scope_raises(tenant_a):
    connector = _connector(tenant_a)
    with pytest.raises(CoreBankingError, match="Scopes"):
        sync_cbs_referentials(
            tenant_a.id, connector=connector, scopes=["nope"]
        )
