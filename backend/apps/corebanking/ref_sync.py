"""Synchronisation des référentiels Perfect (GET ref/*) vers FinFlow."""
from __future__ import annotations

import logging
import re
from copy import deepcopy
from typing import Iterable

from django.db import transaction

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
from apps.credits.models import PurposeType
from apps.tenants.models import Agency

from .models import CoreBankingConnector
from .perfect_defaults import PERFECT_ENDPOINTS, PURPOSE_CBS
from .services import CoreBankingError, RestAdapter, resolve_active_connector

logger = logging.getLogger("finflow")

# Référentiels alimentés uniquement depuis Perfect (pas de CRUD manuel)
SYNC_SCOPES = (
    "currencies",
    "periodicities",
    "financing_objects",
    "service_points",
    "managers",
    "financing_sources",
    "decision_motifs",
    "professions",
)

# Vision code/id → code FinFlow LoanPeriodicity
_PERIODICITY_HINTS: dict[str, str] = {
    "D": "DAILY",
    "J": "DAILY",
    "DAILY": "DAILY",
    "JOURNALIER": "DAILY",
    "W": "WEEKLY",
    "H": "WEEKLY",
    "WEEKLY": "WEEKLY",
    "HEBDOMADAIRE": "WEEKLY",
    "BM": "BIMONTHLY",
    "BIMONTHLY": "BIMONTHLY",
    "BIMENSUEL": "BIMONTHLY",
    "M": "MONTHLY",
    "MONTHLY": "MONTHLY",
    "MENSUEL": "MONTHLY",
    "MENSUELLE": "MONTHLY",
    "T": "QUARTERLY",
    "QUARTERLY": "QUARTERLY",
    "TRIMESTRIEL": "QUARTERLY",
    "TRIMESTRIELLE": "QUARTERLY",
    "S": "SEMIANNUAL",
    "SEMIANNUAL": "SEMIANNUAL",
    "SEMESTRIEL": "SEMIANNUAL",
    "SEMESTRIELLE": "SEMIANNUAL",
    "Y": "ANNUAL",
    "A": "ANNUAL",
    "ANNUAL": "ANNUAL",
    "ANNUEL": "ANNUAL",
    "ANNUELLE": "ANNUAL",
}

_PERIODS_PER_YEAR: dict[str, int] = {
    "DAILY": 360,
    "WEEKLY": 52,
    "BIMONTHLY": 24,
    "MONTHLY": 12,
    "QUARTERLY": 4,
    "SEMIANNUAL": 2,
    "ANNUAL": 1,
}

# Vision devise.code → code ISO FinFlow (codeDevise Perfect = code Vision, pas l'id)
_CURRENCY_ISO_HINTS: dict[str, str] = {
    "FCFA": "XOF",
    "XOF": "XOF",
    "XAF": "XAF",
    "EUR": "EUR",
    "USD": "USD",
    "CDF": "CDF",
    "GNF": "GNF",
    "MAD": "MAD",
}

# Vision object-fin code → PurposeType FinFlow
_PURPOSE_HINTS: dict[str, str] = {
    "IMMO": PurposeType.REAL_ESTATE,
    "IMMOBILIER": PurposeType.REAL_ESTATE,
    "REAL_ESTATE": PurposeType.REAL_ESTATE,
    "CONSO": PurposeType.CONSUMPTION,
    "CONSOMMATION": PurposeType.CONSUMPTION,
    "CONSUMPTION": PurposeType.CONSUMPTION,
    "AUTO": PurposeType.EQUIPMENT,
    "EQUIPEMENT": PurposeType.EQUIPMENT,
    "EQUIPMENT": PurposeType.EQUIPMENT,
    "STOCK": PurposeType.STOCK,
    "TRESORERIE": PurposeType.TREASURY,
    "TREASURY": PurposeType.TREASURY,
    "FONDS_ROULEMENT": PurposeType.WORKING_CAPITAL,
    "WORKING_CAPITAL": PurposeType.WORKING_CAPITAL,
    "AUTRE": PurposeType.OTHER,
    "OTHER": PurposeType.OTHER,
}


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").strip().upper())


