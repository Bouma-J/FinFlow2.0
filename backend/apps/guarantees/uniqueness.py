"""Unicité des garanties déjà prises (hypothèque et gage hors bijou)."""
from __future__ import annotations

from apps.guarantees.models import Guarantee, PledgeCategory


def normalize_document_number(value: str | None) -> str:
    return " ".join((value or "").split()).upper()


def normalize_chassis(value: str | None) -> str:
    return "".join(ch for ch in (value or "").upper() if ch.isalnum())


def _is_vehicle(guarantee_type, pledge_category) -> bool:
    return (
        guarantee_type == Guarantee.GuaranteeType.PLEDGE
        and pledge_category == PledgeCategory.VEHICLE
    )


def _is_mortgage(guarantee_type) -> bool:
    return guarantee_type == Guarantee.GuaranteeType.MORTGAGE


def _conflict_message(conflict: Guarantee) -> str:
    client = ""
    if conflict.client_id:
        client = (
            getattr(conflict.client, "display_name", None) or str(conflict.client)
        )
    app_ref = ""
    if conflict.application_id:
        app_ref = conflict.application.reference or str(conflict.application_id)
    ref = conflict.reference or str(conflict.id)[:8]
    parts = [f"garantie {ref}"]
    if client:
        parts.append(f"client {client}")
    if app_ref:
        parts.append(f"dossier {app_ref}")
    return "Ce bien est déjà pris en garantie (" + " — ".join(parts) + ")."


def find_conflicting_guarantee(
    *,
    guarantee_type,
    pledge_category="",
    document_type="",
    document_number="",
    chassis_number="",
    exclude_id=None,
    tenant_id=None,
) -> Guarantee | None:
    """
    Autre garantie ACTIVE portant le même titre (hypothèque) ou le même
    châssis (gage véhicule). Les bijoux et les garanties levées / réalisées
    / transférées ne bloquent pas.
    """
    if _is_mortgage(guarantee_type):
        key = normalize_document_number(document_number)
        if not key or not document_type:
            return None
        from apps.common.tenancy import get_current_tenant_id

        tenant_id = tenant_id or get_current_tenant_id()
        qs = (
            Guarantee.objects.filter(
                status=Guarantee.Status.ACTIVE,
                guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
                document_type=document_type,
            )
            .exclude(document_number="")
            .select_related("client", "application")
        )
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        if exclude_id:
            qs = qs.exclude(pk=exclude_id)
        for row in qs:
            if normalize_document_number(row.document_number) == key:
                return row
        return None

    if _is_vehicle(guarantee_type, pledge_category):
        key = normalize_chassis(chassis_number)
        if not key:
            return None
        from apps.common.tenancy import get_current_tenant_id

        tenant_id = tenant_id or get_current_tenant_id()
        qs = (
            Guarantee.objects.filter(
                status=Guarantee.Status.ACTIVE,
                guarantee_type=Guarantee.GuaranteeType.PLEDGE,
                pledge_category=PledgeCategory.VEHICLE,
            )
            .exclude(chassis_number="")
            .select_related("client", "application")
        )
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        if exclude_id:
            qs = qs.exclude(pk=exclude_id)
        for row in qs:
            if normalize_chassis(row.chassis_number) == key:
                return row
        return None

    return None


def conflict_details(conflict: Guarantee) -> dict:
    client = ""
    if conflict.client_id:
        client = (
            getattr(conflict.client, "display_name", None) or str(conflict.client)
        )
    app_ref = ""
    app_id = None
    if conflict.application_id:
        app_id = str(conflict.application_id)
        app_ref = conflict.application.reference or app_id
    return {
        "code": "GUARANTEE_ALREADY_TAKEN",
        "message": _conflict_message(conflict),
        "id": str(conflict.id),
        "reference": conflict.reference or str(conflict.id)[:8],
        "client_display": client,
        "application_id": app_id,
        "application_reference": app_ref,
    }


def uniqueness_error(
    *,
    guarantee_type,
    pledge_category="",
    document_type="",
    document_number="",
    chassis_number="",
    exclude_id=None,
    tenant_id=None,
) -> dict | None:
    conflict = find_conflicting_guarantee(
        guarantee_type=guarantee_type,
        pledge_category=pledge_category,
        document_type=document_type,
        document_number=document_number,
        chassis_number=chassis_number,
        exclude_id=exclude_id,
        tenant_id=tenant_id,
    )
    if conflict is None:
        return None
    return {"already_taken": conflict_details(conflict)}
