"""Journalisation d'évènements métier lisibles (piste d'audit workflow)."""
from .context import get_current_ip, get_current_user
from .models import AuditLog

# Codes d'évènements de workflow d'un dossier de crédit.
SUBMITTED = "SUBMITTED"
RESUBMITTED = "RESUBMITTED"
CANCELLED = "CANCELLED"
RETURNED_STEP = "RETURNED_STEP"
RETURNED_SUBMITTER = "RETURNED_SUBMITTER"
DELETED = "DELETED"


def log_workflow_event(application, event, detail="", user=None):
    """Enregistre un évènement de workflow explicite sur un dossier.

    Complète la piste d'audit automatique (CREATE/UPDATE/DELETE) par des entrées
    « WORKFLOW » lisibles (soumission, annulation, renvois, re-soumission…).
    """
    try:
        AuditLog.objects.create(
            tenant_id=getattr(application, "tenant_id", None),
            user=user or get_current_user(),
            action=AuditLog.Action.WORKFLOW,
            model_label=application._meta.label,
            object_id=str(application.pk),
            object_repr=str(application)[:255],
            changes={"event": event, "detail": detail or ""},
            ip_address=get_current_ip(),
        )
    except Exception:  # noqa: BLE001 - l'audit ne doit jamais bloquer l'action
        pass
