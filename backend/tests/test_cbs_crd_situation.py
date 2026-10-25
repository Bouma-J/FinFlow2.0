"""Perfect crd/situation → GET_LOAN_STATUS / main levée."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.common.tenancy import tenant_context
from apps.corebanking.models import CoreBankingConnector
from apps.corebanking.services import (
    CoreBankingError,
    RestAdapter,
    USER_MSG_CBS_GENERIC,
    USER_MSG_CBS_NOT_CONFIGURED,
    USER_MSG_CBS_UNAVAILABLE,
    _normalize_credit_schedule,
    compute_cbs_overdue,
    get_loan_status,
    user_message_for_cbs_error,
)
from apps.catalog.defaults import ensure_catalog_defaults

pytestmark = pytest.mark.django_db


def test_normalize_schedule_all_paid():
    settled, outstanding = _normalize_credit_schedule(
        {
            "datas": [
                {"echeance": 1, "montantTotal": 100, "statut": "Payée"},
                {"echeance": 2, "montantTotal": 100, "statut": "Payée"},
            ]
        }
    )
    assert settled is True
    assert outstanding == 0


def test_normalize_schedule_partial_outstanding():
    settled, outstanding = _normalize_credit_schedule(
        {
            "datas": [
                {"echeance": 1, "montantTotal": 42917, "statut": "Payée"},
                {"echeance": 2, "montantTotal": 42683, "statut": "En attente"},
            ]
        }
    )
    assert settled is False
    assert outstanding == Decimal("42683")


def test_normalize_vision_loans_sums_encours():
    settled, outstanding = _normalize_credit_schedule(
        {
            "datas": [
                {"numeroPret": "P1", "encours": 100, "montantPret": 100},
                {"numeroPret": "P2", "encours": 50.5, "montantPret": 50.5},
            ]
        }
    )
    assert settled is False
    assert outstanding == Decimal("150.5")


def test_rest_adapter_crd_situation_maps_settled(tenant_a):
    ensure_catalog_defaults(tenant_a)
    with tenant_context(tenant_a.id):
        conn = CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="REST crd situation",
            protocol="REST",
            base_url="https://serveur-api",
            mapping_rules={
                "endpoints": {
                    "crd_situation": "gateway-perfect/crd/situation",
                },
            },
            auth_config={"access_token": "TOK"},
            is_active=True,
        )
    adapter = RestAdapter(conn)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"{}"
    mock_resp.json.return_value = {
        "responseCode": 200,
        "message": "OK",
        "numDemande": "DEM00556",
        "refDemande": "REF-DEM-2023-00556",
        "numContrat": "CONTRAT-CRED-123",
        "montant": 500000,
        "codeDevise": "XOF",
        "datas": [
            {
                "echeance": 1,
                "date": "2023-11-27",
                "montantCapital": 40000,
                "montantInteret": 2917,
                "montantTotal": 42917,
                "statut": "Payée",
            },
            {
                "echeance": 2,
                "date": "2023-12-27",
                "montantCapital": 40000,
                "montantInteret": 2683,
                "montantTotal": 42683,
                "statut": "Payée",
            },
        ],
        "context": "CREDIT SITUATION",
    }
    with patch("requests.post", return_value=mock_resp) as post:
        result = adapter.send(
            "GET_LOAN_STATUS",
            {
                "loan_ref": "REF-DEM-2023-00556",
                "codeAdherent": "A0012345",
                "currency": "XOF",
            },
        )
    assert result["settled"] is True
    assert result["outstanding"] == "0"
    assert result["num_contrat"] == "CONTRAT-CRED-123"
    args, kwargs = post.call_args
    assert kwargs["url"].endswith("gateway-perfect/crd/situation")
    assert kwargs["json"]["refDemande"] == "REF-DEM-2023-00556"
    assert kwargs["json"]["codeAdherent"] == "A0012345"
    assert kwargs["headers"]["Authorization"] == "Bearer TOK"


def test_rest_adapter_crd_situation_not_found(tenant_a):
    ensure_catalog_defaults(tenant_a)
    with tenant_context(tenant_a.id):
        conn = CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="REST crd 409",
            protocol="REST",
            base_url="https://serveur-api",
            auth_config={"access_token": "TOK"},
            is_active=True,
        )
    adapter = RestAdapter(conn)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"{}"
    mock_resp.json.return_value = {
        "responseCode": 409,
        "message": "Demande de crédit introuvable !",
    }
    with patch("requests.post", return_value=mock_resp):
        with pytest.raises(CoreBankingError, match="introuvable"):
            adapter.send(
                "GET_LOAN_STATUS",
                {"loan_ref": "REF-UNKNOWN", "currency": "XOF"},
            )


def test_get_loan_status_via_simulated_connector(tenant_a):
    ensure_catalog_defaults(tenant_a)
    with tenant_context(tenant_a.id):
        CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="sim ML",
            protocol="REST",
            base_url="https://x",
            mapping_rules={
                "force_simulate": True,
                "simulate": {"loan_settled_default": True},
            },
            is_active=True,
        )
        result = get_loan_status(tenant_a.id, "REF-OK")
        assert result["settled"] is True
        assert result["outstanding"] == 0

        result_open = get_loan_status(tenant_a.id, "UNSOLDE-TEST-01")
        assert result_open["settled"] is False
        assert result_open["outstanding"] > 0
        assert result_open["days_overdue"] >= 1


def test_compute_cbs_overdue_uses_oldest_unpaid_due_date():
    as_of = date(2026, 9, 10)
    result = compute_cbs_overdue(
        {
            "datas": [
                {
                    "date": "2026-07-01",
                    "montantTotal": 10000,
                    "statut": "Payée",
                },
                {
                    "date": "2026-08-01",
                    "montantTotal": 20000,
                    "statut": "En attente",
                },
                {
                    "date": "2026-10-01",
                    "montantTotal": 30000,
                    "statut": "En attente",
                },
            ]
        },
        as_of=as_of,
    )
    assert result["settled"] is False
    assert result["days_overdue"] == 40
    assert result["overdue_amount"] == Decimal("20000")


def test_user_message_for_cbs_error_hides_technical_details():
    assert (
        user_message_for_cbs_error(
            "Impossible de joindre le CBS (situation crédit) "
            "(HTTPSConnectionPool(host='x', port=443): Max retries exceeded)"
        )
        == USER_MSG_CBS_UNAVAILABLE
    )
    assert (
        user_message_for_cbs_error(
            "Aucun connecteur Core Banking actif pour cette filiale. "
            "Configurez-en un dans Administration → Connecteurs CBS."
        )
        == USER_MSG_CBS_NOT_CONFIGURED
    )
    assert user_message_for_cbs_error("Adhérent introuvable !") == (
        "Adhérent introuvable !"
    )
    assert (
        user_message_for_cbs_error("Échec situation crédit CBS (HTTP 500).")
        == USER_MSG_CBS_GENERIC
    )
