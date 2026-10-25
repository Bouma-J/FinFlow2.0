"""Import client depuis CBS (situation adhérent)."""
from datetime import date

import pytest
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User
from apps.clients.cbs_services import import_client_from_cbs, preview_client_from_cbs
from apps.clients.models import Client
from apps.common.tenancy import tenant_context
from apps.corebanking.models import CoreBankingConnector
from apps.corebanking.services import get_client_situation

pytestmark = pytest.mark.django_db


@pytest.fixture
def cbs_connector(tenant_a):
    with tenant_context(tenant_a.id):
        return CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="CBS Test",
            protocol=CoreBankingConnector.Protocol.REST,
            base_url="",  # force simulate
            mapping_rules={
                "force_simulate": True,
                "simulate": {
                    "client_est_valide_default": False,
                    "client_nom_default": "Traoré Aminata",
                },
            },
            is_active=True,
        )


def test_get_client_situation_simulated(tenant_a, cbs_connector):
    with tenant_context(tenant_a.id):
        result = get_client_situation(
            tenant_a.id, code_adherent="A00999"
        )
    assert result["full_name"] == "Traoré Aminata"
    assert result["code_adherent"] == "A00999"
    assert result["last_name"] == "Traoré"
    assert result["first_name"] == "Aminata"
    assert result["kyc_alert"] is True
    assert result["est_valide"] is False


def test_import_individual_maps_identity_fields(tenant_a, cbs_connector):
    user = User.objects.create(username="import_op", tenant=tenant_a)
    with tenant_context(tenant_a.id):
        client, preview = import_client_from_cbs(
            tenant_id=tenant_a.id,
            user=user,
            data={
                "client_type": "INDIVIDUAL",
                "code_adherent": "A00999",
            },
        )
    assert client.cbs_client_id == "A00999"
    assert client.last_name == "Traoré"
    assert client.first_name == "Aminata"
    assert client.birth_date == date(1990, 3, 12)
    assert client.civility == "MRS"
    assert client.national_id == "CI1234567890"
    assert client.client_type == Client.ClientType.INDIVIDUAL
    assert client.kyc_status == Client.KycStatus.PENDING
    assert client.cbs_full_name == "Traoré Aminata"
    assert client.cbs_situation.get("code_adherent") == "A00999"
    assert client.cbs_situation.get("raw", {}).get("codeAdherent") == "A00999"
    assert client.cbs_synced_at is not None
    assert client.cbs_registration_date == date(2020, 1, 15)
    assert client.cbs_point_of_service_id == "PS01"
    assert client.cbs_point_of_service_name == "Agence Principale"
    assert client.cbs_context == "ADHERENT SITUATION"
    assert client.cbs_est_valide is False
    assert client.cbs_credit_limit is not None
    assert preview["kyc_alert"] is True
    assert preview["can_import"] is True
    assert preview["missing_required"] == []


def test_import_corporate_by_identification(tenant_a, cbs_connector):
    user = User.objects.create(username="import_corp", tenant=tenant_a)
    with tenant_context(tenant_a.id):
        client, preview = import_client_from_cbs(
            tenant_id=tenant_a.id,
            user=user,
            data={
                "client_type": "CORPORATE",
                "identification_nationale": "IFU-CI-999",
            },
        )
    assert client.client_type == Client.ClientType.CORPORATE
    assert client.ifu == "IFU-CI-999"
    assert "SODECI" in client.company_name
    assert client.rccm
    assert preview["identification_nationale"] == "IFU-CI-999"
    assert preview["can_import"] is True


def test_preview_requires_client_type(tenant_a, cbs_connector):
    with tenant_context(tenant_a.id):
        with pytest.raises(ValidationError) as exc:
            preview_client_from_cbs(
                tenant_id=tenant_a.id, data={"code_adherent": "A1"}
            )
    assert "client_type" in exc.value.detail


def test_preview_rejects_professional(tenant_a, cbs_connector):
    with tenant_context(tenant_a.id):
        with pytest.raises(ValidationError):
            preview_client_from_cbs(
                tenant_id=tenant_a.id,
                data={"client_type": "PROFESSIONAL", "code_adherent": "A1"},
            )


