"""Configuration de l'application Celery pour FIN_FLOW."""
import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("finflow")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "flag-sla-breaches": {
        "task": "apps.workflow.tasks.flag_sla_breaches",
        "schedule": crontab(minute="*/15"),
    },
    "refresh-overdue-loans": {
        "task": "apps.collections.tasks.refresh_all_overdue_loans",
        "schedule": crontab(hour=2, minute=15),
    },
    "send-collection-reminders": {
        "task": "apps.collections.tasks.send_collection_reminders",
        "schedule": crontab(hour=8, minute=0),
    },
    "notify-hearing-reminders": {
        "task": "apps.collections.tasks.notify_hearing_reminders",
        "schedule": crontab(hour=7, minute=30),
    },
    "retry-cbs-integrations": {
        "task": "apps.corebanking.tasks.retry_cbs_integrations",
        "schedule": crontab(minute="*/10"),
    },
    "purge-old-audit-logs": {
        "task": "apps.audit.tasks.purge_old_audit_logs",
        "schedule": crontab(hour=3, minute=30),
    },
    "notify-expiring-documents": {
        "task": "apps.documents.tasks.notify_expiring_documents",
        "schedule": crontab(hour=7, minute=0),
    },
    "purge-soft-deleted-documents": {
        "task": "apps.documents.tasks.purge_soft_deleted_documents",
        "schedule": crontab(hour=4, minute=10),
    },
    "refresh-reporting-snapshots": {
        "task": "apps.reporting.tasks.refresh_reporting_snapshots",
        "schedule": crontab(minute=20),  # toutes les heures à :20
    },
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
