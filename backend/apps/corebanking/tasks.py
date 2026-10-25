"""Tâches Celery — Core Banking (rejeux)."""
import logging

from celery import shared_task

logger = logging.getLogger("finflow")


@shared_task(
    ignore_result=True,
    soft_time_limit=1800,
    time_limit=1860,
)
def import_cbs_portfolio_task(
    tenant_id: str, connector_id: str = "", loan_refs=None
):
    """Importe les crédits CBS existants et constitue les dossiers recouvrement."""
    from apps.common.tenancy import tenant_context
    from apps.corebanking.models import CoreBankingConnector
    from apps.corebanking.portfolio_import import import_cbs_portfolio

    try:
        with tenant_context(tenant_id):
            connector = None
            if connector_id:
                connector = CoreBankingConnector.objects.filter(
                    pk=connector_id
                ).first()
            stats = import_cbs_portfolio(
                tenant_id, connector=connector, loan_refs=loan_refs
            )
            if connector is not None:
                rules = dict(connector.mapping_rules or {})
                rules.pop("portfolio_import_error", None)
                connector.mapping_rules = rules
                connector.save(update_fields=["mapping_rules", "updated_at"])
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Import portefeuille CBS filiale %s échoué", tenant_id
        )
        try:
            with tenant_context(tenant_id):
                failed = None
                if connector_id:
                    failed = CoreBankingConnector.objects.filter(
                        pk=connector_id
                    ).first()
                if failed is not None:
                    rules = dict(failed.mapping_rules or {})
                    rules["portfolio_import_error"] = str(exc)[:240]
                    failed.mapping_rules = rules
                    failed.save(update_fields=["mapping_rules", "updated_at"])
        except Exception:  # noqa: BLE001
            logger.exception(
                "Impossible d'enregistrer l'échec d'import CBS filiale %s",
                tenant_id,
            )
        return {
            "errors": [
                {
                    "error": (
                        "Import CBS interrompu : connecteur indisponible "
                        "ou réponse invalide."
                    )
                }
            ]
        }
    logger.info("Import portefeuille CBS filiale %s : %s", tenant_id, stats)
    return stats


@shared_task(ignore_result=True, soft_time_limit=600, time_limit=660)
def retry_cbs_integrations(limit: int = 50):
    """Rejoue les opérations CBS marquées RETRY."""
    from apps.corebanking.models import IntegrationLog
    from apps.corebanking.services import send_operation

    logs = list(
        IntegrationLog.all_tenants.filter(status=IntegrationLog.Status.RETRY)
        .exclude(operation="SUBMIT_CREDIT")
        .select_related("connector")
        .order_by("created_at")[:limit]
    )
    done = 0
    for log in logs:
        try:
            send_operation(
                log.connector,
                log.operation,
                log.request_payload or {},
                log.idempotency_key or "",
            )
            done += 1
        except Exception:  # noqa: BLE001
            logger.exception("Échec retry CBS log=%s", log.id)
    logger.info("CBS retry : %s opérations rejouées", done)
    return done
