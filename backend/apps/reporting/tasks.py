"""Tâches Celery — reporting matérialisé."""
import logging

from celery import shared_task

logger = logging.getLogger("finflow")


@shared_task(ignore_result=True, soft_time_limit=300, time_limit=360)
def refresh_reporting_snapshots():
    from apps.reporting.snapshots import refresh_all_snapshots

    n = refresh_all_snapshots()
    logger.info("Reporting : %s snapshots rafraîchis", n)
    return n
