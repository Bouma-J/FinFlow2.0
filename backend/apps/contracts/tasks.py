"""Tâches Celery — génération de contrats."""
import logging

from celery import shared_task
from django.db import transaction

from apps.common.tenancy import tenant_context

logger = logging.getLogger("finflow")


@shared_task(bind=True, ignore_result=False, soft_time_limit=240, time_limit=300)
def generate_contract_task(
    self,
    application_id: str,
    template_id: str,
    user_id: str,
    extra_values: dict | None = None,
    tenant_id: str | None = None,
    surety_engagement_id: str | None = None,
):
    """Génère un contrat hors requête HTTP."""
    from apps.accounts.models import User
    from apps.contracts.context import build_context
    from apps.contracts.models import ContractTemplate, GeneratedContract
    from apps.contracts.rendering import ContractRenderError, render_template
    from apps.contracts.services import refresh_contract_status
    from apps.credits.models import CreditApplication

    extra_values = extra_values or {}
    with tenant_context(tenant_id):
        try:
            application = CreditApplication.all_tenants.select_related(
                "client", "client__agency", "product", "agency", "tenant"
            ).prefetch_related("client__phones").get(pk=application_id)
            template = ContractTemplate.all_tenants.get(pk=template_id)
            user = User.objects.get(pk=user_id)
            from apps.contracts.services import assert_surety_generation

            assert_surety_generation(template, surety_engagement_id)
        except Exception:
            logger.exception("generate_contract_task : entité introuvable")
            raise

        primary_engagement = None
        if surety_engagement_id:
            from apps.sureties.models import SuretyEngagement

            try:
                primary_engagement = SuretyEngagement.all_tenants.select_related(
                    "surety"
                ).get(pk=surety_engagement_id, application_id=application_id)
            except SuretyEngagement.DoesNotExist:
                logger.exception(
                    "generate_contract_task : engagement %s introuvable",
                    surety_engagement_id,
                )
                raise

        context = build_context(
            application,
            extra_values,
            primary_engagement=primary_engagement,
        )
        try:
            rendered = render_template(template, context)
        except ContractRenderError:
            logger.exception("Échec rendu contrat app=%s", application_id)
            raise

        with transaction.atomic():
            cancel_qs = application.generated_contracts.filter(
                template=template
            ).exclude(status=GeneratedContract.Status.CANCELLED)
            if primary_engagement is not None:
                cancel_qs = cancel_qs.filter(
                    surety_engagement=primary_engagement
                )
            cancel_qs.update(status=GeneratedContract.Status.CANCELLED)
            gc = GeneratedContract(
                application=application,
                template=template,
                template_name=template.name,
                category=template.category,
                surety_engagement=primary_engagement,
                context_snapshot=context,
                extra_values=extra_values,
                created_by=user,
                updated_by=user,
                tenant_id=application.tenant_id,
            )
            gc.file.save(rendered.name, rendered, save=False)
            gc.save()
            refresh_contract_status(application, user)
        return str(gc.id)