def _empty_bucket() -> dict:
    return {
        "fetched": 0,
        "created": 0,
        "updated": 0,
        "linked": 0,
        "unchanged": 0,
        "deactivated": 0,
        "unmatched": [],
        "error": None,
    }


def _deactivate_absent(model, seen_cbs_ids: set[str]) -> int:
    """Désactive les lignes locales absentes du payload CBS (source unique)."""
    from django.db.models import Q

    if not seen_cbs_ids:
        return 0
    qs = model.objects.filter(is_active=True).filter(
        Q(cbs_code="") | ~Q(cbs_code__in=seen_cbs_ids)
    )
    n = 0
    for row in qs.iterator():
        row.is_active = False
        row.save(update_fields=["is_active", "updated_at"])
        n += 1
    return n


def sync_cbs_referentials(
    tenant_id,
    *,
    connector: CoreBankingConnector | None = None,
    scopes: Iterable[str] | None = None,
) -> dict:
    """
    Importe les listes Perfect ``ref/*`` dans FinFlow (source unique).

    - devises → ``Currency`` (``cbs_code`` = id Vision)
    - périodicités → ``LoanPeriodicity``
    - objets de financement → ``FinancingObject`` + ``purpose_map`` connecteur
    - points de service → ``ServicePoint`` (+ rattache agences homonymes)
    - gestionnaires → ``CbsManager`` (association utilisateur = manuelle)
    - sources de financement → ``FinancingSource``
    - motifs de décision → ``DecisionMotif``
    - professions → ``CbsProfession``
    """
    connector = connector or resolve_active_connector(tenant_id)
    if connector is None:
        raise CoreBankingError("Aucun connecteur CBS actif pour cette filiale.")

    selected = {
        s.strip().lower()
        for s in (scopes or SYNC_SCOPES)
        if str(s).strip()
    }
    unknown = selected - set(SYNC_SCOPES)
    if unknown:
        raise CoreBankingError(
            f"Scopes de sync inconnus : {', '.join(sorted(unknown))}."
        )

    adapter = RestAdapter(connector)
    report: dict = {
        "connector_id": str(connector.id),
        "scopes": sorted(selected),
        "results": {},
    }

    with tenant_context(tenant_id):
        if "currencies" in selected:
            report["results"]["currencies"] = _sync_currencies(adapter)
        if "periodicities" in selected:
            report["results"]["periodicities"] = _sync_periodicities(adapter)
        if "financing_objects" in selected:
            report["results"]["financing_objects"] = _sync_financing_objects(
                adapter, connector
            )
        if "service_points" in selected:
            report["results"]["service_points"] = _sync_service_points(
                adapter, tenant_id
            )
        if "managers" in selected:
            report["results"]["managers"] = _sync_managers(adapter)
        if "financing_sources" in selected:
            report["results"]["financing_sources"] = _sync_simple_catalog(
                adapter,
                FinancingSource,
                "ref_source_fin_list",
            )
        if "decision_motifs" in selected:
            report["results"]["decision_motifs"] = _sync_simple_catalog(
                adapter,
                DecisionMotif,
                "ref_motif_decision_list",
            )
        if "professions" in selected:
            report["results"]["professions"] = _sync_simple_catalog(
                adapter,
                CbsProfession,
                "ref_profession_list",
            )

        # Fusionne les chemins ref/* manquants dans mapping_rules.endpoints
        _ensure_ref_endpoints(connector)

    return report


def _ensure_ref_endpoints(connector: CoreBankingConnector) -> None:
    rules = deepcopy(connector.mapping_rules or {})
    endpoints = dict(rules.get("endpoints") or {})
    changed = False
    for key, path in PERFECT_ENDPOINTS.items():
        if key.startswith("ref_") and endpoints.get(key) != path:
            endpoints[key] = path
            changed = True
    if not changed:
        return
    rules["endpoints"] = endpoints
    connector.mapping_rules = rules
    connector.save(update_fields=["mapping_rules", "updated_at"])


