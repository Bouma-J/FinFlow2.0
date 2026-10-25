"""Accès objet scopé par filiale — sûr sous contexte Groupe.

Sous ``is_group_context``, ``TenantManager`` ne filtre pas : un
``Model.objects.get(pk=…)`` peut donc résoudre un UUID d'une autre
filiale. Toujours passer par ``get_for_tenant`` (ou le queryset du
ViewSet) pour les mutations.
"""
from __future__ import annotations

from django.core.cache import cache
from rest_framework.exceptions import NotFound, ValidationError

from apps.common.tenancy import get_current_tenant_id


def require_tenant_id():
    """Exige une filiale active (header X-Tenant-Id ou user.tenant_id)."""
    tenant_id = get_current_tenant_id()
    if tenant_id is None:
        raise ValidationError(
            {
                "detail": (
                    "Aucune filiale sélectionnée. Choisissez une filiale "
                    "avant cette action."
                )
            }
        )
    return tenant_id


def get_for_tenant(
    model,
    pk,
    *,
    tenant_field: str = "tenant_id",
    error_field: str | None = None,
):
    """
    Charge ``pk`` et refuse s'il n'appartient pas au tenant courant.

    Utilise ``all_tenants`` quand disponible pour éviter les pièges du
    manager par défaut en contexte Groupe, puis assert le tenant.

    Si ``error_field`` est fourni, lève ``ValidationError`` sur ce champ
    (UX formulaires) plutôt qu'un 404 générique.
    """
    tenant_id = require_tenant_id()
    manager = getattr(model, "all_tenants", None) or model._default_manager

    def _missing():
        if error_field:
            raise ValidationError({error_field: "Introuvable."})
        raise NotFound()

    try:
        obj = manager.get(pk=pk)
    except model.DoesNotExist as exc:
        try:
            _missing()
        except (NotFound, ValidationError) as err:
            raise err from exc

    obj_tid = getattr(obj, tenant_field, None)
    if obj_tid is None and hasattr(obj, "tenant_id"):
        obj_tid = obj.tenant_id
    if str(obj_tid) != str(tenant_id):
        # Ne pas révéler l'existence cross-filiale.
        _missing()
    return obj


def track_async_task(task_id: str, user_id, *, ttl: int = 3600) -> None:
    """Associe une tâche Celery à l'utilisateur qui l'a lancée."""
    if not task_id or not user_id:
        return
    cache.set(f"async_task_owner:{task_id}", str(user_id), ttl)


def async_task_owner(task_id: str) -> str | None:
    return cache.get(f"async_task_owner:{task_id}")
