"""Payload Perfect construit exclusivement à partir du résolveur commun."""
from decimal import Decimal

from apps.catalog.cbs_mapping import assert_application_cbs_mapping, lock_application_cbs_mapping
from apps.catalog.cbs_resolve import resolve_currency_cbs, resolve_periodicity_cbs
from .services import CoreBankingError


def external_id(application, *, connector, requires_real):
    """Une référence globale stable ; préserver celle de toute tentative passée."""
    from .models import IntegrationLog

    previous = IntegrationLog.all_tenants.filter(
        connector=connector, tenant_id=application.tenant_id,
        operation="SUBMIT_CREDIT", idempotency_key=f"disburse:{application.pk}",
    ).values_list("request_payload", flat=True).first()
    if isinstance(previous, dict) and str(previous.get("externalId") or "").strip():
        return str(previous["externalId"]).strip()
    # La référence métier est séquentielle par filiale et peut donc déjà
    # exister sur un CBS partagé. L'UUID distingue les nouveaux dossiers.
    return str(application.pk) if requires_real else (application.reference or str(application.pk)).strip()


def build_payload(application, *, connector=None):
    from apps.credits.amounts import reference_amount
    from apps.credits.services import period_count
    from .disbursement import build_callback_url
    from .perfect_defaults import PERIODICITY_CBS

    if application.client is None or application.product is None:
        raise CoreBankingError("Client et produit requis pour la mise en place CBS.")
    lock_application_cbs_mapping(application)
    resolved = assert_application_cbs_mapping(application, connector=connector)
    values = dict(resolved["values"])
    if not resolved["requires_real"]:
        # Compatibilité réservée aux connecteurs explicitement simulés/locaux.
        if not values["idPeriodicite"]:
            values["idPeriodicite"] = resolve_periodicity_cbs(application.tenant_id, application.periodicity or "MONTHLY", fallback_map=PERIODICITY_CBS)
        if not values["codeDevise"]:
            values["codeDevise"] = resolve_currency_cbs(application.tenant_id, application.currency)
    if not any(values.get(key) for key in ("codeAdherent", "numManuel", "numPieceIdentite")):
        raise CoreBankingError("Identifiant adhérent CBS, compte ou pièce d'identité requis.")
    # La simulation autorise les correspondances historiques, mais un message
    # incomplet doit échouer avant d'être journalisé comme une mise en place.
    for key in ("idPointService", "idGestionnaire", "idProduitCrd", "idProduitRemb", "idPeriodicite", "codeDevise"):
        if not str(values.get(key) or "").strip():
            raise CoreBankingError(f"Correspondance CBS requise : {key}.")
    amount = reference_amount(application) or application.amount_requested
    rate = application.interest_rate
    if rate is None:
        rate = application.product.interest_rate
    if amount is None or rate is None:
        raise CoreBankingError("Montant et taux approuvés requis pour la mise en place CBS.")
    return {
        "externalId": external_id(application, connector=resolved["connector_id"], requires_real=resolved["requires_real"]),
        "callbackUrl": build_callback_url(application),
        **{k: v for k, v in values.items() if k not in {"codeAdherent", "numManuel", "numPieceIdentite"} or v},
        "taux": float(Decimal(rate)),
        "nombreEcheance": int(period_count(application.duration_months or 1, application.periodicity or "MONTHLY", tenant_id=application.tenant_id)),
        "montantDemande": float(Decimal(amount)),
    }
