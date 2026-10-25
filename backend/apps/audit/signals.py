"""
Enregistrement automatique de la piste d'audit.

Tout modèle héritant de `TenantScopedModel` est audité automatiquement
(création / modification / suppression), sans code supplémentaire dans
les modules métier.
"""
from contextvars import ContextVar

from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import receiver

from apps.common.models import TenantScopedModel

from .context import get_current_ip, get_current_user
from .models import AuditLog

# Filiales en cours de suppression dans le contexte courant. La suppression
# d'une filiale cascade sur ses données métier, dont chaque `post_delete`
# écrirait une entrée d'audit pointant sur une filiale qui n'existera plus au
# COMMIT (les contraintes FK de Postgres sont différées) : on détache donc ces
# entrées de la filiale au lieu de faire échouer toute la transaction.
_deleting_tenant_ids = ContextVar("finflow_deleting_tenant_ids", default=frozenset())


def _iter_audited_models():
    for model in TenantScopedModel.__subclasses__():
        # On ignore les classes encore abstraites.
        if not model._meta.abstract:
            yield model


def _serialize_instance(instance):
    data = {}
    for field in instance._meta.fields:
        if field.name in ("created_at", "updated_at"):
            continue
        value = getattr(instance, field.attname, None)
        data[field.name] = str(value) if value is not None else None
    return data


@receiver(pre_delete, sender="tenants.Tenant")
def tenant_deletion_started(sender, instance, **kwargs):
    """Marque la filiale comme condamnée avant la cascade de suppressions.

    Django émet tous les `pre_delete` de la collecte avant le premier
    `post_delete` : le marqueur est donc bien posé quand les entités filles
    sont auditées.
    """
    _deleting_tenant_ids.set(_deleting_tenant_ids.get() | {instance.pk})


@receiver(post_delete, sender="tenants.Tenant")
def tenant_deletion_finished(sender, instance, **kwargs):
    _deleting_tenant_ids.set(_deleting_tenant_ids.get() - {instance.pk})


@receiver(post_save)
def log_save(sender, instance, created, **kwargs):
    if not isinstance(instance, TenantScopedModel) or sender is AuditLog:
        return
    AuditLog.objects.create(
        tenant_id=getattr(instance, "tenant_id", None),
        user=get_current_user(),
        action=AuditLog.Action.CREATE if created else AuditLog.Action.UPDATE,
        model_label=instance._meta.label,
        object_id=str(instance.pk),
        object_repr=str(instance)[:255],
        changes=_serialize_instance(instance),
        ip_address=get_current_ip(),
    )


@receiver(post_delete)
def log_delete(sender, instance, **kwargs):
    if not isinstance(instance, TenantScopedModel) or sender is AuditLog:
        return
    tenant_id = getattr(instance, "tenant_id", None)
    changes = {}
    if tenant_id is not None and tenant_id in _deleting_tenant_ids.get():
        # La filiale disparaît : on conserve son identifiant dans les données
        # de l'entrée, seule la clé étrangère est détachée.
        changes = {"tenant_id": str(tenant_id)}
        tenant_id = None
    AuditLog.objects.create(
        tenant_id=tenant_id,
        user=get_current_user(),
        action=AuditLog.Action.DELETE,
        model_label=instance._meta.label,
        object_id=str(instance.pk),
        object_repr=str(instance)[:255],
        changes=changes,
        ip_address=get_current_ip(),
    )
