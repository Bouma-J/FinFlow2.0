"""Chiffrement au repos des secrets applicatifs (SMTP, auth CBS).

- Préfixe ``enc:`` pour distinguer clair legacy et valeurs chiffrées.
- Clé : ``FIELD_ENCRYPTION_KEY`` (Fernet url-safe) ou dérivée de ``SECRET_KEY``.
- Lecture rétrocompatible : valeurs sans préfixe = plaintext.
"""
from __future__ import annotations

import base64
import hashlib
import json
from functools import lru_cache

from django.conf import settings

PREFIX = "enc:"

# Clés sensibles dans auth_config CBS
AUTH_SECRET_KEYS = (
    "password",
    "client_secret",
    "access_token",
    "accessToken",
    "bearer_token",
    "token",
    "secret",
)


@lru_cache(maxsize=1)
def _fernet():
    from cryptography.fernet import Fernet

    raw = (getattr(settings, "FIELD_ENCRYPTION_KEY", None) or "").strip()
    if not raw:
        # Prod doit définir FIELD_ENCRYPTION_KEY (voir settings/prod.py).
        # Hors prod : dérivation stable pour le développement uniquement.
        if not getattr(settings, "DEBUG", False):
            from django.core.exceptions import ImproperlyConfigured

            raise ImproperlyConfigured(
                "FIELD_ENCRYPTION_KEY est obligatoire lorsque DEBUG=False "
                "(évite de lier le coffre secrets à DJANGO_SECRET_KEY)."
            )
        digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(digest))
    key = raw.encode("ascii") if isinstance(raw, str) else raw
    return Fernet(key)


def encrypt_str(value: str | None) -> str:
    if value is None:
        return ""
    text = str(value)
    if not text:
        return ""
    if text.startswith(PREFIX):
        return text
    token = _fernet().encrypt(text.encode("utf-8")).decode("ascii")
    return f"{PREFIX}{token}"


def decrypt_str(value: str | None) -> str:
    if value is None:
        return ""
    text = str(value)
    if not text:
        return ""
    if not text.startswith(PREFIX):
        return text
    from cryptography.fernet import InvalidToken

    try:
        return _fernet().decrypt(text[len(PREFIX) :].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        # Valeur corrompue ou mauvaise clé : ne pas faire planter l'app
        return ""


def is_encrypted(value: str | None) -> bool:
    return bool(value) and str(value).startswith(PREFIX)


def encrypt_auth_config(cfg: dict | None) -> dict:
    out = dict(cfg or {})
    for key in AUTH_SECRET_KEYS:
        if key in out and out[key]:
            out[key] = encrypt_str(str(out[key]))
    return out


def decrypt_auth_config(cfg: dict | None) -> dict:
    out = dict(cfg or {})
    for key in AUTH_SECRET_KEYS:
        if key in out and out[key]:
            out[key] = decrypt_str(str(out[key]))
    return out


def encrypt_json_blob(payload: dict | None) -> str:
    """Chiffre un dict entier (optionnel, pour blobs)."""
    raw = json.dumps(payload or {}, separators=(",", ":"), ensure_ascii=False)
    return encrypt_str(raw)


def decrypt_json_blob(value: str | None) -> dict:
    plain = decrypt_str(value)
    if not plain:
        return {}
    try:
        data = json.loads(plain)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}