def test_preview_requires_identifier(tenant_a, cbs_connector):
    with tenant_context(tenant_a.id):
        with pytest.raises(ValidationError):
            preview_client_from_cbs(
                tenant_id=tenant_a.id, data={"client_type": "INDIVIDUAL"}
            )
        with pytest.raises(ValidationError):
            preview_client_from_cbs(
                tenant_id=tenant_a.id, data={"client_type": "CORPORATE"}
            )


def test_preview_flags_incomplete_cbs_data(tenant_a, cbs_connector):
    rules = dict(cbs_connector.mapping_rules or {})
    simulate = dict(rules.get("simulate") or {})
    simulate["client_situation_by_id"] = {
        "A-INCOMPLET": {
            "responseCode": 200,
            "codeAdherent": "A-INCOMPLET",
            "nom": "Koné",
            "prenoms": "",
            "nomAdherent": "Koné",
            "estValide": True,
            "telephone": "N/A",
            "ville": "",
            "adresse": "",
            "numPieceIdentite": "",
        }
    }
    rules["simulate"] = simulate
    cbs_connector.mapping_rules = rules
    cbs_connector.save(update_fields=["mapping_rules"])

    with tenant_context(tenant_a.id):
        preview = preview_client_from_cbs(
            tenant_id=tenant_a.id,
            data={"client_type": "INDIVIDUAL", "code_adherent": "A-INCOMPLET"},
        )
        with pytest.raises(ValidationError) as exc:
            import_client_from_cbs(
                tenant_id=tenant_a.id,
                user=User.objects.create(username="import_incomplete", tenant=tenant_a),
                data={"client_type": "INDIVIDUAL", "code_adherent": "A-INCOMPLET"},
            )

    assert preview["can_import"] is False
    keys = {item["key"] for item in preview["missing_required"]}
    assert "first_name" in keys
    assert "phone" in keys
    assert "num_piece_identite" in keys
    assert "city" in keys
    assert "address" in keys
    message = str(exc.value.detail)
    assert "Mettez à jour" in message
    assert "CBS" in message


def test_import_rejects_expired_id_document(tenant_a, cbs_connector):
    rules = dict(cbs_connector.mapping_rules or {})
    simulate = dict(rules.get("simulate") or {})
    simulate["client_situation_by_id"] = {
        "A-EXPIRE": {
            "responseCode": 200,
            "codeAdherent": "A-EXPIRE",
            "nom": "Koné",
            "prenoms": "Awa",
            "nomAdherent": "Koné Awa",
            "estValide": True,
            "telephone": "+2250700000000",
            "ville": "Abidjan",
            "adresse": "Cocody",
            "numPieceIdentite": "CI999",
            "dateNaissance": "1990-03-12",
            "dateEtablissementPiece": "2010-01-10",
            "dateExpirationPiece": "2020-01-10",
        }
    }
    rules["simulate"] = simulate
    cbs_connector.mapping_rules = rules
    cbs_connector.save(update_fields=["mapping_rules"])

    with tenant_context(tenant_a.id):
        preview = preview_client_from_cbs(
            tenant_id=tenant_a.id,
            data={"client_type": "INDIVIDUAL", "code_adherent": "A-EXPIRE"},
        )
        with pytest.raises(ValidationError) as exc:
            import_client_from_cbs(
                tenant_id=tenant_a.id,
                user=User.objects.create(username="import_expired", tenant=tenant_a),
                data={"client_type": "INDIVIDUAL", "code_adherent": "A-EXPIRE"},
            )

    assert preview["can_import"] is False
    reasons = {
        item["key"]: item["reason"] for item in preview["missing_required"]
    }
    assert reasons["id_document_expiry_date"] == "expired"
    assert "expirée" in str(exc.value.detail)


def test_import_rejects_duplicate_cbs_id(tenant_a, cbs_connector):
    user = User.objects.create(username="import_dup", tenant=tenant_a)
    with tenant_context(tenant_a.id):
        import_client_from_cbs(
            tenant_id=tenant_a.id,
            user=user,
            data={"client_type": "INDIVIDUAL", "code_adherent": "A00999"},
        )
        with pytest.raises(ValidationError) as exc:
            import_client_from_cbs(
                tenant_id=tenant_a.id,
                user=user,
                data={"client_type": "INDIVIDUAL", "code_adherent": "A00999"},
            )
    assert "existe déjà" in str(exc.value.detail)
