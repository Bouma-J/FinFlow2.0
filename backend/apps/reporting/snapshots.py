"""Matérialisation et lecture des snapshots de reporting."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.utils import timezone

from .models import ReportingSnapshot
from .services import build_dashboard, build_group_breakdown


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def params_hash(params) -> str:
    if not params:
        return ""
    if hasattr(params, "items"):
        items = sorted((k, str(v)) for k, v in dict(params).items() if v not in (None, ""))
    else:
        items = sorted((k, str(v)) for k, v in params.items() if v not in (None, ""))
    if not items:
        return ""
    raw = json.dumps(items, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def snapshot_max_age_seconds() -> int:
    return int(getattr(settings, "REPORTING_SNAPSHOT_MAX_AGE_SECONDS", 3600))


def get_fresh_snapshot(*, scope: str, tenant_id, kind: str, params) -> dict | None:
    """Retourne le payload si le snapshot est encore frais, sinon None."""
    ph = params_hash(params)
    qs = ReportingSnapshot.objects.filter(scope=scope, kind=kind, params_hash=ph)
    if scope == ReportingSnapshot.Scope.TENANT:
        qs = qs.filter(tenant_id=tenant_id)
    else:
        qs = qs.filter(tenant__isnull=True)
    snap = qs.first()
    if snap is None:
        return None
    age = (timezone.now() - snap.computed_at).total_seconds()
    if age > snapshot_max_age_seconds():
        return None
    data = dict(snap.payload)
    data["_snapshot"] = {
        "computed_at": snap.computed_at.isoformat(),
        "age_seconds": int(age),
        "kind": kind,
    }
    return data


def upsert_snapshot(*, scope: str, tenant_id, kind: str, params, payload: dict):
    ph = params_hash(params)
    defaults = {"payload": _json_safe(payload)}
    if scope == ReportingSnapshot.Scope.TENANT:
        obj, _ = ReportingSnapshot.objects.update_or_create(
            scope=scope,
            tenant_id=tenant_id,
            kind=kind,
            params_hash=ph,
            defaults=defaults,
        )
    else:
        obj, _ = ReportingSnapshot.objects.update_or_create(
            scope=scope,
            tenant=None,
            kind=kind,
            params_hash=ph,
            defaults=defaults,
        )
    return obj


def refresh_all_snapshots():
    """Recalcule les snapshots « sans filtre » pour chaque filiale + Groupe."""
    from apps.tenants.models import Tenant

    empty = {}
    count = 0
    for tenant in Tenant.objects.filter(is_active=True).iterator():
        payload = build_dashboard(tenant_id=tenant.id, params=empty)
        upsert_snapshot(
            scope=ReportingSnapshot.Scope.TENANT,
            tenant_id=tenant.id,
            kind="dashboard",
            params=empty,
            payload=payload,
        )
        count += 1

    group_payload = build_dashboard(tenant_id=None, params=empty)
    upsert_snapshot(
        scope=ReportingSnapshot.Scope.GROUP,
        tenant_id=None,
        kind="dashboard",
        params=empty,
        payload=group_payload,
    )
    count += 1

    for dimension in ("tenant", "country", "zone", "status", "product"):
        rows = build_group_breakdown(empty, dimension=dimension)
        upsert_snapshot(
            scope=ReportingSnapshot.Scope.GROUP,
            tenant_id=None,
            kind=f"breakdown:{dimension}",
            params=empty,
            payload={"dimension": dimension, "rows": rows},
        )
        count += 1
    return count
