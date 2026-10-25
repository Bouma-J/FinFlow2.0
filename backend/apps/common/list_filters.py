"""Filtres de liste partagés (query params)."""
from __future__ import annotations

from django.db.models import Q, QuerySet


def query_param(request, name: str) -> str:
    return (request.query_params.get(name) or "").strip()


def apply_or_lookups(qs: QuerySet, value: str, *lookups: str) -> QuerySet:
    if not value:
        return qs
    combined = Q()
    for lookup in lookups:
        combined |= Q(**{lookup: value})
    return qs.filter(combined)


def apply_gestionnaire(qs: QuerySet, request, *lookups: str) -> QuerySet:
    """Filtre créateur / soumetteur (gestionnaire du dossier)."""
    value = query_param(request, "gestionnaire")
    return apply_or_lookups(qs, value, *lookups)
