"""
Tests poussés — mapping CBS / référentiels / décaissement Perfect.

Couvre :
- priorités de résolution (utilisateur, produit, catalogue, connecteur)
- validation dossier contre référentiels
- API admin référentiels + isolation multi-tenant
- RestAdapter._crd_simple (HTTP mocké)
- callbacks sécurisés
- bootstrap filiale
- period_count via catalogue
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.catalog.cbs_resolve import (
    resolve_currency_cbs,
    resolve_periodicity_cbs,
    resolve_periodicity_periods_per_year,
    resolve_repayment_cbs,
)
from apps.catalog.defaults import ensure_catalog_defaults
from apps.catalog.models import Currency, LoanPeriodicity, RepaymentMethod
from apps.clients.models import Client
from apps.common.tenancy import tenant_context
from apps.corebanking.disbursement import (
    apply_cbs_callback,
    build_credit_disbursement_payload,
    disbursement_mode,
    submit_credit_to_cbs,
)
from apps.corebanking.models import CoreBankingConnector, IntegrationLog
from apps.corebanking.services import (
    CoreBankingError,
    RestAdapter,
    SimulatedAdapter,
    get_adapter,
)
from apps.credits.models import CreditApplication
from apps.credits.serializers import CreditApplicationSerializer
from apps.credits.services import WorkflowError, disburse_application, period_count
from apps.tenants.models import Agency
from apps.tenants.services import bootstrap_tenant

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def agency(tenant_a):
    with tenant_context(tenant_a.id):
        return Agency.objects.create(
            tenant=tenant_a,
            code="AG-CBS",
            name="Agence CBS",
            cbs_point_of_service_id="PS-AG01",
        )


@pytest.fixture
def catalog(tenant_a):
    ensure_catalog_defaults(tenant_a)
    return tenant_a


@pytest.fixture
def connector(tenant_a, catalog):
    with tenant_context(tenant_a.id):
        return CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="CBS Advanced",
            protocol=CoreBankingConnector.Protocol.REST,
            base_url="https://cbs.prod.example/api",
            mapping_rules={
                "force_simulate": True,
                "disbursement": {
                    "mode": "LOCAL",
                    "callback_secret": "secret-test",
                    "defaults": {
                        "idPointService": "PS-DEFAULT",
                        "idGestionnaire": "GEST-DEFAULT",
                        "idProduitRemb": "REMB-DEFAULT",
                    },
                },
                "simulate": {},
            },
            auth_config={"access_token": "TOKEN-TEST"},
            is_active=True,
        )


@pytest.fixture
def officer(tenant_a, agency):
    return User.objects.create_user(
        username="adv_officer",
        password="FinFlow2026!",
        tenant=tenant_a,
        agency=agency,
        cbs_id="GEST-USER",
        employee_id="EMP-FALLBACK",
        data_scope="AGENCY",
    )


@pytest.fixture
def staff_admin(tenant_a):
    """Admin Groupe (superuser) pour les appels API CRUD référentiels / users."""
    return User.objects.create_user(
        username="adv_admin",
        password="FinFlow2026!",
        tenant=None,
        is_group_level=True,
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def prepared_product(product_a):
    product_a.cbs_product_code = "CRED-ADV"
    product_a.cbs_repayment_product_code = ""
    product_a.currency = "XOF"
    product_a.save(
        update_fields=[
            "cbs_product_code",
            "cbs_repayment_product_code",
            "currency",
            "updated_at",
        ]
    )
    return product_a


@pytest.fixture
def prepared_client(client_a):
    client_a.cbs_client_id = "A-ADV-001"
    client_a.save(update_fields=["cbs_client_id"])
    return client_a


def _approved_app(
    tenant,
    *,
    product,
    client,
    agency,
    officer=None,
    **extra,
):
    defaults = {
        "tenant": tenant,
        "reference": "ADV-CRD-001",
        "client": client,
        "product": product,
        "agency": agency,
        "amount_requested": Decimal("750000"),
        "amount_approved": Decimal("700000"),
        "interest_rate": Decimal("8.5"),
        "duration_months": 24,
        "periodicity": "MONTHLY",
        "repayment_mechanism": "DEGRESSIVE",
        "purpose_type": "EQUIPMENT",
        "currency": "XOF",
        "status": CreditApplication.Status.APPROVED,
        "created_by": officer,
        "submitted_by": officer,
    }
    defaults.update(extra)
    with tenant_context(tenant.id):
        return CreditApplication.objects.create(**defaults)


# ---------------------------------------------------------------------------
# Modes & adaptateurs
# ---------------------------------------------------------------------------


def test_disbursement_mode_matrix(tenant_a, catalog):
    with tenant_context(tenant_a.id):
        local_forced = CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="mode-local",
            protocol="REST",
            base_url="https://x",
            mapping_rules={"disbursement": {"mode": "LOCAL"}},
            is_active=True,
        )
        cbs_forced = CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="mode-cbs",
            protocol="REST",
            base_url="https://x",
            mapping_rules={"disbursement": {"mode": "CBS"}},
            is_active=True,
        )
        simulate = CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="mode-sim",
            protocol="REST",
            base_url="https://x",
            mapping_rules={"force_simulate": True},
            is_active=True,
        )
        no_url = CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="mode-nourl",
            protocol="REST",
            base_url="",
            mapping_rules={},
            is_active=True,
        )
    assert disbursement_mode(local_forced) == "LOCAL"
    assert disbursement_mode(cbs_forced) == "CBS"
    assert disbursement_mode(simulate) == "LOCAL"
    assert disbursement_mode(no_url) == "LOCAL"
    assert isinstance(get_adapter(simulate), SimulatedAdapter)
    assert isinstance(get_adapter(cbs_forced), RestAdapter)


# ---------------------------------------------------------------------------
# Priorités de mapping
# ---------------------------------------------------------------------------


def test_id_gestionnaire_prefers_submitted_by_cbs_id(
    tenant_a, catalog, connector, agency, prepared_product, prepared_client, officer,
):
    creator = User.objects.create_user(
        username="creator_only",
        password="x",
        tenant=tenant_a,
        agency=agency,
        cbs_id="GEST-CREATOR",
    )
    app = _approved_app(
        tenant_a,
        product=prepared_product,
        client=prepared_client,
        agency=agency,
        officer=officer,
        created_by=creator,
        submitted_by=officer,
    )
    payload = build_credit_disbursement_payload(app, connector=connector)
    assert payload["idGestionnaire"] == "GEST-USER"


def test_id_gestionnaire_does_not_use_hr_employee_id(
    tenant_a, catalog, connector, agency, prepared_product, prepared_client,
):
    user = User.objects.create_user(
        username="emp_only",
        password="x",
        tenant=tenant_a,
        agency=agency,
        cbs_id="",
        employee_id="EMP-42",
    )
    app = _approved_app(
        tenant_a,
        product=prepared_product,
        client=prepared_client,
        agency=agency,
        officer=user,
    )
    payload = build_credit_disbursement_payload(app, connector=connector)
    # Le matricule RH n'est pas un identifiant du référentiel CBS.
    assert payload["idGestionnaire"] == "GEST-DEFAULT"

    user.employee_id = ""
    user.save(update_fields=["employee_id"])
    app.refresh_from_db()
    payload2 = build_credit_disbursement_payload(app, connector=connector)
    assert payload2["idGestionnaire"] == "GEST-DEFAULT"


def test_id_produit_remb_product_overrides_repayment_method(
    tenant_a, catalog, connector, agency, prepared_product, prepared_client, officer,
):
    with tenant_context(tenant_a.id):
        RepaymentMethod.objects.filter(code="DEGRESSIVE").update(
            cbs_code="REMB-FROM-METHOD"
        )

    prepared_product.cbs_repayment_product_code = "REMB-FROM-PRODUCT"
    prepared_product.save(update_fields=["cbs_repayment_product_code"])
    app = _approved_app(
        tenant_a,
        product=prepared_product,
        client=prepared_client,
        agency=agency,
        officer=officer,
    )
    payload = build_credit_disbursement_payload(app, connector=connector)
    assert payload["idProduitRemb"] == "REMB-FROM-PRODUCT"

    prepared_product.cbs_repayment_product_code = ""
    prepared_product.save(update_fields=["cbs_repayment_product_code"])
    payload2 = build_credit_disbursement_payload(app, connector=connector)
    assert payload2["idProduitRemb"] == "REMB-FROM-METHOD"


def test_catalog_custom_codes_for_periodicity_and_currency(
    tenant_a, catalog, connector, agency, prepared_product, prepared_client, officer,
):
    with tenant_context(tenant_a.id):
        LoanPeriodicity.objects.filter(code="QUARTERLY").update(
            cbs_code="TRIM-CUSTOM", periods_per_year=4
        )
        Currency.objects.filter(code="EUR").update(cbs_code="EUR-CBS")

    app = _approved_app(
        tenant_a,
        product=prepared_product,
        client=prepared_client,
        agency=agency,
        officer=officer,
        periodicity="QUARTERLY",
        currency="EUR",
        duration_months=12,
    )
    payload = build_credit_disbursement_payload(app, connector=connector)
    assert payload["idPeriodicite"] == "TRIM-CUSTOM"
    assert payload["codeDevise"] == "EUR-CBS"
    assert payload["nombreEcheance"] == 4  # 12 mois / 12 * 4
    assert payload["idObjetFinancement"] == "EQUIPEMENT"
    assert payload["montantDemande"] == 700000.0  # montant approuvé
    assert payload["idPointService"] == "PS-AG01"  # agence > défaut


def test_bimonthly_maps_to_bimensuel_in_api_payload(
    tenant_a, catalog, connector, agency, prepared_product, prepared_client, officer,
):
    """BIMONTHLY → idPeriodicite=BIMENSUEL, 24 échéances sur 12 mois."""
    with tenant_context(tenant_a.id):
        assert LoanPeriodicity.objects.filter(
            code="BIMONTHLY", cbs_code="BIMENSUEL"
        ).exists()

    app = _approved_app(
        tenant_a,
        product=prepared_product,
        client=prepared_client,
        agency=agency,
        officer=officer,
        periodicity="BIMONTHLY",
        duration_months=12,
    )
    with override_settings(PUBLIC_API_BASE_URL="https://finflow.test"):
        payload = build_credit_disbursement_payload(app, connector=connector)

    assert payload["idPeriodicite"] == "BIMENSUEL"
    assert payload["nombreEcheance"] == 24
    assert payload["idGestionnaire"] == "GEST-USER"
    assert payload["idProduitCrd"] == prepared_product.cbs_product_code
    assert payload["idProduitRemb"]
    assert payload["codeDevise"] == "XOF"
    assert payload["idPointService"] == "PS-AG01"
    assert payload["callbackUrl"].endswith(
        f"/api/v1/cbs/callbacks/crd/{app.pk}/"
    )


def test_agency_point_of_service_fallback_to_defaults(
    tenant_a, catalog, connector, prepared_product, prepared_client, officer,
):
    with tenant_context(tenant_a.id):
        bare = Agency.objects.create(
            tenant=tenant_a, code="AG-BARE", name="Sans POS",
        )
    app = _approved_app(
        tenant_a,
        product=prepared_product,
        client=prepared_client,
        agency=bare,
        officer=officer,
    )
    payload = build_credit_disbursement_payload(app, connector=connector)
    assert payload["idPointService"] == "PS-DEFAULT"


# ---------------------------------------------------------------------------
# Erreurs bloquantes
# ---------------------------------------------------------------------------


def test_payload_errors_when_required_mappings_missing(
    tenant_a, catalog, connector, agency, prepared_product, officer,
):
    # Client sans identifiant CBS
    bare_client = Client.objects.create(
        tenant=tenant_a,
        reference="NO-CBS",
        client_type=Client.ClientType.INDIVIDUAL,
        first_name="X",
        last_name="Y",
        kyc_status=Client.KycStatus.VALIDATED,
    )
    app = _approved_app(
        tenant_a,
        product=prepared_product,
        client=bare_client,
        agency=agency,
        officer=officer,
        reference="ADV-ERR-1",
    )
    with pytest.raises(CoreBankingError, match="Identifiant adhérent"):
        build_credit_disbursement_payload(app, connector=connector)

    bare_client.cbs_client_id = "OK"
    bare_client.save(update_fields=["cbs_client_id"])

    # Sans cbs_product_code → fallback sur product.code
    prepared_product.cbs_product_code = ""
    prepared_product.save(update_fields=["cbs_product_code"])
    payload = build_credit_disbursement_payload(app, connector=connector)
    assert payload["idProduitCrd"] == prepared_product.code

    # Sans gestionnaire ni défaut connecteur
    connector.mapping_rules = {
        **connector.mapping_rules,
        "disbursement": {
            "mode": "LOCAL",
            "defaults": {
                "idPointService": "PS01",
                "idProduitRemb": "R1",
            },
        },
    }
    connector.save(update_fields=["mapping_rules"])
    orphan = User.objects.create_user(
        username="no_cbs",
        password="x",
        tenant=tenant_a,
        agency=agency,
        cbs_id="",
        employee_id="",
    )
    app2 = _approved_app(
        tenant_a,
        product=prepared_product,
        client=bare_client,
        agency=agency,
        officer=orphan,
        reference="ADV-ERR-2",
    )
    with pytest.raises(CoreBankingError, match="idGestionnaire"):
        build_credit_disbursement_payload(app2, connector=connector)


def test_missing_id_produit_remb_raises(
    tenant_a, catalog, connector, agency, prepared_product, prepared_client, officer,
):
    with tenant_context(tenant_a.id):
        RepaymentMethod.objects.filter(code="DEGRESSIVE").update(cbs_code="")
    prepared_product.cbs_repayment_product_code = ""
    prepared_product.save(update_fields=["cbs_repayment_product_code"])
    connector.mapping_rules = {
        **connector.mapping_rules,
        "disbursement": {
            "mode": "LOCAL",
            "defaults": {
                "idPointService": "PS01",
                "idGestionnaire": "G1",
            },
        },
    }
    connector.save(update_fields=["mapping_rules"])
    app = _approved_app(
        tenant_a,
        product=prepared_product,
        client=prepared_client,
        agency=agency,
        officer=officer,
        reference="ADV-ERR-REMB",
        repayment_mechanism="DEGRESSIVE",
    )
    with pytest.raises(CoreBankingError, match="idProduitRemb"):
        build_credit_disbursement_payload(app, connector=connector)


def test_period_count_uses_catalog_periods_per_year(tenant_a, catalog):
    with tenant_context(tenant_a.id):
        LoanPeriodicity.objects.filter(code="WEEKLY").update(periods_per_year=52)
    assert period_count(12, "WEEKLY", tenant_id=tenant_a.id) == 52
    assert resolve_periodicity_periods_per_year(tenant_a.id, "WEEKLY") == 52
    # Sans tenant : fallback historique
    assert period_count(12, "MONTHLY") == 12


# ---------------------------------------------------------------------------
# Validation serializer dossier
# ---------------------------------------------------------------------------


def test_credit_application_rejects_unknown_catalog_codes(
    tenant_a, catalog, prepared_product, prepared_client, agency, officer,
):
    with tenant_context(tenant_a.id):
        ser = CreditApplicationSerializer(
            data={
                "client": str(prepared_client.id),
                "product": str(prepared_product.id),
                "agency": str(agency.id),
                "amount_requested": "100000",
                "duration_months": 12,
                "periodicity": "BIWEEKLY_UNKNOWN",
                "repayment_mechanism": "DEGRESSIVE",
                "currency": "XOF",
            },
            context={"request": MagicMock(user=officer, FILES={})},
        )
        assert not ser.is_valid()
        assert "periodicity" in ser.errors


def test_credit_application_accepts_catalog_codes(
    tenant_a, catalog, prepared_product, prepared_client, agency, officer,
):
    with tenant_context(tenant_a.id):
        ser = CreditApplicationSerializer(
            data={
                "client": str(prepared_client.id),
                "product": str(prepared_product.id),
                "agency": str(agency.id),
                "amount_requested": "100000",
                "duration_months": 12,
                "periodicity": "MONTHLY",
                "repayment_mechanism": "IN_FINE",
                "currency": "XOF",
            },
            context={"request": MagicMock(user=officer, FILES={})},
        )
        assert ser.is_valid(), ser.errors


# ---------------------------------------------------------------------------
# API référentiels + isolation tenant
# ---------------------------------------------------------------------------


def test_api_catalog_crud_and_tenant_isolation(
    tenant_a, tenant_b, catalog, staff_admin,
):
    ensure_catalog_defaults(tenant_b)
    api = APIClient()
    api.force_authenticate(staff_admin)
    api.credentials(HTTP_X_TENANT_ID=str(tenant_a.id))

    # Liste filiale A
    res = api.get("/api/v1/loan-periodicities/")
    assert res.status_code == 200
    codes_a = {r["code"] for r in res.json()["results"]}
    assert "MONTHLY" in codes_a

    # Création custom sur A
    res_create = api.post(
        "/api/v1/repayment-methods/",
        {
            "code": "LINEAR_ADV",
            "label": "Linéaire avancé",
            "cbs_code": "REMB-LINEAR",
            "sort_order": 99,
            "is_active": True,
        },
        format="json",
    )
    assert res_create.status_code == 201, res_create.content
    created_id = res_create.json()["id"]

    # L'identifiant CBS du mécanisme configure idProduitRemb.
    res_patch = api.patch(
        f"/api/v1/repayment-methods/{created_id}/",
        {"cbs_code": "REMB-LINEAR-V2", "label": "Linéaire modifié"},
        format="json",
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["cbs_code"] == "REMB-LINEAR-V2"
    assert res_patch.json()["label"] == "Linéaire modifié"

    # Invisible pour filiale B
    api.credentials(HTTP_X_TENANT_ID=str(tenant_b.id))
    res_b = api.get("/api/v1/repayment-methods/")
    assert res_b.status_code == 200
    codes_b = {r["code"] for r in res_b.json()["results"]}
    assert "LINEAR_ADV" not in codes_b
    assert "DEGRESSIVE" in codes_b

    # Currencies API (revenir sur A)
    api.credentials(HTTP_X_TENANT_ID=str(tenant_a.id))
    res_cur = api.get("/api/v1/currencies/?is_active=true")
    assert res_cur.status_code == 200
    assert any(r["code"] == "XOF" for r in res_cur.json()["results"])


def test_api_user_cbs_id_create_and_patch(tenant_a, agency, staff_admin):
    from apps.catalog.models import CbsManager

    for code in ("GEST-NEW-99", "GEST-UPDATED"):
        CbsManager.all_tenants.create(tenant=tenant_a, code=code, label=code, cbs_code=code)
    api = APIClient()
    api.force_authenticate(staff_admin)
    api.credentials(HTTP_X_TENANT_ID=str(tenant_a.id))
    res = api.post(
        "/api/v1/users/",
        {
            "username": "gest_new",
            "first_name": "Gest",
            "last_name": "Nouveau",
            "email": "gest@example.com",
            "phone": "",
            "employee_id": "E99",
            "cbs_id": "GEST-NEW-99",
            "tenant": str(tenant_a.id),
            "agency": str(agency.id),
            "agency_ids": [str(agency.id)],
            "data_scope": "AGENCY",
            "is_group_level": False,
            "is_active": True,
            "group_ids": [],
            "password_delivery": "manual",
            "password": "FinFlow2026!",
            "password_confirm": "FinFlow2026!",
        },
        format="json",
    )
    assert res.status_code in (200, 201), res.content
    user_id = res.json()["id"]
    created = User.objects.get(pk=user_id)
    assert created.cbs_id == "GEST-NEW-99"

    res_patch = api.patch(
        f"/api/v1/users/{user_id}/",
        {"cbs_id": "GEST-UPDATED"},
        format="json",
    )
    assert res_patch.status_code == 200
    created.refresh_from_db()
    assert created.cbs_id == "GEST-UPDATED"


# ---------------------------------------------------------------------------
# REST Perfect mocké
# ---------------------------------------------------------------------------


def test_rest_adapter_crd_simple_success_and_business_error(tenant_a, catalog):
    with tenant_context(tenant_a.id):
        conn = CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="REST live",
            protocol="REST",
            base_url="https://serveur-api",
            mapping_rules={
                "endpoints": {"crd_simple": "gateway-perfect/crd/simple"},
            },
            auth_config={"access_token": "ABC"},
            is_active=True,
        )
    adapter = RestAdapter(conn)
    payload = {
        "externalId": "EXT-1",
        "callbackUrl": "https://finflow.test/cb",
        "idPointService": "PS01",
        "codeAdherent": "A1",
        "idPeriodicite": "MENSUEL",
        "taux": 7,
        "nombreEcheance": 12,
        "idObjetFinancement": "CONSOMMATION",
        "idGestionnaire": "G1",
        "idProduitCrd": "CRED",
        "idProduitRemb": "CC",
        "montantDemande": 100000,
        "codeDevise": "XOF",
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"{}"
    mock_resp.json.return_value = {
        "responseCode": 200,
        "message": "OK",
        "numDemande": "DEM1",
        "refDemande": "REF1",
        "numContrat": "CTR1",
        "limitCredit": 200000,
        "montant": 100000,
        "codeDevise": "XOF",
    }
    with patch("requests.post", return_value=mock_resp) as post:
        result = adapter.send("SUBMIT_CREDIT", payload)
    assert result["num_contrat"] == "CTR1"
    assert result["num_demande"] == "DEM1"
    post.assert_called_once()
    args, kwargs = post.call_args
    assert kwargs["url"].endswith("gateway-perfect/crd/simple")
    assert kwargs["headers"]["Authorization"] == "Bearer ABC"
    assert kwargs["json"]["externalId"] == "EXT-1"

    mock_fail = MagicMock()
    mock_fail.status_code = 200
    mock_fail.content = b"{}"
    mock_fail.json.return_value = {
        "responseCode": 409,
        "message": "Limite de crédit insuffisante !",
    }
    with patch("requests.post", return_value=mock_fail):
        with pytest.raises(CoreBankingError, match="Limite de crédit"):
            adapter.send("SUBMIT_CREDIT", payload)

    with pytest.raises(CoreBankingError, match="incomplet"):
        adapter.send("SUBMIT_CREDIT", {"externalId": "x"})


def test_perfect_authentification_form_urlencoded_and_access_token(tenant_a, catalog):
    """Doc Perfect : POST …/authentification → accessToken → Bearer sur crd/simple."""
    with tenant_context(tenant_a.id):
        conn = CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="REST Perfect auth",
            protocol="REST",
            base_url="https://serveur-api",
            mapping_rules={
                "endpoints": {
                    "authentification": "gateway-perfect/authentification",
                    "crd_simple": "gateway-perfect/crd/simple",
                },
            },
            auth_config={
                "username": "VOTRE_USER",
                "password": "VOTRE_PASS",
                "scope": "perfect",
            },
            is_active=True,
        )
    adapter = RestAdapter(conn)

    auth_resp = MagicMock()
    auth_resp.status_code = 200
    auth_resp.content = b"{}"
    auth_resp.json.return_value = {
        "accessToken": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.demo",
    }
    crd_resp = MagicMock()
    crd_resp.status_code = 200
    crd_resp.content = b"{}"
    crd_resp.json.return_value = {
        "responseCode": 200,
        "numDemande": "DEM-A",
        "refDemande": "REF-A",
        "numContrat": "CTR-A",
    }

    with patch("requests.post") as post:
        def _route(url, *args, **kwargs):
            if "authentification" in str(url):
                return auth_resp
            return crd_resp

        post.side_effect = _route
        result = adapter.send(
            "SUBMIT_CREDIT",
            {
                "externalId": "EXT-AUTH",
                "callbackUrl": "https://finflow.test/cb",
                "idPointService": "PS01",
                "codeAdherent": "A1",
                "idPeriodicite": "MENSUEL",
                "taux": 7,
                "nombreEcheance": 12,
                "idObjetFinancement": "CONSOMMATION",
                "idGestionnaire": "G1",
                "idProduitCrd": "CRED",
                "idProduitRemb": "CC",
                "montantDemande": 100000,
                "codeDevise": "XOF",
            },
        )

    assert result["num_contrat"] == "CTR-A"
    assert post.call_count == 2
    auth_args, auth_kwargs = post.call_args_list[0]
    assert auth_kwargs["url"].endswith("gateway-perfect/authentification")
    assert auth_kwargs["headers"]["Content-Type"] == (
        "application/x-www-form-urlencoded"
    )
    assert auth_kwargs["data"] == {
        "username": "VOTRE_USER",
        "password": "VOTRE_PASS",
        "scope": "perfect",
    }
    crd_args, crd_kwargs = post.call_args_list[1]
    assert crd_kwargs["url"].endswith("gateway-perfect/crd/simple")
    assert crd_kwargs["headers"]["Authorization"] == (
        "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.demo"
    )


def test_perfect_authentification_bad_credentials(tenant_a, catalog):
    with tenant_context(tenant_a.id):
        conn = CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="REST Perfect bad auth",
            protocol="REST",
            base_url="https://serveur-api",
            auth_config={"username": "bad", "password": "wrong"},
            is_active=True,
        )
    adapter = RestAdapter(conn)
    fail = MagicMock()
    fail.status_code = 401
    fail.content = b"{}"
    fail.json.return_value = {
        "error": "invalid_grant",
        "error_description": "Bad credentials",
    }
    with patch("requests.post", return_value=fail):
        with pytest.raises(CoreBankingError, match="Bad credentials"):
            adapter._resolve_bearer_token()


def test_submit_credit_cbs_mode_uses_rest_and_journals(
    tenant_a,
    catalog,
    agency,
    prepared_product,
    prepared_client,
    officer,
):
    with tenant_context(tenant_a.id):
        conn = CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="CBS REST mode",
            protocol="REST",
            base_url="https://serveur-api",
            mapping_rules={
                "disbursement": {
                    "mode": "CBS",
                    "defaults": {
                        "idPointService": "PS01",
                        "idGestionnaire": "G1",
                        "idProduitRemb": "CC",
                    },
                },
            },
            auth_config={"access_token": "TOK"},
            is_active=True,
        )
    prepared_product.cbs_product_code = "CRED-X"
    prepared_product.save(update_fields=["cbs_product_code"])
    app = _approved_app(
        tenant_a,
        product=prepared_product,
        client=prepared_client,
        agency=agency,
        officer=officer,
        reference="ADV-REST-1",
    )
    from tests.setup_helpers import configure_verified_cbs, prepare_setup
    configure_verified_cbs(app, conn, officer)
    prepare_setup(app)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"{}"
    mock_resp.json.return_value = {
        "responseCode": 200,
        "numDemande": "DEM-R",
        "refDemande": "REF-R",
        "numContrat": "CTR-R",
        "limitCredit": 900000,
        "montant": 700000,
        "codeDevise": "XOF",
    }
    with tenant_context(tenant_a.id):
        with patch("requests.post", return_value=mock_resp):
            result = submit_credit_to_cbs(app, connector=conn)
    assert result["mode"] == "CBS"
    assert result["num_contrat"] == "CTR-R"
    assert IntegrationLog.all_tenants.filter(
        operation="SUBMIT_CREDIT",
        status=IntegrationLog.Status.SUCCESS,
        idempotency_key=f"disburse:{app.pk}",
    ).exists()


# ---------------------------------------------------------------------------
# Callback + décaissement bout-en-bout
# ---------------------------------------------------------------------------


def test_callback_secret_and_updates(
    tenant_a, catalog, connector, agency, prepared_product, prepared_client, officer,
):
    app = _approved_app(
        tenant_a,
        product=prepared_product,
        client=prepared_client,
        agency=agency,
        officer=officer,
        reference="ADV-CB-1",
    )
    with tenant_context(tenant_a.id):
        with patch(
            "apps.contracts.services.missing_required_contracts", return_value=[]
        ), patch(
            "apps.workflow.services.has_pending_conditions", return_value=False
        ):
            from tests.setup_helpers import prepare_setup
            executor = prepare_setup(app)
            loan = disburse_application(app, user=executor)

    with pytest.raises(CoreBankingError, match="Secret"):
        apply_cbs_callback(
            app.pk,
            {"numContrat": "X", "context": "HACK"},
            secret="wrong",
        )

    with pytest.raises(CoreBankingError, match="Secret"):
        apply_cbs_callback(
            app.pk,
            {"numContrat": "X", "context": "HACK"},
            secret=None,
        )

    result = apply_cbs_callback(
        app.pk,
        {
            "numDemande": "DEM-CB",
            "refDemande": "REF-CB",
            "numContrat": "CTR-CB",
            "context": "DEBLOQUE",
        },
        secret="secret-test",
    )
    assert result["loan_id"] == str(loan.pk)
    loan.refresh_from_db()
    assert loan.cbs_contract_number == "CTR-CB"
    assert loan.cbs_disbursement_status == "DEBLOQUE"
    assert loan.core_banking_reference == "CTR-CB"


def test_disburse_api_endpoint_with_cbs_local(
    tenant_a,
    catalog,
    connector,
    agency,
    prepared_product,
    prepared_client,
    officer,
):
    # Droit de décaissement
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.get_for_model(CreditApplication)
    perm = Permission.objects.get(
        content_type=ct, codename="disburse_creditapplication"
    )
    officer.user_permissions.add(perm)
    officer.is_staff = True
    officer.save(update_fields=["is_staff"])

    app = _approved_app(
        tenant_a,
        product=prepared_product,
        client=prepared_client,
        agency=agency,
        officer=officer,
        reference="ADV-API-1",
        status=CreditApplication.Status.DISBURSEMENT_PENDING,
    )
    api = APIClient()
    api.force_authenticate(officer)
    with patch(
        "apps.contracts.services.missing_required_contracts", return_value=[]
    ), patch(
        "apps.workflow.services.has_pending_conditions", return_value=False
    ):
        from tests.setup_helpers import prepare_setup
        prepare_setup(app, executor=officer)
        res = api.post(
            f"/api/v1/credit-applications/{app.pk}/disburse/",
            {},
            format="json",
            HTTP_X_TENANT_ID=str(tenant_a.id),
        )
    assert res.status_code == 200, res.content
    data = res.json()
    assert data["cbs_contract_number"].startswith("CONTRAT-SIM-")
    assert data["cbs_external_id"] == "ADV-API-1"
    assert data["cbs_disbursement_status"] == "SUBMITTED"
    app.refresh_from_db()
    assert app.status == CreditApplication.Status.DISBURSED


def test_disburse_blocks_when_cbs_rejects(
    tenant_a, catalog, connector, agency, prepared_product, prepared_client, officer,
):
    connector.mapping_rules = {
        **connector.mapping_rules,
        "simulate": {"credit_submit_fail": True},
    }
    connector.save(update_fields=["mapping_rules"])
    app = _approved_app(
        tenant_a,
        product=prepared_product,
        client=prepared_client,
        agency=agency,
        officer=officer,
        reference="ADV-FAIL-1",
    )
    with tenant_context(tenant_a.id):
        with patch(
            "apps.contracts.services.missing_required_contracts", return_value=[]
        ), patch(
            "apps.workflow.services.has_pending_conditions", return_value=False
        ):
            from tests.setup_helpers import prepare_setup
            executor = prepare_setup(app)
            with pytest.raises(WorkflowError, match="Limite"):
                disburse_application(app, user=executor)
    assert not hasattr(app, "loan") or not CreditApplication.objects.filter(
        pk=app.pk, status=CreditApplication.Status.DISBURSED
    ).exists()


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def test_bootstrap_tenant_seeds_catalog(tenant_a):
    # tenant_a starts empty of catalog
    assert LoanPeriodicity.all_tenants.filter(tenant=tenant_a).count() == 0
    bootstrap_tenant(tenant_a)
    assert LoanPeriodicity.all_tenants.filter(tenant=tenant_a).count() == 7
    assert RepaymentMethod.all_tenants.filter(tenant=tenant_a).count() == 3
    assert Currency.all_tenants.filter(tenant=tenant_a).count() >= 4
    with tenant_context(tenant_a.id):
        conn = CoreBankingConnector.objects.get(name="CBS Perfect")
        assert conn.protocol == "REST"
        assert conn.mapping_rules["provider"] == "perfect"
        assert conn.mapping_rules["endpoints"]["authentification"] == (
            "gateway-perfect/authentification"
        )
        assert conn.mapping_rules["endpoints"]["crd_simple"] == (
            "gateway-perfect/crd/simple"
        )
        assert conn.mapping_rules["disbursement"]["periodicity_map"]["BIMONTHLY"] == (
            "BIMENSUEL"
        )
        assert conn.auth_config.get("scope") == "perfect"
    # Idempotent
    bootstrap_tenant(tenant_a)
    assert LoanPeriodicity.all_tenants.filter(tenant=tenant_a).count() == 7
    with tenant_context(tenant_a.id):
        assert CoreBankingConnector.objects.filter(name="CBS Perfect").count() == 1


def test_ensure_perfect_connector_upgrades_existing_endpoints(tenant_a):
    from apps.corebanking.perfect_defaults import ensure_perfect_connector

    with tenant_context(tenant_a.id):
        old = CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="CBS Legacy",
            protocol="REST",
            base_url="https://serveur-api",
            mapping_rules={
                "endpoints": {"adh_situation": "gateway-perfect/adh/situation"},
                "disbursement": {"mode": "CBS"},
            },
            auth_config={"username": "u", "password": "p"},
            is_active=True,
        )
    conn, created = ensure_perfect_connector(tenant_a, demo=False)
    assert created is False
    assert conn.pk == old.pk
    assert conn.mapping_rules["endpoints"]["authentification"] == (
        "gateway-perfect/authentification"
    )
    assert conn.mapping_rules["endpoints"]["crd_simple"] == (
        "gateway-perfect/crd/simple"
    )
    assert conn.mapping_rules["disbursement"]["periodicity_map"]["MONTHLY"] == (
        "MENSUEL"
    )
    assert conn.auth_config["scope"] == "perfect"
    assert conn.auth_config["username"] == "u"


def test_resolve_helpers_fallback_when_catalog_empty(tenant_a):
    assert resolve_periodicity_cbs(
        tenant_a.id, "MONTHLY", fallback_map={"MONTHLY": "MENSUEL"}
    ) == "MENSUEL"
    assert resolve_repayment_cbs(tenant_a.id, "DEGRESSIVE") == ""
    assert resolve_currency_cbs(tenant_a.id, "XOF") == "XOF"


@override_settings(PUBLIC_API_BASE_URL="https://api.finflow.test")
def test_callback_url_uses_public_api_base(
    tenant_a, catalog, connector, agency, prepared_product, prepared_client, officer,
):
    app = _approved_app(
        tenant_a,
        product=prepared_product,
        client=prepared_client,
        agency=agency,
        officer=officer,
        reference="ADV-URL-1",
    )
    payload = build_credit_disbursement_payload(app, connector=connector)
    assert payload["callbackUrl"] == (
        f"https://api.finflow.test/api/v1/cbs/callbacks/crd/{app.pk}/"
    )
