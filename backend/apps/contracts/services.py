"""Logique métier : statut de contractualisation et blocage de la mise en place."""
from __future__ import annotations


def assert_surety_generation(template, engagement_id) -> None:
    """Un cautionnement se génère depuis l'engagement, pas depuis le dossier."""
    from rest_framework.exceptions import ValidationError

    from .models import ContractCategory

    if (
        getattr(template, "category", "") == ContractCategory.SURETY
        and not engagement_id
    ):
        raise ValidationError(
            {
                "surety_engagement": (
                    "Générez le cautionnement depuis la fiche de la caution, "
                    "pas depuis le dossier."
                )
            }
        )


def required_templates_for(application):
    """Modèles obligatoires (actifs) applicables à un dossier donné."""
    from .models import ContractCategory, ContractTemplate

    templates = ContractTemplate.all_tenants.filter(
        tenant_id=application.tenant_id, is_active=True, is_required=True
    ).exclude(category=ContractCategory.SURETY).select_related("product")
    return [t for t in templates if t.applies_to_application(application)]


def missing_required_contracts(application) -> list[str]:
    """Retourne les intitulés des contrats obligatoires non encore générés."""
    from .models import GeneratedContract
    from apps.credits.instruction_policy import get_instruction_policy

    policy = get_instruction_policy(application.tenant_id, application=application)
    if not policy.require_credit_contracts:
        return []

    contracts = application.generated_contracts.exclude(
            status=GeneratedContract.Status.CANCELLED
        )
    if policy.require_credit_signed_contracts:
        contracts = contracts.filter(status=GeneratedContract.Status.SIGNED).exclude(signed_file="")
    generated_template_ids = set(contracts.values_list("template_id", flat=True))
    return [
        t.name
        for t in required_templates_for(application)
        if t.id not in generated_template_ids
    ]


def missing_surety_signed_contracts(application) -> list[str]:
    """
    Engagements de caution actifs sans contrat de cautionnement signé.

    Un contrat lié à l'engagement (``surety_engagement``) en statut SIGNED
    est exigé. Les contrats SURETY « dossier » non liés à l'engagement ne
    suffisent pas (une caution = un acte).
    """
    from apps.sureties.models import SuretyEngagement

    from .models import GeneratedContract
    from apps.credits.instruction_policy import get_instruction_policy

    policy = get_instruction_policy(application.tenant_id, application=application)
    if not policy.require_surety_contracts:
        return []

    missing: list[str] = []
    engagements = (
        SuretyEngagement.objects.filter(
            application=application,
            status=SuretyEngagement.Status.ACTIVE,
        )
        .select_related("surety")
        .prefetch_related("generated_contracts")
    )
    for eng in engagements:
        gc = eng.active_contract
        label = eng.surety.display_name if eng.surety_id else str(eng.pk)
        if gc is None:
            missing.append(f"Cautionnement — {label} (non généré)")
        elif policy.require_surety_signed_contracts and (gc.status != GeneratedContract.Status.SIGNED or not gc.signed_file):
            missing.append(f"Cautionnement — {label} (non signé)")
    return missing


def refresh_contract_status(application, user=None):
    """Passe le dossier en CONTRACT_GENERATED si tous les contrats requis sont là.

    N'intervient que sur un dossier approuvé (ou déjà en contractualisation),
    afin de ne pas court-circuiter le circuit d'approbation.
    """
    from apps.credits.models import CreditApplication

    from .models import GeneratedContract

    if application.status not in (
        CreditApplication.Status.APPROVED,
        CreditApplication.Status.CONTRACT_GENERATED,
    ):
        return

    has_any = application.generated_contracts.exclude(
        status=GeneratedContract.Status.CANCELLED
    ).exists()

    if has_any and not missing_required_contracts(application):
        if application.status != CreditApplication.Status.CONTRACT_GENERATED:
            application.status = CreditApplication.Status.CONTRACT_GENERATED
            application.save(update_fields=["status", "updated_at"])