def _fetch(adapter: RestAdapter, endpoint_key: str) -> list[dict]:
    default = PERFECT_ENDPOINTS.get(endpoint_key, "")
    return adapter.fetch_ref_list(endpoint_key, default_path=default)


def _sync_currencies(adapter: RestAdapter) -> dict:
    """Importe les devises ; ``cbs_code`` = code Perfect (ex. FCFA) pour ``codeDevise``."""
    bucket = _empty_bucket()
    try:
        rows = _fetch(adapter, "ref_devise_list")
    except CoreBankingError as exc:
        bucket["error"] = str(exc)
        return bucket

    bucket["fetched"] = len(rows)
    seen: set[str] = set()
    with transaction.atomic():
        for row in rows:
            vision_id = str(row["id"]).strip()
            vision_code = _norm(row.get("code") or "") or _norm(vision_id)
            # Perfect crd/simple attend le code alphabétique (FCFA), pas l'id numérique
            cbs_code = vision_code
            ff_code = _CURRENCY_ISO_HINTS.get(vision_code, vision_code)
            label = (row.get("libelle") or vision_code).strip()
            seen.add(cbs_code)
            existing = (
                Currency.objects.filter(code__iexact=ff_code).first()
                or Currency.objects.filter(cbs_code=cbs_code).first()
                or Currency.objects.filter(cbs_code=vision_id).first()
                or Currency.objects.filter(code__iexact=vision_code).first()
            )
            if existing is None:
                Currency.objects.create(
                    code=ff_code[:32],
                    label=label[:255],
                    cbs_code=cbs_code[:64],
                    is_active=True,
                )
                bucket["created"] += 1
                continue
            changed = False
            if (existing.cbs_code or "").strip() != cbs_code:
                existing.cbs_code = cbs_code[:64]
                changed = True
            if label and existing.label != label:
                existing.label = label[:255]
                changed = True
            if not existing.is_active:
                existing.is_active = True
                changed = True
            if changed:
                existing.save(
                    update_fields=["cbs_code", "label", "is_active", "updated_at"]
                )
                bucket["updated"] += 1
            else:
                bucket["unchanged"] += 1
        bucket["deactivated"] = _deactivate_absent(Currency, seen)
    return bucket


def _resolve_periodicity_code(vision_code: str, vision_id: str) -> str:
    for key in (_norm(vision_code), _norm(vision_id)):
        if key in _PERIODICITY_HINTS:
            return _PERIODICITY_HINTS[key]
    # Conserve un code stable dérivé du code Vision
    raw = _norm(vision_code) or _norm(vision_id) or "PERIOD"
    return raw[:32]


def _sync_periodicities(adapter: RestAdapter) -> dict:
    bucket = _empty_bucket()
    try:
        rows = _fetch(adapter, "ref_periodicite_list")
    except CoreBankingError as exc:
        bucket["error"] = str(exc)
        return bucket

    bucket["fetched"] = len(rows)
    seen: set[str] = set()
    with transaction.atomic():
        for idx, row in enumerate(rows):
            vision_id = str(row["id"]).strip()
            vision_code = str(row.get("code") or "").strip()
            label = (row.get("libelle") or vision_code or vision_id).strip()
            ff_code = _resolve_periodicity_code(vision_code, vision_id)
            periods = _PERIODS_PER_YEAR.get(ff_code, 12)
            seen.add(vision_id)

            existing = (
                LoanPeriodicity.objects.filter(code=ff_code).first()
                or LoanPeriodicity.objects.filter(cbs_code=vision_id).first()
                or LoanPeriodicity.objects.filter(code__iexact=vision_code).first()
            )
            if existing is None:
                LoanPeriodicity.objects.create(
                    code=ff_code[:32],
                    label=label[:255],
                    cbs_code=vision_id[:64],
                    periods_per_year=periods,
                    sort_order=(idx + 1) * 10,
                    is_active=True,
                )
                bucket["created"] += 1
                continue
            changed = False
            if (existing.cbs_code or "").strip() != vision_id:
                existing.cbs_code = vision_id[:64]
                changed = True
            if label and existing.label != label:
                existing.label = label[:255]
                changed = True
            if not existing.is_active:
                existing.is_active = True
                changed = True
            if changed:
                existing.save(
                    update_fields=[
                        "cbs_code",
                        "label",
                        "is_active",
                        "updated_at",
                    ]
                )
                bucket["updated"] += 1
            else:
                bucket["unchanged"] += 1
        bucket["deactivated"] = _deactivate_absent(LoanPeriodicity, seen)
    return bucket


