"""Helpers de cache applicatif (Redis)."""
from __future__ import annotations

import hashlib
from typing import Any, Callable

from django.core.cache import cache


def cache_key(*parts: Any) -> str:
    raw = ":".join("" if p is None else str(p) for p in parts)
    if len(raw) > 200:
        return hashlib.sha256(raw.encode()).hexdigest()
    return raw


def cached_get(key: str, producer: Callable[[], Any], timeout: int = 60) -> Any:
    """Lit le cache ou calcule et stocke la valeur."""
    value = cache.get(key)
    if value is not None:
        return value
    value = producer()
    cache.set(key, value, timeout)
    return value


def invalidate_prefix(*parts: Any) -> None:
    """Invalide une clé exacte (pas de wildcards Redis sans django-redis)."""
    cache.delete(cache_key(*parts))
