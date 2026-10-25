"""Tâches Celery — GED (alertes expiration + purge soft-delete)."""
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db.models import QuerySet
from django.utils import timezone

logger = logging.getLogger("finflow")


@shared_task(ignore_result=True, soft_time_limit=120, time_limit=180)
def notify_expiring_documents():
    """Journalise les documents expirant sous 30 jours (hook alertes)."""
    from apps.documents.models import Document

    horizon = timezone.now().date() + timedelta(days=30)
    qs = Document.all_tenants.filter(
        category__tracks_expiry=True,
        expiry_date__isnull=False,
        expiry_date__lte=horizon,
    )
    count = qs.count()
    logger.info("GED : %s document(s) à échéance ≤ 30 j", count)
    return count


@shared_task(ignore_result=True, soft_time_limit=300, time_limit=360)
def purge_soft_deleted_documents():
    """
    Purge hard des documents soft-deleted au-delà de la rétention
    (GED_SOFT_DELETE_RETENTION_DAYS, défaut 90).
    """
    from apps.documents.models import Document
    from apps.documents.quotas import bump_ged_usage

    days = int(getattr(settings, "GED_SOFT_DELETE_RETENTION_DAYS", 90) or 90)
    cutoff = timezone.now() - timedelta(days=days)
    targets = list(
        Document.including_deleted.filter(
            is_deleted=True, deleted_at__lt=cutoff
        ).order_by("deleted_at")[:500]
    )
    purged = 0
    for doc in targets:
        size = int(doc.size_bytes or 0)
        tenant_id = doc.tenant_id
        file_name = ""
        storage = None
        if doc.file and getattr(doc.file, "name", None):
            file_name = doc.file.name
            storage = doc.file.storage
        doc_id = doc.pk
        try:
            QuerySet.delete(Document.including_deleted.filter(pk=doc_id))
        except Exception:  # noqa: BLE001
            logger.exception("Purge GED échouée id=%s", doc_id)
            continue
        if file_name and storage is not None:
            try:
                storage.delete(file_name)
            except Exception:  # noqa: BLE001
                logger.exception("Purge fichier GED key=%s", file_name)
        if size:
            try:
                bump_ged_usage(tenant_id, -size)
            except Exception:  # noqa: BLE001
                logger.exception("Quota après purge id=%s", doc_id)
        purged += 1
    logger.info("GED purge soft-delete : %s document(s)", purged)
    return purged
