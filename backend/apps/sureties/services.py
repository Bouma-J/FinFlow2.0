"""Services métier — engagements de caution et contrats de cautionnement."""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.contracts.context import build_context
from apps.contracts.models import ContractCategory, ContractTemplate, GeneratedContract
from apps.contracts.rendering import ContractRenderError, render_template
from apps.contracts.services import refresh_contract_status

from .models import SuretyEngagement


def release_engagement(
    engagement: SuretyEngagement, *, user=None, comment: str = ""
) -> SuretyEngagement:
    if engagement.status == SuretyEngagement.Status.RELEASED:
        raise ValidationError("Cet engagement est déjà libéré.")
    engagement.status = SuretyEngagement.Status.RELEASED
    engagement.released_at = timezone.now()
    if comment:
        engagement.notes = (
            f"{engagement.notes}\n{comment}".strip()
            if engagement.notes
            else comment
        )
    engagement.save(update_fields=["status", "released_at", "notes", "updated_at"])
    return engagement


def call_engagement(
    engagement: SuretyEngagement, *, user=None, comment: str = ""
) -> SuretyEngagement:
    if engagement.status == SuretyEngagement.Status.RELEASED:
        raise ValidationError("Impossible d'appeler une caution déjà libérée.")
    if engagement.status == SuretyEngagement.Status.CALLED:
        raise ValidationError("Cet engagement est déjà en appel.")
    engagement.status = SuretyEngagement.Status.CALLED
    engagement.called_at = timezone.now()
    if comment:
        engagement.notes = (
            f"{engagement.notes}\n{comment}".strip()
            if engagement.notes
            else comment
        )
    engagement.save(update_fields=["status", "called_at", "notes", "updated_at"])
    return engagement


def _pick_surety_template(application, template_id: str | None = None) -> ContractTemplate:
    qs = ContractTemplate.objects.filter(is_active=True)
    if template_id:
        try:
            tpl = qs.get(id=template_id)
        except (ContractTemplate.DoesNotExist, ValueError, TypeError):
            raise ValidationError({"template": "Modèle introuvable."})
        if not tpl.applies_to_application(application):
            raise ValidationError(
                {"template": "Ce modèle ne s'applique pas à ce dossier."}
            )
        return tpl

    surety_tpls = [
        t
        for t in qs.filter(category=ContractCategory.SURETY).order_by(
            "ordering", "name"
        )
        if t.applies_to_application(application)
    ]
    if not surety_tpls:
        raise ValidationError(
            "Aucun modèle de contrat de cautionnement (catégorie SURETY) "
            "actif pour ce dossier. Créez-en un dans Administration → Contrats."
        )
    return surety_tpls[0]


@transaction.atomic
def generate_engagement_contract(
    engagement: SuretyEngagement,
    *,
    user,
    template_id: str | None = None,
    extra_values: dict | None = None,
) -> GeneratedContract:
    """Génère (ou régénère) le contrat de cautionnement lié à un engagement."""
    application = engagement.application
    template = _pick_surety_template(application, template_id)
    extra_values = extra_values or {}
    context = build_context(
        application,
        extra_values,
        primary_engagement=engagement,
    )

    try:
        rendered = render_template(template, context)
    except ContractRenderError as exc:
        raise ValidationError({"detail": str(exc)}) from exc

    # Annuler l'ancien contrat actif de cet engagement (même modèle).
    GeneratedContract.objects.filter(
        surety_engagement=engagement,
        template=template,
    ).exclude(status=GeneratedContract.Status.CANCELLED).update(
        status=GeneratedContract.Status.CANCELLED
    )

    gc = GeneratedContract(
        tenant_id=application.tenant_id,
        application=application,
        template=template,
        template_name=template.name,
        category=template.category or ContractCategory.SURETY,
        surety_engagement=engagement,
        context_snapshot=context,
        extra_values=extra_values,
        created_by=user,
        updated_by=user,
    )
    gc.file.save(rendered.name, rendered, save=False)
    gc.save()
    refresh_contract_status(application, user)
    return gc


@transaction.atomic
def upload_engagement_signed_contract(
    engagement: SuretyEngagement,
    *,
    signed_file,
    user,
    notes: str = "",
) -> GeneratedContract:
    gc = engagement.active_contract
    if gc is None or gc.status == GeneratedContract.Status.CANCELLED:
        raise ValidationError(
            "Générez d'abord le contrat de cautionnement avant de déposer "
            "le scan signé."
        )
    gc.signed_file = signed_file
    if notes:
        gc.notes = notes
    gc.status = GeneratedContract.Status.SIGNED
    gc.signed_at = timezone.now()
    gc.updated_by = user
    gc.save()
    if not engagement.signed_date:
        engagement.signed_date = timezone.localdate()
        engagement.save(update_fields=["signed_date"])
    return gc
