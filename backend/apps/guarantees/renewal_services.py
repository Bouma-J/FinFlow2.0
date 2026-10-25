"""Reconduction de garanties sur un dossier de crédit (renouvellement)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.credits.models import CreditApplication

from .models import (
    Guarantee,
    GuaranteeJewelryItem,
    GuaranteeMovement,
)


class RenewalError(Exception):
    pass


# Champs copiés tels quels lors d'une reconduction (hors fichiers lourds).
_COPY_FIELDS = [
    "guarantee_type",
    "pledge_category",
    "description",
    "owners",
    "expertise_value",
    "current_value",
    "is_insured",
    "insurance_reference",
    "owner_last_name",
    "owner_first_name",
    "owner_marital_status",
    "matrimonial_regime",
    "document_type",
    "document_number",
    "document_issue_date",
    "document_validity_date",
    "address",
    "expertise_date",
    "expertise_firm",
    "expert_name",
    "expertise_reference",
    "value_to_consider",
    "occupancy_status",
    "chassis_number",
    "engine_number",
    "brand",
    "model_name",
    "registration",
    "power",
    "first_registration_year",
    "acquisition_date",
    "acquisition_value",
    "resale_value",
    "estimation_date",
    "additional_info",
    "raw_material_price",
    "financial_type",
    "account_number",
    "balance",
    "remuneration_rate",
    "deposit_maturity_date",
    "isin_code",
    "volatility_history",
    "security_discount",
    "latitude",
    "longitude",
    "last_valuation_date",
    "agency_id",
]

# Fichiers : on reprend la référence (même fichier stocké).
_COPY_FILE_FIELDS = [
    "document_scan",
    "expertise_report_scan",
    "lease_contract_scan",
    "legal_situation_certificate_scan",
    "registration_card_scan",
    "mechanical_expertise_scan",
    "technical_inspection_scan",
    "insurance_scan",
    "purchase_invoice_scan",
    "expertise_certificate_scan",
    "origin_certificate_scan",
    "pledge_deed_scan",
]

def renewable_guarantees_for_application(application: CreditApplication):
    """
    Détection automatique des garanties reconductibles pour un dossier.

    Critères :
    - même client ;
    - statut ACTIVE ;
    - pas de main levée en cours ;
    - pas déjà rattachée au dossier courant ;
    - pas déjà reconduite sur le dossier courant ;
    - issue d'un autre dossier du client (ou sans dossier) — typiquement
      un crédit précédent.
    """
    already_renewed_ids = set(
        Guarantee.objects.filter(
            application=application,
            renewed_from__isnull=False,
        ).values_list("renewed_from_id", flat=True)
    )
    from .busy import busy_map

    candidate_ids = list(
        Guarantee.objects.filter(
            client_id=application.client_id,
            status=Guarantee.Status.ACTIVE,
        )
        .exclude(application_id=application.pk)
        .exclude(id__in=already_renewed_ids)
        .values_list("id", flat=True)
    )
    blocked_by_process = set(busy_map(candidate_ids).keys())

    qs = (
        Guarantee.objects.filter(
            client_id=application.client_id,
            status=Guarantee.Status.ACTIVE,
        )
        .exclude(application_id=application.pk)
        .exclude(id__in=already_renewed_ids)
        .exclude(id__in=blocked_by_process)
        .filter(
            Q(application__isnull=True)
            | Q(
                application__client_id=application.client_id,
            )
            & ~Q(application_id=application.pk)
        )
        .select_related("application")
        .order_by("-created_at")
        .distinct()
    )
    return qs


def _next_reference(tenant_id) -> str:
    from apps.tenants.models import Tenant

    today = timezone.now().strftime("%Y%m%d")
    with transaction.atomic():
        Tenant.objects.select_for_update().filter(pk=tenant_id).first()
        count = (
            Guarantee.all_tenants.filter(
                tenant_id=tenant_id, created_at__date=date.today()
            ).count()
            + 1
        )
        return f"GAR-R-{today}-{count:04d}"


@transaction.atomic
def renew_guarantee(
    *,
    source: Guarantee,
    application: CreditApplication,
    user,
    revaluate: bool = False,
    valuation: dict | None = None,
    comment: str = "",
) -> Guarantee:
    """
    Crée une nouvelle garantie liée à `source` et rattachée au dossier cible.

    - revaluate=False : copie des valeurs actuelles
    - revaluate=True  : applique les champs fournis dans `valuation`
    """
    if source.client_id != application.client_id:
        raise RenewalError(
            "La garantie n'appartient pas au client de ce dossier."
        )
    if str(source.tenant_id) != str(application.tenant_id):
        raise RenewalError(
            "La garantie n'appartient pas à la même filiale que le dossier."
        )
    if source.status != Guarantee.Status.ACTIVE:
        raise RenewalError(
            "Seule une garantie active (sans main levée) peut être reconduite."
        )
    from .busy import guarantee_busy

    busy = guarantee_busy(source)
    if busy:
        raise RenewalError(
            f"Impossible de reconduire : {busy['label'].lower()} sur cette garantie."
        )
    if Guarantee.objects.filter(
        application=application, renewed_from=source
    ).exists():
        raise RenewalError(
            "Cette garantie a déjà été reconduite sur ce dossier."
        )

    clone = Guarantee(
        tenant_id=application.tenant_id,
        client_id=application.client_id,
        application=application,
        renewed_from=source,
        status=Guarantee.Status.ACTIVE,
        created_by=user,
        updated_by=user,
    )
    for name in _COPY_FIELDS:
        setattr(clone, name, getattr(source, name))
    for name in _COPY_FILE_FIELDS:
        setattr(clone, name, getattr(source, name))

    valuation = valuation or {}
    if revaluate:
        decimal_fields = {
            "expertise_value",
            "current_value",
            "value_to_consider",
            "resale_value",
            "balance",
            "raw_material_price",
        }
        date_fields = {
            "expertise_date",
            "estimation_date",
            "last_valuation_date",
        }
        text_fields = {"expertise_firm", "expert_name"}
        allowed = decimal_fields | date_fields | text_fields
        for key, value in valuation.items():
            if key not in allowed or value in (None, ""):
                continue
            if key in decimal_fields:
                try:
                    value = Decimal(str(value))
                except (InvalidOperation, TypeError) as exc:
                    raise RenewalError(
                        f"Valeur numérique invalide pour « {key} »."
                    ) from exc
            elif key in date_fields:
                if isinstance(value, datetime):
                    value = value.date()
                elif isinstance(value, str):
                    try:
                        value = date.fromisoformat(value[:10])
                    except ValueError as exc:
                        raise RenewalError(
                            f"Date invalide pour « {key} »."
                        ) from exc
                elif not isinstance(value, date):
                    raise RenewalError(f"Date invalide pour « {key} ».")
            setattr(clone, key, value)
        if not clone.last_valuation_date:
            clone.last_valuation_date = timezone.now().date()

    from .uniqueness import uniqueness_error

    conflict = uniqueness_error(
        guarantee_type=clone.guarantee_type,
        pledge_category=getattr(clone, "pledge_category", "") or "",
        document_type=getattr(clone, "document_type", "") or "",
        document_number=getattr(clone, "document_number", "") or "",
        chassis_number=getattr(clone, "chassis_number", "") or "",
        exclude_id=source.pk,
        tenant_id=application.tenant_id,
    )
    if conflict:
        details = conflict.get("already_taken") or {}
        raise RenewalError(
            details.get("message")
            or "Ce bien est déjà pris en garantie active."
        )

    clone.reference = _next_reference(application.tenant_id)
    clone.save()

    for item in source.jewelry_items.all():
        GuaranteeJewelryItem.objects.create(
            tenant_id=clone.tenant_id,
            guarantee=clone,
            nature=item.nature,
            weight=item.weight,
            description=item.description,
        )

    mode_label = "avec réévaluation" if revaluate else "à l'identique"
    note = comment.strip() or (
        f"Reconduction {mode_label} depuis {source.reference or source.pk}"
    )
    GuaranteeMovement.objects.create(
        tenant_id=clone.tenant_id,
        guarantee=clone,
        movement_type=GuaranteeMovement.MovementType.RENEWAL,
        movement_date=timezone.now().date(),
        value=clone.current_value,
        target_application=application,
        comment=note,
    )
    GuaranteeMovement.objects.create(
        tenant_id=source.tenant_id,
        guarantee=source,
        movement_type=GuaranteeMovement.MovementType.RENEWAL,
        movement_date=timezone.now().date(),
        value=source.current_value,
        target_application=application,
        comment=f"Origine d'une reconduction vers {clone.reference}",
    )
    return clone