def _guess_purpose_type(vision_code: str) -> str:
    return _PURPOSE_HINTS.get(_norm(vision_code), "")


def _sync_financing_objects(
    adapter: RestAdapter, connector: CoreBankingConnector
) -> dict:
    bucket = _empty_bucket()
    try:
        rows = _fetch(adapter, "ref_object_fin_list")
    except CoreBankingError as exc:
        bucket["error"] = str(exc)
        return bucket

    bucket["fetched"] = len(rows)
    purpose_updates: dict[str, str] = {}
    seen: set[str] = set()

    with transaction.atomic():
        for idx, row in enumerate(rows):
            vision_id = str(row["id"]).strip()
            code = _norm(row.get("code") or "") or _norm(vision_id)
            label = (row.get("libelle") or code).strip()
            purpose = _guess_purpose_type(code)
            seen.add(vision_id)
            existing = (
                FinancingObject.objects.filter(code=code).first()
                or FinancingObject.objects.filter(cbs_code=vision_id).first()
            )
            if existing is None:
                FinancingObject.objects.create(
                    code=code[:32],
                    label=label[:255],
                    cbs_code=vision_id[:64],
                    purpose_type=purpose,
                    sort_order=(idx + 1) * 10,
                    is_active=True,
                )
                bucket["created"] += 1
            else:
                changed = False
                if (existing.cbs_code or "").strip() != vision_id:
                    existing.cbs_code = vision_id[:64]
                    changed = True
                if label and existing.label != label:
                    existing.label = label[:255]
                    changed = True
                if purpose and not (existing.purpose_type or "").strip():
                    existing.purpose_type = purpose
                    changed = True
                if not existing.is_active:
                    existing.is_active = True
                    changed = True
                if changed:
                    existing.save(
                        update_fields=[
                            "cbs_code",
                            "label",
                            "purpose_type",
                            "is_active",
                            "updated_at",
                        ]
                    )
                    bucket["updated"] += 1
                else:
                    bucket["unchanged"] += 1
                purpose = purpose or (existing.purpose_type or "").strip()

            if purpose:
                purpose_updates[purpose] = vision_id

        if purpose_updates:
            _merge_purpose_map(connector, purpose_updates)
            bucket["linked"] = len(purpose_updates)
        bucket["deactivated"] = _deactivate_absent(FinancingObject, seen)

    return bucket


def _merge_purpose_map(
    connector: CoreBankingConnector, updates: dict[str, str]
) -> None:
    rules = deepcopy(connector.mapping_rules or {})
    disb = dict(rules.get("disbursement") or {})
    purpose_map = {
        **PURPOSE_CBS,
        **dict(disb.get("purpose_map") or {}),
        **updates,
    }
    disb["purpose_map"] = purpose_map
    rules["disbursement"] = disb
    connector.mapping_rules = rules
    connector.save(update_fields=["mapping_rules", "updated_at"])


