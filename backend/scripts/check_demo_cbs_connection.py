"""Read-only CBS authentication/reference probe; never prints credentials or tokens.

Run via manage.py shell -c "exec(open('backend/scripts/check_demo_cbs_connection.py').read())".
Uses the FIL01 active connector directly through RestAdapter without saving changes.
"""
import json
import re
import time
import os
import ssl
from contextlib import ExitStack
from unittest.mock import patch
from urllib.parse import urlsplit

from apps.tenants.models import Tenant
from apps.corebanking.services import RestAdapter, get_adapter, resolve_active_connector

tenant = Tenant.objects.get(code="FIL01")
connector = resolve_active_connector(tenant.pk)
connector.timeout_seconds = min(connector.timeout_seconds or 30, 20)
adapter = RestAdapter(connector)
probe_stack = ExitStack()
if os.environ.get("CBS_PROBE_SYSTEM_TRUST") == "1":
    import requests
    from requests.adapters import HTTPAdapter

    class SystemTrustAdapter(HTTPAdapter):
        def init_poolmanager(self, *args, **kwargs):
            kwargs["ssl_context"] = ssl.create_default_context()
            return super().init_poolmanager(*args, **kwargs)

    session = probe_stack.enter_context(requests.Session())
    session.mount("https://", SystemTrustAdapter())
    probe_stack.enter_context(patch("requests.post", session.post))
    probe_stack.enter_context(patch("requests.get", session.get))
report = {
    "tenant": tenant.code,
    "connector": connector.name,
    "normal_adapter": type(get_adapter(connector)).__name__,
    "trust_source": "system_plus_requests" if os.environ.get("CBS_PROBE_SYSTEM_TRUST") == "1" else "requests_default",
    "checks": [],
}
auth = connector.get_auth_config_decrypted()
secret_values = [
    str(value) for key, value in auth.items()
    if value and key.lower() in {
        "username", "password", "token", "access_token", "accesstoken",
        "client_secret", "bearer_token",
    }
]
http_events = []

for method in ("_http_post", "_http_get"):
    original = getattr(adapter, method)

    def recorded(url, _original=original, _method=method, **kwargs):
        response = _original(url, **kwargs)
        parsed = urlsplit(response.url)
        http_events.append({
            "method": _method, "host": parsed.hostname,
            "path": parsed.path, "http": response.status_code,
        })
        return response

    setattr(adapter, method, recorded)


def safe_error(exc):
    message = str(exc)
    for value in secret_values:
        message = message.replace(value, "[redacted]")
    return re.sub(r"eyJ[A-Za-z0-9_.-]+", "[redacted-token]", message)[:400]


started = time.monotonic()
try:
    token = adapter._resolve_bearer_token()
    secret_values.append(token)
    report["checks"].append({
        "check": "real_authentication", "ok": bool(token),
        "duration_seconds": round(time.monotonic() - started, 2),
    })
    adapter._resolve_bearer_token = lambda: token
    for key in ("ref_devise_list", "ref_point_service_list"):
        started = time.monotonic()
        try:
            rows = adapter.fetch_ref_list(key)
            report["checks"].append({
                "check": key, "ok": True, "rows": len(rows),
                "duration_seconds": round(time.monotonic() - started, 2),
            })
        except Exception as exc:
            report["checks"].append({"check": key, "ok": False, "error": safe_error(exc)})
except Exception as exc:
    report["checks"].append({
        "check": "real_authentication", "ok": False, "error": safe_error(exc),
        "duration_seconds": round(time.monotonic() - started, 2),
    })
report["http_events"] = http_events
probe_stack.close()
print(json.dumps(report, ensure_ascii=True))
