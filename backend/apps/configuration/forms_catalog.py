"""Schémas déclaratifs bornés : aucune expression ou code utilisateur."""
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import models

ANALYSIS_SECTIONS = {
    "fa-params": "Paramètres", "fa-quality": "Fiabilité des données", "fa-business": "Reconstitution activité",
    "fa-exploitation": "Activité et résultat", "fa-balance": "Bilan", "fa-trend": "Historique et tendance",
    "fa-income": "Revenus du ménage", "fa-activity": "Activité génératrice de revenus",
    "fa-charges": "Charges et patrimoine", "fa-stability": "Stabilité salariale", "fa-group": "Groupement",
    "fa-debt": "Endettement", "fa-treasury": "Capacité et trésorerie", "fa-collateral": "Garanties",
    "fa-sector": "Analyse sectorielle", "fa-es": "Environnement et social", "fa-conclusion": "Conclusion",
}
OPTIONAL_SECTIONS = {"fa-sector", "fa-es"}
SECTOR_FIELDS = {"sector", "sub_sector", "value_chain_position", "market_dynamic", "seasonality_level", "competition_intensity", "supplier_dependency", "client_concentration", "input_price_sensitivity", "fx_exposure", "regulatory_sensitivity", "climate_sensitivity", "sector_risk_level", "sector_outlook", "sector_comment"}
ES_FIELDS = {"es_category", "permit_reference", "waste_management", "resource_use", "chemicals_pesticides", "nuisances_emissions", "working_conditions", "occupational_safety", "child_forced_labor_risk", "community_impact", "land_resettlement_risk", "es_mitigation_plan", "es_risk_level", "es_comment", "exclusion_list_ok", "env_permit_required", "env_permit_obtained", "eia_required", "eia_done", "es_regulatory_compliance", "es_action_required", "es_insurance", "jobs_created", "jobs_maintained", "jobs_women", "jobs_youth", "workforce_count"}
REFERENCE_FIELDS = {"civility": 10, "marital_status": 15, "id_document_type": 20, "legal_form": 20}


def native_kyc_fields():
    from apps.clients.models import Client
    excluded = {"reference", "client_type", "kyc_status", "cbs_client_id", "cbs_account_number"}
    return {field.name: str(field.verbose_name) for field in Client._meta.fields
            if isinstance(field, (models.CharField, models.TextField, models.DateField))
            and field.name not in excluded and not field.name.startswith(("cbs_", "kyc_"))}


def document_fields():
    from apps.clients.models import Client
    return {field.name: str(field.verbose_name) for field in Client._meta.fields if isinstance(field, models.FileField)}


def form_defaults():
    from apps.clients.models import Civility, IdDocumentType, LegalForm, MaritalStatus
    choices = {"civility": Civility.choices, "marital_status": MaritalStatus.choices,
               "id_document_type": IdDocumentType.choices, "legal_form": LegalForm.choices}
    return {"forms": {"client_fields": [], "analysis_fields": [], "analysis_sections": []},
            "kyc": {"required_fields": [], "required_documents": [], "check_expiry": False, "validity_days": 0},
            "references": {key: [{"code": code, "label": str(label), "active": True, "cbs_code": ""}
                                  for code, label in values] for key, values in choices.items()}}


def protect_required_sections(configuration):
    required = set(configuration["analysis"]["required_fields"])
    protected = [key for key, fields in (("fa-sector", SECTOR_FIELDS), ("fa-es", ES_FIELDS)) if required.intersection(fields)]
    configuration["protected_analysis_sections"] = protected
    for section in configuration["forms"]["analysis_sections"]:
        if section["id"] in protected:
            section["visible"] = True


