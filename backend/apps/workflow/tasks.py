"""Tâches Celery — workflow (SLA)."""
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger("finflow")


@shared_task(ignore_result=True, soft_time_limit=120, time_limit=180)
def flag_sla_breaches():
    """Repère les tâches d'approbation hors SLA et notifie (dédup 24 h)."""
    from apps.notifications.models import NotificationLog
    from apps.notifications.services import notify_sla_breach
    from apps.workflow.models import ApprovalTask

    now = timezone.now()
    since = now - timedelta(hours=24)
    overdue = (
        ApprovalTask.all_tenants.filter(
            status=ApprovalTask.Status.PENDING,
            instance__status="IN_PROGRESS",
            due_at__isnull=False,
            due_at__lt=now,
        )
        .select_related(
            "step",
            "step__required_group",
            "instance",
            "instance__tenant",
        )
        .order_by("due_at")[:200]
    )
    notified = 0
    for task in overdue:
        already = NotificationLog.all_tenants.filter(
            approval_task_id=task.id,
            subject__startswith="[FIN_FLOW][SLA]",
            created_at__gte=since,
        ).exists()
        if already:
            continue
        try:
            notify_sla_breach(task)
            notified += 1
        except Exception:  # noqa: BLE001
            logger.exception("Échec notification SLA task=%s", task.id)
    logger.info("SLA : %s notifications envoyées", notified)
    return notified
