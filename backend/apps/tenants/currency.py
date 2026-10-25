"""Résolution de la devise filiale (source de vérité : Tenant.currency)."""

DEFAULT_CURRENCY = "XOF"


def tenant_currency(tenant_or_id, *, fallback: str = DEFAULT_CURRENCY) -> str:
    """
    Renvoie la devise locale de la filiale.

    Accepte un Tenant, un UUID/str d'id, ou None (→ fallback).
    """
    if tenant_or_id is None:
        return fallback
    currency = getattr(tenant_or_id, "currency", None)
    if currency:
        return str(currency).strip().upper() or fallback
    from apps.tenants.models import Tenant

    row = (
        Tenant.objects.filter(pk=tenant_or_id)
        .values_list("currency", flat=True)
        .first()
    )
    if row:
        return str(row).strip().upper() or fallback
    return fallback
