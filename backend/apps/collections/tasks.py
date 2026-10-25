"""Tâches Celery — recouvrement."""
import logging

from celery import shared_task

logger = logging.getLogger("finflow")


@shared_task(
    ignore_result=True,
    soft_time_limit=1800,
    time_limit=1860,
)
def refresh_all_overdue_loans():
    """Recalcule les retards PAR depuis le CBS pour tous les prêts actifs."""
    from apps.collections.services import (
        loan_cbs_reference,
        refresh_broken_promises,
        refresh_loan_overdue,
    )
    from apps.common.tenancy import tenant_context
    from apps.credits.models import Loan

    loans = Loan.all_tenants.filter(status=Loan.Status.ACTIVE).iterator()
    count = 0
    skipped = 0
    for loan in loans:
        try:
            # TenantManager filtre sur ContextVar : obligatoire hors requête HTTP.
            with tenant_context(loan.tenant_id):
                if not loan_cbs_reference(loan):
                    skipped += 1
                    continue
                refresh_loan_overdue(loan)
            count += 1
        except Exception:  # noqa: BLE001
            logger.exception("Échec refresh overdue loan=%s", loan.id)
    broken = refresh_broken_promises()
    logger.info(
        "Recouvrement CBS : %s prêts actualisés, %s sans réf. CBS, %s promesses rompues",
        count,
        skipped,
        broken,
    )
    return count


@shared_task(
    ignore_result=True,
    soft_time_limit=900,
    time_limit=960,
)
def refresh_tenant_overdue_loans(tenant_id: str):
    """Recalcule les retards CBS pour une filiale (déclenché depuis l'API)."""
    from apps.collections.services import (
        loan_cbs_reference,
        refresh_broken_promises,
        refresh_loan_overdue,
    )
    from apps.common.tenancy import tenant_context
    from apps.credits.models import Loan

    refreshed = 0
    skipped = 0
    with tenant_context(tenant_id):
        loans = Loan.objects.filter(status=Loan.Status.ACTIVE)
        for loan in loans.iterator():
            try:
                if not loan_cbs_reference(loan):
                    skipped += 1
                    continue
                refresh_loan_overdue(loan)
                refreshed += 1
            except Exception:  # noqa: BLE001
                logger.exception("Échec refresh overdue loan=%s", loan.id)
        broken = refresh_broken_promises()
    logger.info(
        "Recouvrement CBS filiale %s : %s prêts, %s sans réf., %s promesses rompues",
        tenant_id,
        refreshed,
        skipped,
        broken,
    )
    return {
        "refreshed_loans": refreshed,
        "skipped_no_cbs_ref": skipped,
        "broken_promises": broken,
    }


@shared_task(ignore_result=True, soft_time_limit=600, time_limit=660)
def send_collection_reminders():
    """Relances automatiques EMAIL/SMS pour les actions dues."""
    from apps.collections.services import send_due_collection_reminders

    stats = send_due_collection_reminders()
    logger.info("Relances recouvrement : %s", stats)
    return stats


@shared_task(ignore_result=True, soft_time_limit=300, time_limit=360)
def notify_hearing_reminders():
    """Rappels e-mail pour les audiences contentieux à J-7."""
    from apps.collections.services import notify_upcoming_hearings

    stats = notify_upcoming_hearings(within_days=7)
    logger.info("Rappels audiences contentieux : %s", stats)
    return stats
