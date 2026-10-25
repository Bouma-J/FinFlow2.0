"""
Configuration Perfect API par défaut pour les connecteurs CBS.

Source unique des chemins, auth, mapping périodicité / objet de financement
et règles de mise en place documentés pour gateway-perfect.
"""
from __future__ import annotations

from copy import deepcopy

# ---------------------------------------------------------------------------
# Endpoints Perfect (relatifs à base_url)
# ---------------------------------------------------------------------------

PERFECT_ENDPOINTS = {
    "authentification": "gateway-perfect/authentification",
    "adh_situation": "gateway-perfect/adh/situation",
    "crd_simple": "gateway-perfect/crd/simple",
    "crd_situation": "gateway-perfect/crd/situation",
    "crd_impayes": "gateway-perfect/crd/impayes",
    # Référentiels Perfect (GET, Bearer) — { datas: [{ id, code, libelle }] }
    "ref_devise_list": "gateway-perfect/ref/devise-list",
    "ref_point_service_list": "gateway-perfect/ref/point-service-list",
    "ref_type_piece_identite_list": "gateway-perfect/ref/type-piece-identite-list",
    "ref_gestionnaire_list": "gateway-perfect/ref/gestionnaire-list",
    "ref_periodicite_list": "gateway-perfect/ref/periodicite-list",
    "ref_motif_decision_list": "gateway-perfect/ref/motif-decision-list",
    "ref_object_fin_list": "gateway-perfect/ref/object-fin-list",
    "ref_source_fin_list": "gateway-perfect/ref/source-fin-list",
    "ref_profession_list": "gateway-perfect/ref/profession-list",
}

DEFAULT_AUTH_SCOPE = "perfect"

DEFAULT_CONNECTOR_NAME = "CBS Perfect"

# Auth Perfect : POST form-urlencoded → accessToken
# username / password à renseigner filiale ; scope fixe.
PERFECT_AUTH_CONFIG = {
    "scope": DEFAULT_AUTH_SCOPE,
    # "username": "",
    # "password": "",
    # "access_token": "",  # optionnel : bypass /authentification
    # "token_url": "",     # optionnel : URL absolue d'auth
}

# Mapping codes Fin Flow → codes Perfect (idPeriodicite / idObjetFinancement)
PERIODICITY_CBS = {
    "DAILY": "JOURNALIER",
    "WEEKLY": "HEBDOMADAIRE",
    "BIMONTHLY": "BIMENSUEL",
    "MONTHLY": "MENSUEL",
    "QUARTERLY": "TRIMESTRIEL",
    "SEMIANNUAL": "SEMESTRIEL",
    "ANNUAL": "ANNUEL",
}

PURPOSE_CBS = {
    "WORKING_CAPITAL": "FONDS_ROULEMENT",
    "EQUIPMENT": "EQUIPEMENT",
    "STOCK": "STOCK",
    "REAL_ESTATE": "IMMOBILIER",
    "TREASURY": "TRESORERIE",
    "CONSUMPTION": "CONSOMMATION",
    "OTHER": "AUTRE",
}

# Défauts métier mise en place (surchargeables agence / produit / utilisateur)
DISBURSEMENT_DEFAULTS = {
    "idPointService": "PS01",
    "idGestionnaire": "GEST01",
    "idProduitRemb": "COMPTE-COURANT",
}


def perfect_mapping_rules(*, demo: bool = False) -> dict:
    """
    ``mapping_rules`` prêts pour Perfect.

    - prod / filiale : mode CBS, pas de simulation forcée
    - demo : force_simulate + mise en place LOCAL (aucun HTTP)
    """
    rules = {
        "provider": "perfect",
        "force_simulate": bool(demo),
        "verify_ssl": True,
        "endpoints": dict(PERFECT_ENDPOINTS),
        "disbursement": {
            "mode": "LOCAL" if demo else "CBS",
            "defaults": dict(DISBURSEMENT_DEFAULTS),
            "periodicity_map": dict(PERIODICITY_CBS),
            "purpose_map": dict(PURPOSE_CBS),
        },
        "simulate": {
            "loan_settled_default": True,
            "loan_outstanding_default": "0",
            "client_outstanding_default": "0",
        },
    }
    return rules


def perfect_auth_config() -> dict:
    return deepcopy(PERFECT_AUTH_CONFIG)


def perfect_connector_defaults(*, demo: bool = False, base_url: str = "") -> dict:
    """Champs à passer à ``CoreBankingConnector.objects.create`` / get_or_create."""
    resolved_url = base_url
    if not resolved_url and demo:
        resolved_url = "https://cbs.demo.local"
    return {
        "protocol": "REST",
        "base_url": resolved_url,
        "timeout_seconds": 30,
        "max_retries": 3,
        "is_active": True,
        "auth_config": perfect_auth_config(),
        "mapping_rules": perfect_mapping_rules(demo=demo),
        "certificate_reference": "",
    }


def _deep_merge_missing(target: dict, defaults: dict) -> bool:
    """Complète ``target`` avec les clés absentes de ``defaults`` (récursif)."""
    changed = False
    for key, value in defaults.items():
        if key not in target or target[key] in (None, "", {}, []):
            target[key] = deepcopy(value)
            changed = True
        elif isinstance(value, dict) and isinstance(target.get(key), dict):
            if _deep_merge_missing(target[key], value):
                changed = True
    return changed


def ensure_perfect_connector(tenant, *, demo: bool = False, name: str | None = None):
    """
    Garantit un connecteur REST Perfect pour la filiale (idempotent).

    - Crée ``CBS Perfect`` s'il n'existe aucun connecteur actif REST.
    - Sinon complète le connecteur actif (endpoints auth, maps, scope).
    """
    from apps.common.tenancy import tenant_context

    from .models import CoreBankingConnector

    connector_name = name or DEFAULT_CONNECTOR_NAME
    defaults = perfect_connector_defaults(demo=demo)

    with tenant_context(tenant.id):
        candidates = CoreBankingConnector.objects.filter(protocol=CoreBankingConnector.Protocol.REST)
        candidates = candidates.filter(name=name) if name else candidates.filter(is_active=True)
        existing = candidates.order_by("created_at").first()
        if existing is None:
            return CoreBankingConnector.objects.create(
                tenant=tenant,
                name=connector_name,
                **defaults,
            ), True

        changed_fields: list[str] = []
        rules = deepcopy(existing.mapping_rules or {})
        if _deep_merge_missing(rules, perfect_mapping_rules(demo=demo)):
            # Ne pas forcer force_simulate / mode si déjà définis explicitement.
            # _deep_merge_missing ne remplace que les absents.
            existing.mapping_rules = rules
            changed_fields.append("mapping_rules")

        auth = deepcopy(existing.auth_config or {})
        if _deep_merge_missing(auth, perfect_auth_config()):
            existing.auth_config = auth
            changed_fields.append("auth_config")

        if not (existing.base_url or "").strip() and defaults.get("base_url"):
            existing.base_url = defaults["base_url"]
            changed_fields.append("base_url")

        if changed_fields:
            existing.save(update_fields=[*changed_fields, "updated_at"])
        return existing, False
