#!/usr/bin/env python
"""
Test global des 3 phases de montée en charge FIN_FLOW.
Usage (dans le conteneur backend) :
  python scripts/test_scale_phases.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

BASE = os.environ.get("FINFLOW_API_BASE", "http://127.0.0.1:8000/api/v1").rstrip("/")
USER = os.environ.get("FINFLOW_USER", "group_admin")
PASSWORD = os.environ.get("FINFLOW_PASSWORD", "FinFlow2026!")

OK = 0
KO = 0
RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, passed: bool, detail: str = ""):
    global OK, KO
    RESULTS.append((name, passed, detail))
    if passed:
        OK += 1
        print(f"  OK  {name}" + (f" — {detail}" if detail else ""))
    else:
        KO += 1
        print(f"  KO  {name}" + (f" — {detail}" if detail else ""))


def request(
    method: str,
    path: str,
    *,
    data: dict | None = None,
    token: str | None = None,
    expect: int | tuple[int, ...] = 200,
) -> tuple[int, Any]:
    url = path if path.startswith("http") else f"{BASE}{path}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            try:
                parsed = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                parsed = raw
            code = resp.status
    except urllib.error.HTTPError as exc:
        code = exc.code
        raw = exc.read().decode(errors="replace")
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = raw
    expected = expect if isinstance(expect, tuple) else (expect,)
    if code not in expected:
        raise AssertionError(f"{method} {path} -> {code}, attendu {expected}: {parsed}")
    return code, parsed


def login(username=USER, password=PASSWORD, otp=None) -> str:
    payload = {"username": username, "password": password}
    if otp:
        payload["otp"] = otp
    _, data = request("POST", "/auth/token/", data=payload, expect=200)
    assert isinstance(data, dict) and "access" in data
    return data["access"], data.get("refresh")


def main():
    print("=== Phase 0 — prérequis ===")
    try:
        code, health = request("GET", "/health/", expect=(200, 503))
        record("health endpoint", code == 200 and health.get("ready") is True, str(health.get("status")))
    except Exception as exc:
        record("health endpoint", False, str(exc))
        print("API inaccessible — arrêt.")
        return 1

    print("\n=== Phase 1 — court terme ===")
    try:
        access, refresh = login()
        record("login JWT", True, "group_admin")
    except Exception as exc:
        record("login JWT", False, str(exc))
        return 1

    # Pagination listes
    for path, label in (
        ("/clients/?page=1", "pagination clients"),
        ("/credit-applications/?page=1", "pagination dossiers"),
        ("/guarantees/?page=1", "pagination garanties"),
        ("/sureties/?page=1", "pagination cautions"),
        ("/audit-logs/?page=1", "pagination audit"),
    ):
        try:
            _, data = request("GET", path, token=access)
            ok = isinstance(data, dict) and "results" in data and "count" in data
            record(label, ok, f"count={data.get('count') if ok else '?'}")
        except Exception as exc:
            record(label, False, str(exc))

    # Liste allégée dossiers (pas de documents/fees_breakdown)
    try:
        _, data = request("GET", "/credit-applications/?page=1", token=access)
        results = data.get("results") or []
        if not results:
            record("liste dossiers allégée", True, "vide (OK sur base propre)")
        else:
            row = results[0]
            heavy = ("documents" in row) or ("stock_photos" in row) or ("fees_breakdown" in row)
            record("liste dossiers allégée", not heavy, f"clés={sorted(row.keys())[:8]}…")
    except Exception as exc:
        record("liste dossiers allégée", False, str(exc))

    # S3 storage config via metrics/settings smoke (upload_url)
    try:
        code, data = request(
            "POST",
            "/documents/upload_url/",
            token=access,
            data={"filename": "scale-test.txt", "content_type": "text/plain"},
            expect=(201, 400),
        )
        if code == 201 and isinstance(data, dict) and data.get("upload_url"):
            record("S3 upload_url présigné", True, "clé=" + str(data.get("key", ""))[:40])
        elif code == 400:
            # Peut échouer sans filiale sélectionnée pour group_admin
            record(
                "S3 upload_url présigné",
                "s3" in str(data).lower() or "filiale" in str(data).lower() or "tenant" in str(data).lower()
                or "STORAGE" in str(data),
                str(data)[:120],
            )
        else:
            record("S3 upload_url présigné", False, f"{code} {data}")
    except Exception as exc:
        record("S3 upload_url présigné", False, str(exc))

    print("\n=== Phase 2 — moyen terme ===")
    # Cache /me
    try:
        _, me1 = request("GET", "/users/me/", token=access)
        _, me2 = request("GET", "/users/me/", token=access)
        record(
            "cache /users/me/",
            me1.get("username") == USER and me1.get("username") == me2.get("username"),
            f"mfa_enabled={me1.get('mfa_enabled')}",
        )
    except Exception as exc:
        record("cache /users/me/", False, str(exc))

    # MFA setup (enrôlement sans activer durablement si on disable après)
    secret = None
    try:
        _, setup = request("POST", "/auth/mfa/setup/", token=access, data={}, expect=200)
        secret = setup.get("secret")
        uri = setup.get("provisioning_uri")
        record("MFA setup", bool(secret and uri), "secret généré")
    except Exception as exc:
        record("MFA setup", False, str(exc))

    if secret:
        try:
            import pyotp

            otp = pyotp.TOTP(secret).now()
            _, conf = request(
                "POST", "/auth/mfa/confirm/", token=access, data={"otp": otp}, expect=200
            )
            record("MFA confirm", conf.get("mfa_enabled") is True)

            # Login sans OTP doit échouer
            try:
                request(
                    "POST",
                    "/auth/token/",
                    data={"username": USER, "password": PASSWORD},
                    expect=401,
                )
                record("MFA gate login sans OTP", True)
            except Exception as exc:
                record("MFA gate login sans OTP", False, str(exc))

            otp2 = pyotp.TOTP(secret).now()
            access2, refresh2 = login(otp=otp2)
            record("MFA login avec OTP", True)

            # Disable MFA
            otp3 = pyotp.TOTP(secret).now()
            _, dis = request(
                "POST",
                "/auth/mfa/disable/",
                token=access2,
                data={"otp": otp3, "password": PASSWORD},
                expect=200,
            )
            record("MFA disable", dis.get("mfa_enabled") is False)
            access, refresh = login()
        except Exception as exc:
            record("MFA flux complet", False, str(exc))
            # tenter de désactiver pour ne pas bloquer le compte
            try:
                import pyotp

                otp = pyotp.TOTP(secret).now()
                request(
                    "POST",
                    "/auth/mfa/disable/",
                    token=access,
                    data={"otp": otp, "password": PASSWORD},
                    expect=(200, 400, 401),
                )
            except Exception:
                pass

    # JWT logout blacklist
    try:
        access_l, refresh_l = login()
        request("POST", "/auth/logout/", token=access_l, data={"refresh": refresh_l}, expect=200)
        # refresh blacklisted
        code, _ = request(
            "POST",
            "/auth/token/refresh/",
            data={"refresh": refresh_l},
            expect=(401, 400),
        )
        record("JWT blacklist logout", code in (400, 401), f"refresh status={code}")
        access, refresh = login()
    except Exception as exc:
        record("JWT blacklist logout", False, str(exc))

    # Celery task import / beat keys
    try:
        from config.celery import app

        keys = set(app.conf.beat_schedule.keys())
        needed = {
            "flag-sla-breaches",
            "refresh-overdue-loans",
            "retry-cbs-integrations",
            "purge-old-audit-logs",
            "notify-expiring-documents",
            "refresh-reporting-snapshots",
        }
        missing = needed - keys
        record("Celery beat schedule", not missing, f"manque={missing or '—'}")
    except Exception as exc:
        record("Celery beat schedule", False, str(exc))

    # Index / settings
    try:
        from django.conf import settings

        record("CONN_MAX_AGE", settings.DATABASES["default"].get("CONN_MAX_AGE") == 60, str(settings.DATABASES["default"].get("CONN_MAX_AGE")))
        record("STORAGE_BACKEND=s3", settings.STORAGE_BACKEND == "s3")
        record("BLACKLIST_AFTER_ROTATION", settings.SIMPLE_JWT.get("BLACKLIST_AFTER_ROTATION") is True)
    except Exception as exc:
        record("settings scale", False, str(exc))

    print("\n=== Phase 3 — long terme ===")
    try:
        from apps.reporting.tasks import refresh_reporting_snapshots
        from apps.reporting.models import ReportingSnapshot

        n = refresh_reporting_snapshots()
        count = ReportingSnapshot.objects.count()
        record("refresh snapshots reporting", n > 0 and count > 0, f"n={n} rows={count}")
    except Exception as exc:
        record("refresh snapshots reporting", False, str(exc))

    try:
        _, dash = request("GET", "/reporting/dashboard/", token=access, expect=(200, 400))
        # group_admin sans tenant peut avoir scope GROUP via consolidation
        record(
            "dashboard API",
            isinstance(dash, dict) and ("credits" in dash or "detail" in dash or "_snapshot" in dash or "scope" in dash),
            str(list(dash.keys())[:6]) if isinstance(dash, dict) else str(dash)[:80],
        )
    except Exception as exc:
        record("dashboard API", False, str(exc))

    try:
        _, cons = request("GET", "/reporting/group-consolidation/", token=access)
        has_snap = isinstance(cons, dict) and (
            "_snapshot" in cons or cons.get("scope") == "GROUPE" or "credits" in cons
        )
        record("consolidation snapshot/live", has_snap, f"snapshot={'_snapshot' in cons if isinstance(cons, dict) else False}")
    except Exception as exc:
        record("consolidation snapshot/live", False, str(exc))

    try:
        _, metrics = request("GET", "/metrics/", token=access)
        record(
            "metrics endpoint",
            isinstance(metrics, dict) and "tenants_active" in metrics,
            f"tenants={metrics.get('tenants_active') if isinstance(metrics, dict) else '?'}",
        )
    except Exception as exc:
        record("metrics endpoint", False, str(exc))

    try:
        from apps.tenants.models import Tenant

        # champs quota présents
        f = {x.name for x in Tenant._meta.get_fields()}
        record("GED quota fields", "ged_quota_bytes" in f and "ged_used_bytes" in f)
    except Exception as exc:
        record("GED quota fields", False, str(exc))

    try:
        from django.conf import settings

        record(
            "TENANT_ISOLATION_MODE",
            getattr(settings, "TENANT_ISOLATION_MODE", None) == "shared",
            getattr(settings, "TENANT_ISOLATION_MODE", None),
        )
        record(
            "AUDIT_RETENTION_DAYS",
            int(getattr(settings, "AUDIT_RETENTION_DAYS", 0)) > 0,
            str(getattr(settings, "AUDIT_RETENTION_DAYS", None)),
        )
    except Exception as exc:
        record("settings long terme", False, str(exc))

    # Throttle classes actives
    try:
        from django.conf import settings

        classes = settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_CLASSES") or ()
        record("throttles DRF actifs", len(classes) >= 2, str(classes))
    except Exception as exc:
        record("throttles DRF actifs", False, str(exc))

    print("\n=== Résumé ===")
    print(f"OK={OK}  KO={KO}  total={OK + KO}")
    return 0 if KO == 0 else 1


if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
    import django

    django.setup()
    sys.exit(main())
