"""Tâches Celery pour l'envoi asynchrone des notifications."""
import logging

from celery import shared_task

logger = logging.getLogger("finflow")


@shared_task(ignore_result=True, soft_time_limit=120, time_limit=180)
def send_step_opened_emails(instance_id: str, order: int):
    from apps.workflow.models import ApprovalTask, WorkflowInstance

    from .services import notify_step_opened

    try:
        instance = WorkflowInstance.all_tenants.select_related(
            "tenant", "definition"
        ).get(pk=instance_id)
    except WorkflowInstance.DoesNotExist:
        logger.warning("WorkflowInstance %s introuvable pour notification", instance_id)
        return

    # all_tenants : le worker Celery n'a pas de contexte tenant HTTP.
    tasks = ApprovalTask.all_tenants.filter(
        instance=instance,
        step__order=order,
        status=ApprovalTask.Status.PENDING,
    ).select_related("step", "step__required_group")
    seen_steps = set()
    for task in tasks:
        if task.step_id in seen_steps:
            continue
        seen_steps.add(task.step_id)
        notify_step_opened(instance, task.step, task=task)


@shared_task(ignore_result=True, soft_time_limit=120, time_limit=180)
def send_workflow_outcome_email(instance_id: str, outcome: str):
    from apps.workflow.models import WorkflowInstance

    from .services import notify_workflow_outcome

    try:
        instance = WorkflowInstance.all_tenants.select_related(
            "tenant", "definition"
        ).prefetch_related("tasks", "tasks__acted_by").get(pk=instance_id)
    except WorkflowInstance.DoesNotExist:
        logger.warning("WorkflowInstance %s introuvable pour notification", instance_id)
        return

    notify_workflow_outcome(instance, outcome)