def _definitions(value):
    if not isinstance(value, list) or len(value) > 50:
        raise ValidationError("Un formulaire accepte au plus 50 champs additionnels.")
    result, ids = [], set()
    for field in value:
        if not isinstance(field, dict) or set(field) - {"id", "label", "type", "required", "choices"}:
            raise ValidationError("Définition de champ additionnel invalide.")
        code, label, kind = field.get("id"), field.get("label"), field.get("type")
        if not isinstance(code, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", code) or code in ids:
            raise ValidationError("Identifiant de champ invalide ou répété (40 caractères, minuscules et chiffres).")
        if not isinstance(label, str) or not label.strip() or len(label) > 150:
            raise ValidationError("Le libellé du champ est requis (150 caractères maximum).")
        if kind not in {"text", "number", "boolean", "date", "choice"} or type(field.get("required", False)) is not bool:
            raise ValidationError("Type de champ ou caractère obligatoire invalide.")
        choices = field.get("choices", [])
        if not isinstance(choices, list) or len(choices) > 100 or any(not isinstance(item, str) or not item.strip() or len(item) > 100 for item in choices):
            raise ValidationError("Liste de choix invalide (100 valeurs maximum).")
        if kind == "choice" and not choices or kind != "choice" and choices:
            raise ValidationError("Les choix sont réservés aux champs de type choix et doivent être renseignés.")
        if len(set(choices)) != len(choices):
            raise ValidationError("Un choix ne peut pas être répété.")
        ids.add(code)
        result.append({"id": code, "label": label.strip(), "type": kind, "required": field.get("required", False), "choices": choices})
    return result


def validate_forms(value):
    if not isinstance(value, dict) or set(value) - {"client_fields", "analysis_fields", "analysis_sections"}:
        raise ValidationError("Rubrique formulaires invalide.")
    result = {key: _definitions(value[key]) for key in ("client_fields", "analysis_fields") if key in value}
    if "analysis_sections" in value:
        sections, ids = value["analysis_sections"], set()
        if not isinstance(sections, list) or len(sections) > len(ANALYSIS_SECTIONS):
            raise ValidationError("Ordre des sections invalide.")
        for section in sections:
            if not isinstance(section, dict) or set(section) != {"id", "visible"} or section["id"] not in ANALYSIS_SECTIONS or type(section["visible"]) is not bool or section["id"] in ids:
                raise ValidationError("Section inconnue, répétée ou visibilité invalide.")
            if not section["visible"] and section["id"] not in OPTIONAL_SECTIONS:
                raise ValidationError("Les paramètres, la conclusion et les sections financières ne peuvent pas être masqués.")
            ids.add(section["id"])
        result["analysis_sections"] = sections
    return result


def validate_kyc(value):
    defaults = form_defaults()["kyc"]
    if not isinstance(value, dict) or set(value) - set(defaults):
        raise ValidationError("Exigence KYC inconnue.")
    for key, fields in (("required_fields", native_kyc_fields()), ("required_documents", document_fields())):
        if key in value and (not isinstance(value[key], list) or any(not isinstance(item, str) or item not in fields for item in value[key])):
            raise ValidationError(f"Liste {key} invalide.")
    if "check_expiry" in value and type(value["check_expiry"]) is not bool:
        raise ValidationError("Le contrôle d'expiration attend un booléen.")
    if "validity_days" in value and (type(value["validity_days"]) is not int or not 0 <= value["validity_days"] <= 36500):
        raise ValidationError("La durée KYC doit être comprise entre 0 et 36500 jours.")
    return value


def validate_references(value):
    if not isinstance(value, dict) or set(value) - set(REFERENCE_FIELDS):
        raise ValidationError("Référentiel client inconnu.")
    result = {}
    for key, entries in value.items():
        if not isinstance(entries, list) or not 1 <= len(entries) <= 200:
            raise ValidationError("Chaque référentiel contient de 1 à 200 valeurs.")
        codes, mappings, result[key] = set(), set(), []
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"code", "label", "active", "cbs_code"}:
                raise ValidationError("Entrée de référentiel invalide.")
            code, label, mapping = entry["code"], entry["label"], entry["cbs_code"]
            if not isinstance(code, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0," + str(REFERENCE_FIELDS[key] - 1) + r"}", code) or code in codes:
                raise ValidationError("Code de référence invalide ou répété.")
            if not isinstance(label, str) or not label.strip() or len(label) > 150 or type(entry["active"]) is not bool:
                raise ValidationError("Libellé ou état de référence invalide.")
            if not isinstance(mapping, str) or len(mapping) > 100 or mapping and mapping in mappings:
                raise ValidationError("Correspondance CBS invalide ou ambiguë.")
            codes.add(code)
            if mapping:
                mappings.add(mapping)
            result[key].append({**entry, "label": label.strip()})
    return result


def validate_custom_values(definitions, values, previous=None, require=False):
    previous = previous or {}
    if not isinstance(values, dict) or len(values) > 200:
        raise ValidationError("Les données additionnelles doivent être un objet de taille limitée.")
    known = {field["id"]: field for field in definitions}
    result = dict(previous)
    for key, value in values.items():
        if key not in known:
            if key not in previous or value != previous[key]:
                raise ValidationError(f"Champ additionnel inconnu ou retiré : {key}.")
            continue
        field = known[key]
        if value is None or value == "":
            result[key] = None
            continue
        kind = field["type"]
        if kind == "boolean":
            valid = type(value) is bool
        elif kind == "number":
            try:
                number = Decimal(str(value))
                valid = not isinstance(value, bool) and number.is_finite() and abs(number) < Decimal("1e18") and max(0, -number.as_tuple().exponent) <= 6
            except (InvalidOperation, ValueError, TypeError):
                valid = False
            if valid:
                value = str(number)
        elif kind == "date":
            try:
                valid = isinstance(value, str) and date.fromisoformat(value).isoformat() == value
            except (ValueError, TypeError):
                valid = False
        elif kind == "choice":
            valid = isinstance(value, str) and value in field["choices"]
        else:
            valid = isinstance(value, str) and len(value) <= 4000
        if not valid:
            raise ValidationError(f"Valeur invalide pour {field['label']} ({kind}).")
        result[key] = value
    if require:
        missing = [field["label"] for field in definitions if field["required"] and
                   (result.get(field["id"]) is None or isinstance(result.get(field["id"]), str) and not result[field["id"]].strip())]
        if missing:
            raise ValidationError("Champs additionnels requis : " + ", ".join(missing))
    return result
