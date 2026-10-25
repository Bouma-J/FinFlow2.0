"""Audit nominatif des habilitations, sans mots de passe ni secrets MFA."""
from django.contrib.auth.models import Group
from django.db.models.signals import pre_save, post_save, post_delete, m2m_changed
from django.dispatch import receiver

from apps.audit.context import get_current_user, get_current_ip
from apps.audit.models import AuditLog
from .models import User, Delegation, TenantRole


FIELDS = {
    User: ("username", "is_active", "is_staff", "is_superuser", "tenant_id", "agency_id", "data_scope", "is_group_level", "mfa_enabled", "must_change_password"),
    Delegation: ("delegator_id", "delegate_id", "reason", "start_date", "end_date", "is_active", "max_amount", "product_id", "agency_id", "step_kind", "approval_required", "approved_by_id", "approved_at"),
    TenantRole: ("tenant_id", "name", "group_id", "pack_code"),
    Group: ("name",),
}


def state(instance):
    return {key: str(getattr(instance, key)) if getattr(instance, key) is not None else None for key in FIELDS[type(instance)]}


def log(instance, action, changes):
    actor = get_current_user()
    tenant_id = getattr(instance, "tenant_id", None)
    if isinstance(instance, Delegation):
        tenant_id = instance.delegator.tenant_id
    if isinstance(instance, Group):
        tenant_id = TenantRole.objects.filter(group=instance).values_list("tenant_id", flat=True).first()
    if tenant_id is None and actor:
        tenant_id = actor.tenant_id
    from apps.audit.signals import _deleting_tenant_ids
    if tenant_id in _deleting_tenant_ids.get():
        tenant_id = None
    AuditLog.objects.create(tenant_id=tenant_id, user=actor, action=action,
        model_label=instance._meta.label, object_id=str(instance.pk),
        object_repr=str(instance)[:255], changes=changes, ip_address=get_current_ip())


@receiver(pre_save)
def before_access_save(sender, instance, **kwargs):
    if sender not in FIELDS:
        return
    previous = sender.objects.filter(pk=instance.pk).first() if instance.pk else None
    instance._access_before = state(previous) if previous else None


@receiver(post_save)
def after_access_save(sender, instance, created, **kwargs):
    if sender not in FIELDS:
        return
    before, after = getattr(instance, "_access_before", None), state(instance)
    if created or before != after:
        log(instance, "CREATE" if created else "UPDATE", {"before": before, "after": after})


@receiver(post_delete)
def access_deleted(sender, instance, **kwargs):
    if sender in FIELDS:
        log(instance, "DELETE", {"before": state(instance), "after": None})


@receiver(m2m_changed)
def access_membership_changed(sender, instance, action, reverse, pk_set, model, **kwargs):
    if sender not in (User.groups.through, User.user_permissions.through, User.agencies.through, Group.permissions.through):
        return
    if action not in ("pre_add", "pre_remove", "pre_clear"):
        return
    before = list(sender.objects.filter(**{
        ("group_id" if reverse and sender == User.groups.through else
         "permission_id" if reverse and sender in (User.user_permissions.through, Group.permissions.through) else
         "agency_id" if reverse else "group_id" if sender == Group.permissions.through else "user_id"): instance.pk
    }).values())
    log(instance, "UPDATE", {"membership_action": action, "relation": sender._meta.label,
        "reverse": reverse, "related_ids": sorted(str(pk) for pk in (pk_set or [])),
        "memberships_before": [{key: str(value) for key, value in row.items()} for row in before]})
