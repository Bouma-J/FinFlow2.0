"""Tâches Celery — audit (rétention)."""
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("finflow")


@shared_task(ignore_result=True, soft_time_limit=600, time_limit=660)
def purge_old_audit_logs():
    """
    Supprime les entrées d'audit plus anciennes que AUDIT_RETENTION_DAYS.
    Par défaut 365 jours. Mettre 0 pour désactiver.
    """
    from apps.audit.models import AuditLog

    days = int(getattr(settings, "AUDIT_RETENTION_DAYS", 365))
    if days <= 0:
        logger.info("Purge audit désactivée (AUDIT_RETENTION_DAYS=%s)", days)
        return 0
    cutoff = timezone.now() - timedelta(days=days)
    deleted, _ = AuditLog.objects.filter(timestamp__lt=cutoff).delete()
    logger.info("Audit : %s lignes purgées (avant %s)", deleted, cutoff.date())
    return deleted
