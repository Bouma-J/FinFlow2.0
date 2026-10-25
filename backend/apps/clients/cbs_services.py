"""Import client depuis le Core Banking (situation adhérent)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.common.tenancy import get_current_tenant_id
from apps.corebanking.services import CoreBankingError, get_client_situation
from apps.tenants.models import Agency

from .models import Civility, Client, MaritalStatus

IMPORT_TYPES = {
    Client.ClientType.INDIVIDUAL,
    Client.ClientType.CORPORATE,
}

_CIVILITY_MAP = {
    "M": Civility.MR,
    "M.": Civility.MR,
    "MR": Civility.MR,
    "MONSIEUR": Civility.MR,
    "MME": Civility.MRS,
    "MME.": Civility.MRS,
    "MRS": Civility.MRS,
    "MADAME": Civility.MRS,
    "MLLE": Civility.MISS,
    "MLLE.": Civility.MISS,
    "MISS": Civility.MISS,
    "MADEMOISELLE": Civility.MISS,
}

_MARITAL_MAP = {
    "CELIBATAIRE": MaritalStatus.SINGLE,
    "CÉLIBATAIRE": MaritalStatus.SINGLE,
    "SINGLE": MaritalStatus.SINGLE,
    "C": MaritalStatus.SINGLE,
    "MARIE": MaritalStatus.MARRIED,
    "MARIÉ": MaritalStatus.MARRIED,
    "MARIEE": MaritalStatus.MARRIED,
    "MARIÉE": MaritalStatus.MARRIED,
    "MARRIED": MaritalStatus.MARRIED,
    "DIVORCE": MaritalStatus.DIVORCED,
    "DIVORCÉ": MaritalStatus.DIVORCED,
    "DIVORCEE": MaritalStatus.DIVORCED,
    "DIVORCÉE": MaritalStatus.DIVORCED,
    "DIVORCED": MaritalStatus.DIVORCED,
    "VEUF": MaritalStatus.WIDOWED,
    "VEUVE": MaritalStatus.WIDOWED,
    "WIDOWED": MaritalStatus.WIDOWED,
}


def parse_client_type(data: dict) -> str:
    client_type = str(data.get("client_type") or data.get("clientType") or "")
    client_type = client_type.strip().upper()
    if client_type not in IMPORT_TYPES:
        raise ValidationError(
            {
                "client_type": (
                    "Choisissez le type de client : personne physique "
                    "ou personne morale."
                )
            }
        )
    return client_type


def _blank(value) -> str:
    text = str(value or "").strip()
    if text.upper() in {"", "N/A", "NA", "EMPTY"}:
        return ""
    return text


def _parse_date(value):
    text = _blank(value)[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _parse_decimal(value):
    text = _blank(value)
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, TypeError, ValueError):
        return None


def _parse_int(value):
    text = _blank(value)
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _map_civility(value: str) -> str:
    return _CIVILITY_MAP.get(_blank(value).upper(), "")


def _map_marital(value: str) -> str:
    key = (
        _blank(value)
        .upper()
        .replace("É", "E")
        .replace("È", "E")
    )
    return {
        "CELIBATAIRE": MaritalStatus.SINGLE,
        "SINGLE": MaritalStatus.SINGLE,
        "C": MaritalStatus.SINGLE,
        "MARIE": MaritalStatus.MARRIED,
        "MARIEE": MaritalStatus.MARRIED,
        "MARRIED": MaritalStatus.MARRIED,
        "DIVORCE": MaritalStatus.DIVORCED,
        "DIVORCEE": MaritalStatus.DIVORCED,
        "DIVORCED": MaritalStatus.DIVORCED,
        "VEUF": MaritalStatus.WIDOWED,
        "VEUVE": MaritalStatus.WIDOWED,
        "WIDOWED": MaritalStatus.WIDOWED,
    }.get(key, _MARITAL_MAP.get(_blank(value).upper(), ""))


def build_cbs_situation_snapshot(preview: dict) -> dict:
    """Copie de sauvegarde JSON (normalisée + raw), en plus des colonnes."""
    snapshot: dict = {}
    for key, value in (preview or {}).items():
        if hasattr(value, "isoformat"):
            snapshot[key] = value.isoformat()
        elif isinstance(value, Decimal):
            snapshot[key] = str(value)
        elif isinstance(value, (str, int, float, bool, type(None), list, dict)):
            snapshot[key] = value
        else:
            snapshot[key] = str(value)
    return snapshot


def parse_identifiers(data: dict, client_type: str) -> dict:
    code = _blank(data.get("code_adherent") or data.get("codeAdherent"))
    num_manuel = _blank(data.get("num_manuel") or data.get("numManuel"))
    num_piece = _blank(
        data.get("num_piece_identite") or data.get("numPieceIdentite")
    )
    identification = _blank(
        data.get("identification_nationale")
        or data.get("identificationNationale")
    )
    num_carte = _blank(
        data.get("num_carte_operateur")
        or data.get("numCarteOperateurEconomique")
        or data.get("rccm")
    )

    if client_type == Client.ClientType.INDIVIDUAL:
        if not (code or num_manuel or num_piece):
            raise ValidationError(
                {
                    "detail": (
                        "Indiquez au moins un identifiant CBS : code adhérent, "
                        "n° manuel ou n° de pièce d'identité."
                    )
                }
            )
    elif not (code or num_manuel or identification or num_carte):
        raise ValidationError(
            {
                "detail": (
                    "Indiquez au moins un identifiant CBS : code adhérent, "
                    "n° manuel, identification nationale ou n° RCCM / carte."
                )
            }
        )

    return {
        "code_adherent": code,
        "num_manuel": num_manuel,
        "num_piece_identite": num_piece,
        "identification_nationale": identification,
        "num_carte_operateur": num_carte,
        "client_type": client_type,
    }


# Champs KYC / identité exigés pour créer le client dans FinFlow.
# Absence ou valeur vide (N/A) → blocage : correction dans le CBS d'abord.
REQUIRED_INDIVIDUAL = (
    ("last_name", "Nom"),
    ("first_name", "Prénoms"),
    ("birth_date", "Date de naissance"),
    ("num_piece_identite", "N° pièce d'identité"),
    ("id_document_issue_date", "Date d'établissement de la pièce"),
    ("id_document_expiry_date", "Date d'expiration de la pièce"),
    ("phone", "Téléphone"),
    ("city", "Ville"),
    ("address", "Adresse"),
    ("code_adherent", "Code adhérent"),
)
REQUIRED_CORPORATE = (
    ("company_name", "Raison sociale"),
    ("identification_nationale", "Identification nationale (IFU)"),
    ("num_carte_operateur", "N° carte / RCCM"),
    ("phone", "Téléphone"),
    ("address", "Adresse / siège social"),
    ("code_adherent", "Code adhérent"),
)


def _preview_text(preview: dict, *keys) -> str:
    for key in keys:
        text = _blank(preview.get(key))
        if text:
            return text
    return ""


def collect_cbs_import_issues(preview: dict, client_type: str) -> list[dict]:
    """Contrôle les informations obligatoires renvoyées par le CBS."""
    issues: list[dict] = []
    required = (
        REQUIRED_INDIVIDUAL
        if client_type == Client.ClientType.INDIVIDUAL
        else REQUIRED_CORPORATE
    )
    for key, label in required:
        if key == "company_name":
            value = _preview_text(preview, "company_name", "full_name")
        elif key == "address" and client_type == Client.ClientType.CORPORATE:
            value = _preview_text(preview, "head_office", "address")
        elif key == "num_carte_operateur":
            value = _preview_text(preview, "num_carte_operateur", "rccm")
        else:
            value = _preview_text(preview, key)
        if not value:
            issues.append({"key": key, "label": label, "reason": "missing"})
            continue
        if key in {
            "birth_date",
            "id_document_issue_date",
            "id_document_expiry_date",
        } and _parse_date(value) is None:
            issues.append({"key": key, "label": label, "reason": "invalid"})

    expiry = _parse_date(preview.get("id_document_expiry_date"))
    if (
        client_type == Client.ClientType.INDIVIDUAL
        and expiry
        and expiry < date.today()
        and not any(i["key"] == "id_document_expiry_date" for i in issues)
    ):
        issues.append(
            {
                "key": "id_document_expiry_date",
                "label": "Date d'expiration de la pièce",
                "reason": "expired",
            }
        )
    return issues


def format_cbs_import_block_message(issues: list[dict]) -> str:
    if not issues:
        return ""
    parts = []
    for issue in issues:
        label = issue["label"]
        reason = issue.get("reason")
        if reason == "expired":
            parts.append(f"{label} (pièce expirée)")
        elif reason == "invalid":
            parts.append(f"{label} (date invalide)")
        else:
            parts.append(label)
    listed = ", ".join(parts)
    return (
        "Impossible d'enregistrer ce client dans FinFlow : des informations "
        f"obligatoires sont absentes ou incorrectes dans le CBS ({listed}). "
        "Mettez à jour ces données dans le core banking, puis relancez "
        "la recherche."
    )


def attach_cbs_completeness(preview: dict, client_type: str) -> dict:
    issues = collect_cbs_import_issues(preview, client_type)
    preview["missing_required"] = issues
    preview["can_import"] = not issues
    if issues:
        preview["import_block_message"] = format_cbs_import_block_message(issues)
    else:
        preview.pop("import_block_message", None)
    return preview


def preview_client_from_cbs(*, tenant_id, data: dict) -> dict:
    client_type = parse_client_type(data)
    ids = parse_identifiers(data, client_type)
    try:
        preview = get_client_situation(tenant_id, **ids)
    except CoreBankingError as exc:
        raise ValidationError({"detail": str(exc)}) from exc
    preview["client_type"] = client_type
    return attach_cbs_completeness(preview, client_type)


def _resolve_agency(*, tenant_id, user, point_of_service: str):
    qs = Agency.objects.all()
    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)
    if point_of_service:
        match = qs.filter(cbs_point_of_service_id=point_of_service).first()
        if match:
            return match
    agency_id = getattr(user, "agency_id", None)
    if agency_id:
        return qs.filter(pk=agency_id).first()
    return None


def map_preview_to_client_fields(
    *,
    preview: dict,
    client_type: str,
    tenant_id,
    user,
    agency,
    kyc_status: str,
) -> dict:
    """
    Mapping champ-par-champ situation CBS → colonnes ``Client``.

    Correspondance API normalisée → modèle :
    - full_name → cbs_full_name (+ last_name si nom/prénom absents)
    - last_name / first_name → last_name / first_name
    - company_name / sigle → company_name / sigle
    - code_adherent → cbs_client_id
    - num_manuel → cbs_account_number
    - num_piece_identite → national_id
    - identification_nationale → ifu
    - num_carte_operateur → rccm
    - num_ordre → cbs_order_number
    - birth_date → birth_date
    - birth_place → birth_country
    - civility / marital_status → civility / marital_status
    - spouse_name → spouse_last_name
    - id_document_* → id_document_*
    - id_profession → cbs_profession_id ; profession → profession
    - id_nationalite → cbs_nationality_id ; nationality → nationality
    - date_creation → cbs_creation_date
    - head_office → head_office (+ address morale)
    - id_secteur_activite → cbs_sector_id
    - id_type_client → cbs_client_type_id
    - id_zone → cbs_zone_id
    - id_produit_epg → cbs_savings_product_id
    - nbre_signature → cbs_signature_count
    - distance → cbs_distance
    - phone / email / city / address / boite_postale
    - date_inscription → cbs_registration_date
    - limit_credit → cbs_credit_limit
    - est_valide → cbs_est_valide
    - id_point_service / nom_point_service → cbs_point_of_service_*
    - context / message → cbs_context / cbs_message
    - raw.externalId → cbs_external_id
    """
    raw = preview.get("raw") if isinstance(preview.get("raw"), dict) else {}
    code = _blank(preview.get("code_adherent"))

    fields = {
        "tenant_id": tenant_id or get_current_tenant_id(),
        "client_type": client_type,
        "agency": agency,
        "phone": _blank(preview.get("phone")),
        "email": _blank(preview.get("email")),
        "city": _blank(preview.get("city")),
        "address": _blank(preview.get("address")),
        "postal_box": _blank(preview.get("boite_postale")),
        "head_office": _blank(preview.get("head_office")),
        "sigle": _blank(preview.get("sigle")),
        "cbs_client_id": code,
        "cbs_account_number": _blank(preview.get("num_manuel")),
        "cbs_full_name": _blank(preview.get("full_name")),
        "cbs_order_number": _blank(preview.get("num_ordre")),
        "cbs_profession_id": _blank(preview.get("id_profession")),
        "cbs_nationality_id": _blank(preview.get("id_nationalite")),
        "cbs_sector_id": _blank(preview.get("id_secteur_activite")),
        "cbs_client_type_id": _blank(preview.get("id_type_client")),
        "cbs_zone_id": _blank(preview.get("id_zone")),
        "cbs_savings_product_id": _blank(preview.get("id_produit_epg")),
        "cbs_signature_count": _parse_int(preview.get("nbre_signature")),
        "cbs_distance": _parse_decimal(preview.get("distance")),
        "cbs_registration_date": _parse_date(preview.get("date_inscription")),
        "cbs_creation_date": _parse_date(preview.get("date_creation")),
        "cbs_credit_limit": _parse_decimal(preview.get("limit_credit")),
        "cbs_est_valide": (
            bool(preview.get("est_valide"))
            if preview.get("est_valide") is not None
            else None
        ),
        "cbs_point_of_service_id": _blank(preview.get("id_point_service")),
        "cbs_point_of_service_name": _blank(preview.get("nom_point_service")),
        "cbs_external_id": _blank(
            raw.get("externalId") or preview.get("external_id")
        ),
        "cbs_context": _blank(preview.get("context")),
        "cbs_message": _blank(preview.get("message")),
        "cbs_synced_at": timezone.now(),
        "cbs_situation": build_cbs_situation_snapshot(preview),
        "kyc_status": kyc_status,
        "created_by": user if getattr(user, "is_authenticated", False) else None,
        "updated_by": user if getattr(user, "is_authenticated", False) else None,
    }

    if client_type == Client.ClientType.INDIVIDUAL:
        last_name = _blank(preview.get("last_name"))
        first_name = _blank(preview.get("first_name"))
        if not last_name and not first_name:
            last_name = _blank(preview.get("full_name"))
        fields.update(
            {
                "last_name": last_name,
                "first_name": first_name,
                "birth_date": _parse_date(preview.get("birth_date")),
                "birth_country": _blank(preview.get("birth_place")),
                "civility": _map_civility(preview.get("civility") or ""),
                "marital_status": _map_marital(
                    preview.get("marital_status") or ""
                ),
                "spouse_last_name": _blank(preview.get("spouse_name")),
                "national_id": _blank(preview.get("num_piece_identite")),
                "id_document_issue_date": _parse_date(
                    preview.get("id_document_issue_date")
                ),
                "id_document_expiry_date": _parse_date(
                    preview.get("id_document_expiry_date")
                ),
                "profession": _blank(preview.get("profession")),
                "nationality": _blank(preview.get("nationality")),
            }
        )
    else:
        fields.update(
            {
                "company_name": _blank(
                    preview.get("company_name") or preview.get("full_name")
                ),
                "ifu": _blank(preview.get("identification_nationale")),
                "rccm": _blank(preview.get("num_carte_operateur")),
                "address": _blank(preview.get("head_office"))
                or _blank(preview.get("address")),
            }
        )

    if kyc_status == Client.KycStatus.VALIDATED:
        fields["kyc_validated_at"] = timezone.localdate()

    return fields


@transaction.atomic
def import_client_from_cbs(*, tenant_id, user, data: dict) -> tuple[Client, dict]:
    """
    Rejoue l'appel CBS puis crée le client (données CBS non modifiables).

    ``client_type`` obligatoire : INDIVIDUAL | CORPORATE.
    """
    client_type = parse_client_type(data)
    preview = preview_client_from_cbs(tenant_id=tenant_id, data=data)
    issues = preview.get("missing_required") or collect_cbs_import_issues(
        preview, client_type
    )
    if issues:
        raise ValidationError(
            {
                "detail": format_cbs_import_block_message(issues),
                "missing_required": issues,
            }
        )
    code = preview.get("code_adherent") or ""
    if code and Client.objects.filter(cbs_client_id=code).exists():
        raise ValidationError(
            {
                "detail": (
                    f"Un client avec le matricule CBS « {code} » existe déjà "
                    "dans cette filiale."
                )
            }
        )

    kyc_alert = bool(preview.get("kyc_alert"))
    kyc_status = (
        Client.KycStatus.PENDING
        if kyc_alert
        else Client.KycStatus.VALIDATED
    )
    agency = _resolve_agency(
        tenant_id=tenant_id or get_current_tenant_id(),
        user=user,
        point_of_service=_blank(preview.get("id_point_service")),
    )
    fields = map_preview_to_client_fields(
        preview=preview,
        client_type=client_type,
        tenant_id=tenant_id,
        user=user,
        agency=agency,
        kyc_status=kyc_status,
    )
    from .compliance import client_configuration, cbs_reference_value, kyc_failures
    candidate = Client(**fields)
    configuration = client_configuration(candidate)
    for key in ("civility", "marital_status"):
        mapped = cbs_reference_value(configuration, key, preview.get(key) or "")
        if mapped is not None:
            fields[key] = mapped
            setattr(candidate, key, mapped)
        if fields.get(key) and fields[key] not in {entry["code"] for entry in configuration["references"][key] if entry["active"]}:
            fields[key] = ""
            setattr(candidate, key, "")
    if candidate.kyc_status == Client.KycStatus.VALIDATED and kyc_failures(candidate, configuration=configuration):
        fields["kyc_status"], fields["kyc_validated_at"] = Client.KycStatus.PENDING, None
        preview["kyc_alert"] = True
    client = Client.objects.create(**fields)
    return client, preview