def _upsert_mapped_row(
    model,
    *,
    vision_id: str,
    code: str,
    label: str,
    sort_order: int,
    extra: dict | None = None,
) -> str:
    """Retourne ``created`` | ``updated`` | ``unchanged``."""
    extra = extra or {}
    existing = (
        model.objects.filter(cbs_code=vision_id).first()
        or model.objects.filter(code=code).first()
    )
    if existing is None:
        model.objects.create(
            code=code[:32],
            label=(label or code)[:255],
            cbs_code=vision_id[:64],
            sort_order=sort_order,
            is_active=True,
            **extra,
        )
        return "created"

    changed = False
    if (existing.cbs_code or "").strip() != vision_id:
        existing.cbs_code = vision_id[:64]
        changed = True
    if label and existing.label != label:
        existing.label = label[:255]
        changed = True
    if not existing.is_active:
        existing.is_active = True
        changed = True
    for field, value in extra.items():
        if value and not (getattr(existing, field, None) or "").strip():
            setattr(existing, field, value)
            changed = True
    if changed:
        fields = ["cbs_code", "label", "is_active", "updated_at", *extra.keys()]
        existing.save(update_fields=list(dict.fromkeys(fields)))
        return "updated"
    return "unchanged"


def _sync_service_points(adapter: RestAdapter, tenant_id) -> dict:
    """Importe les points de service CBS ; rattache les agences homonymes si possible."""
    bucket = _empty_bucket()
    try:
        rows = _fetch(adapter, "ref_point_service_list")
    except CoreBankingError as exc:
        bucket["error"] = str(exc)
        return bucket

    bucket["fetched"] = len(rows)
    agencies = list(Agency.objects.filter(tenant_id=tenant_id))
    by_code = {_norm(a.code): a for a in agencies if a.code}
    by_cbs = {
        _norm(a.cbs_point_of_service_id): a
        for a in agencies
        if (a.cbs_point_of_service_id or "").strip()
    }
    seen: set[str] = set()

    with transaction.atomic():
        for idx, row in enumerate(rows):
            vision_id = str(row["id"]).strip()
            code = _norm(row.get("code") or "") or _norm(vision_id)
            label = (row.get("libelle") or code).strip()
            seen.add(vision_id)
            status = _upsert_mapped_row(
                ServicePoint,
                vision_id=vision_id,
                code=code,
                label=label,
                sort_order=(idx + 1) * 10,
            )
            bucket[status] += 1

            # Rattachement optionnel agence déjà créée (même code / déjà lié)
            agency = by_cbs.get(_norm(vision_id)) or by_code.get(code)
            if agency is None and label:
                for candidate in agencies:
                    if _norm(candidate.name) == _norm(label):
                        agency = candidate
                        break
            if agency is None:
                continue
            if (agency.cbs_point_of_service_id or "").strip() == vision_id:
                continue
            agency.cbs_point_of_service_id = vision_id[:64]
            agency.save(update_fields=["cbs_point_of_service_id", "updated_at"])
            bucket["linked"] += 1
        bucket["deactivated"] = _deactivate_absent(ServicePoint, seen)
    return bucket


def _sync_managers(adapter: RestAdapter) -> dict:
    """Importe les gestionnaires CBS (association utilisateur = manuelle)."""
    return _sync_simple_catalog(adapter, CbsManager, "ref_gestionnaire_list")


def _sync_simple_catalog(
    adapter: RestAdapter, model, endpoint_key: str
) -> dict:
    """Upsert générique ``{id, code, libelle}`` → modèle ``CbsMappedReference``."""
    bucket = _empty_bucket()
    try:
        rows = _fetch(adapter, endpoint_key)
    except CoreBankingError as exc:
        bucket["error"] = str(exc)
        return bucket

    bucket["fetched"] = len(rows)
    seen: set[str] = set()
    with transaction.atomic():
        for idx, row in enumerate(rows):
            vision_id = str(row["id"]).strip()
            code = _norm(row.get("code") or "") or _norm(vision_id)
            label = (row.get("libelle") or code).strip()
            seen.add(vision_id)
            status = _upsert_mapped_row(
                model,
                vision_id=vision_id,
                code=code,
                label=label,
                sort_order=(idx + 1) * 10,
            )
            bucket[status] += 1
        bucket["deactivated"] = _deactivate_absent(model, seen)
    return bucket