"""Validation des identifiants CBS issus des référentiels synchronisés."""
from __future__ import annotations

from rest_framework import serializers

from apps.common.tenancy import get_current_tenant_id


def validate_service_point_id(value: str, *, tenant_id=None) -> str:
    """``Agency.cbs_point_of_service_id`` doit être un id Perfect syncé (ou vide)."""
    value = (value or "").strip()
    if not value:
        return ""
    from .models import ServicePoint

    tid = tenant_id or get_current_tenant_id()
    qs = ServicePoint.all_tenants.filter(cbs_code=value, is_active=True)
    if tid:
        qs = qs.filter(tenant_id=tid)
    if not qs.exists():
        raise serializers.ValidationError(
            "Point de service CBS inconnu. Importez d'abord les référentiels CBS, "
            "puis sélectionnez une entrée de la liste."
        )
    return value


def validate_manager_cbs_id(value: str, *, tenant_id=None) -> str:
    """``User.cbs_id`` doit être un idGestionnaire syncé (ou vide)."""
    value = (value or "").strip()
    if not value:
        return ""
    from .models import CbsManager

    tid = tenant_id or get_current_tenant_id()
    qs = CbsManager.all_tenants.filter(cbs_code=value, is_active=True)
    if tid:
        qs = qs.filter(tenant_id=tid)
    if not qs.exists():
        raise serializers.ValidationError(
            "Gestionnaire CBS inconnu. Importez d'abord les référentiels CBS, "
            "puis associez un gestionnaire de la liste."
        )
    return value
