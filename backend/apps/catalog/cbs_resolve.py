"""Résolution des codes CBS depuis les référentiels catalogue."""
from __future__ import annotations


def _lookup(model, tenant_id, code: str):
    if not tenant_id or not code:
        return None
    return (
        model.all_tenants.filter(
            tenant_id=tenant_id, code=str(code).strip(), is_active=True
        )
        .order_by("sort_order", "label")
        .first()
    )


def resolve_ref(model, tenant_id, code: str) -> dict:
    """Retourne ``{code, label, cbs_code, periods_per_year?}`` ou dict vide."""
    row = _lookup(model, tenant_id, code)
    if row is None:
        return {}
    data = {
        "code": row.code,
        "label": row.label,
        "cbs_code": (row.cbs_code or "").strip(),
    }
    if hasattr(row, "periods_per_year"):
        data["periods_per_year"] = row.periods_per_year
    return data


def resolve_periodicity_cbs(
    tenant_id, code: str, *, fallback_map: dict | None = None
) -> str:
    from .models import LoanPeriodicity

    row = _lookup(LoanPeriodicity, tenant_id, code)
    if row and (row.cbs_code or "").strip():
        return row.cbs_code.strip()
    if fallback_map and code in fallback_map:
        return fallback_map[code]
    return str(code or "").strip()


def resolve_periodicity_periods_per_year(
    tenant_id, code: str, default: int = 12
) -> int:
    from .models import LoanPeriodicity

    row = _lookup(LoanPeriodicity, tenant_id, code)
    if row and row.periods_per_year:
        return int(row.periods_per_year)
    return int(default)


def resolve_repayment_cbs(tenant_id, code: str) -> str:
    from .models import RepaymentMethod

    row = _lookup(RepaymentMethod, tenant_id, code)
    if row and (row.cbs_code or "").strip():
        return row.cbs_code.strip()
    return ""


def resolve_currency_cbs(tenant_id, code: str, *, fallback: str = "XOF") -> str:
    from .models import Currency

    row = _lookup(Currency, tenant_id, code)
    if row:
        return (row.cbs_code or row.code or fallback).strip().upper()
    return str(code or fallback).strip().upper()


def resolve_financing_object_cbs(
    tenant_id,
    purpose_type: str,
    *,
    purpose_map: dict | None = None,
    default: str = "",
) -> str:
    """Résout ``idObjetFinancement`` : catalogue CBS d'abord, puis purpose_map syncé."""
    from .models import FinancingObject

    pt = str(purpose_type or "").strip()
    if tenant_id and pt:
        row = (
            FinancingObject.all_tenants.filter(
                tenant_id=tenant_id,
                purpose_type=pt,
                is_active=True,
            )
            .exclude(cbs_code="")
            .order_by("sort_order", "label")
            .first()
        )
        if row is None:
            row = (
                FinancingObject.all_tenants.filter(
                    tenant_id=tenant_id,
                    code__iexact=pt,
                    is_active=True,
                )
                .exclude(cbs_code="")
                .order_by("sort_order", "label")
                .first()
            )
        if row is not None:
            return (row.cbs_code or "").strip()

    mapped = str((purpose_map or {}).get(pt) or "").strip()
    if mapped and mapped != pt:
        # Accepte un id Vision déjà syncé dans purpose_map, ignore les libellés legacy
        # du type CONSOMMATION si un catalogue actif existe pour ce purpose.
        if tenant_id:
            if FinancingObject.all_tenants.filter(
                tenant_id=tenant_id, cbs_code=mapped, is_active=True
            ).exists():
                return mapped
            has_catalog = FinancingObject.all_tenants.filter(
                tenant_id=tenant_id, is_active=True
            ).exclude(cbs_code="").exists()
            if has_catalog and not mapped.isdigit():
                mapped = ""
        if mapped:
            return mapped

    default_val = str(default or "").strip()
    if default_val:
        return default_val

    # Dernier recours hors catalogue CBS : map Perfect historique (démo / seeds)
    if tenant_id:
        has_catalog = FinancingObject.all_tenants.filter(
            tenant_id=tenant_id, is_active=True
        ).exclude(cbs_code="").exists()
        if has_catalog:
            return ""
    from apps.corebanking.perfect_defaults import PURPOSE_CBS

    return str(PURPOSE_CBS.get(pt) or "").strip()


def active_codes(model, tenant_id) -> set[str]:
    if not tenant_id:
        return set()
    return set(
        model.all_tenants.filter(tenant_id=tenant_id, is_active=True).values_list(
            "code", flat=True
        )
    )


def application_cbs_refs(application) -> dict:
    from .cbs_mapping import resolve_application_cbs

    return resolve_application_cbs(application)


def is_demo_product_code(value):
    from .cbs_mapping import is_demo_product_code as check

    return check(value)
