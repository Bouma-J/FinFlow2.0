"""Mise en place crédit via API Perfect (POST …/crd/simple)."""
from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction

from .models import CoreBankingConnector, IntegrationLog
from .services import (
    CoreBankingError,
    OP_SUBMIT_CREDIT,
    _require_success,
    resolve_active_connector,
    send_operation,
)

logger = logging.getLogger("finflow")

DEFAULT_CRD_SIMPLE_PATH = "gateway-perfect/crd/simple"


def _disbursement_rules(connector: CoreBankingConnector) -> dict:
    return (connector.mapping_rules or {}).get("disbursement") or {}


def disbursement_mode(connector: CoreBankingConnector) -> str:
    """
    ``CBS`` (défaut si REST + URL) ou ``LOCAL`` (pas d'appel Perfect).

    Configurable via ``mapping_rules.disbursement.mode``.
    """
    rules = _disbursement_rules(connector)
    mode = str(rules.get("mode") or "").strip().upper()
    if mode in {"CBS", "LOCAL"}:
        return mode
    # Heuristique : sans URL réelle → local (simulation / démo).
    if not (connector.base_url or "").strip():
        return "LOCAL"
    if (connector.mapping_rules or {}).get("force_simulate"):
        return "LOCAL"
    return "CBS"


def requires_financing_object(tenant_id) -> bool:
    """Return whether this branch's active mode requires an exact CBS object."""
    try:
        connector = resolve_active_connector(tenant_id)
    except CoreBankingError:
        # This matches serializer validation: without an active CBS connector,
        # saving a local draft does not require a CBS-only reference.
        return False
    return disbursement_mode(connector) == "CBS"


def build_callback_url(application) -> str:
    base = (
        getattr(settings, "PUBLIC_API_BASE_URL", None)
        or getattr(settings, "FRONTEND_BASE_URL", None)
        or "http://localhost:8000"
    ).rstrip("/")
    # Si FRONTEND_BASE_URL pointe vers Vite, préférer une URL API explicite.
    if base.endswith(":5173"):
        base = base.replace(":5173", ":8000")
    return f"{base}/api/v1/cbs/callbacks/crd/{application.pk}/"


def build_credit_disbursement_payload(application, *, connector=None) -> dict:
    """Construit le corps Perfect ``crd/simple`` à partir du dossier."""
    from .disbursement_payload import build_payload

    return build_payload(application, connector=connector)


def submit_credit_to_cbs(application, *, connector=None) -> dict:
    """
    Envoie la demande de crédit / mise en place au CBS (Perfect crd/simple).

    Retour normalisé :
    {
      mode, external_id, num_demande, ref_demande, num_contrat,
      limit_credit, montant, currency, raw, log_id, external_reference
    }
    """
    connector = connector or resolve_active_connector(application.tenant_id)
    mode = disbursement_mode(connector)
    if not getattr(settings, "ALLOW_SIMULATED_CBS_SETUP", False) and (
        mode != "CBS" or connector.protocol != "REST" or not connector.base_url.strip()
        or (connector.mapping_rules or {}).get("force_simulate")
    ):
        raise CoreBankingError("La mise en place réelle exige un connecteur CBS REST actif avec une URL et une réponse positive. La simulation est réservée aux environnements de développement et de test.")

    if mode == "LOCAL":
        payload = build_credit_disbursement_payload(
            application, connector=connector
        )
        idem = f"disburse:{application.pk}"
        existing = IntegrationLog.all_tenants.filter(
            connector=connector,
            idempotency_key=idem,
            status=IntegrationLog.Status.SUCCESS,
        ).first()
        if existing:
            response = existing.response_payload or {}
            raw = response.get("raw") or response
            return {
                "mode": "LOCAL",
                "external_id": payload["externalId"],
                "num_demande": str(
                    response.get("num_demande") or raw.get("numDemande") or ""
                ),
                "ref_demande": str(
                    response.get("ref_demande") or raw.get("refDemande") or ""
                ),
                "num_contrat": str(
                    response.get("num_contrat")
                    or raw.get("numContrat")
                    or existing.external_reference
                    or ""
                ),
                "limit_credit": response.get("limit_credit") or raw.get("limitCredit"),
                "montant": response.get("montant") or raw.get("montant"),
                "currency": payload["codeDevise"],
                "raw": raw,
                "log_id": str(existing.id),
                "external_reference": existing.external_reference,
                "payload_sent": payload,
            }

        from .services import SimulatedAdapter

        response = SimulatedAdapter(connector).send(OP_SUBMIT_CREDIT, payload)
        log = IntegrationLog.all_tenants.create(
            tenant_id=application.tenant_id,
            connector=connector,
            operation=OP_SUBMIT_CREDIT,
            direction=IntegrationLog.Direction.OUTBOUND,
            idempotency_key=idem,
            request_payload=payload,
            response_payload=response,
            status=IntegrationLog.Status.SUCCESS,
            external_reference=response.get("external_reference") or "",
            attempts=1,
        )
        return {
            "mode": "LOCAL",
            "external_id": payload["externalId"],
            "num_demande": response.get("num_demande") or "",
            "ref_demande": response.get("ref_demande") or "",
            "num_contrat": response.get("num_contrat")
            or response.get("external_reference")
            or "",
            "limit_credit": response.get("limit_credit"),
            "montant": response.get("montant"),
            "currency": payload["codeDevise"],
            "raw": response.get("raw") or response,
            "log_id": str(log.id),
            "external_reference": response.get("external_reference") or "",
            "payload_sent": payload,
        }

    from apps.catalog.cbs_mapping import cbs_mapping_snapshot, lock_application_cbs_mapping

    with transaction.atomic():
        # Le service crédit relâche son verrou dossier avant l'appel réseau.
        # Relire et stabiliser ici les références évite d'envoyer un mapping
        # différent de celui autorisé entre les deux phases.
        application = application.__class__.all_tenants.get(pk=application.pk)
        lock_application_cbs_mapping(application)
        current = cbs_mapping_snapshot(application)
        authorization = application.setup_authorization or {}
        if (authorization.get("status") != "AUTHORIZED"
                or authorization.get("cbs_mapping") != current
                or current["connector_id"] != str(connector.pk)):
            raise CoreBankingError("Les correspondances CBS ne sont pas couvertes par une autorisation à jour. Refaites le contrôle final et l'autorisation.")
        payload = build_credit_disbursement_payload(application, connector=connector)
        idem = f"disburse:{application.pk}"
        log = send_operation(connector, OP_SUBMIT_CREDIT, payload, idempotency_key=idem, authorized_application=application)
    # Un refus CBS reste journalisé : ne pas lever l'erreur dans le bloc qui
    # a persisté le journal de cette tentative.
    response = _require_success(log, OP_SUBMIT_CREDIT)
    raw = response.get("raw") or response
    return {
        "mode": "CBS",
        "external_id": payload["externalId"],
        "num_demande": str(
            response.get("num_demande") or raw.get("numDemande") or ""
        ),
        "ref_demande": str(
            response.get("ref_demande") or raw.get("refDemande") or ""
        ),
        "num_contrat": str(
            response.get("num_contrat")
            or raw.get("numContrat")
            or log.external_reference
            or ""
        ),
        "limit_credit": response.get("limit_credit") or raw.get("limitCredit"),
        "montant": response.get("montant") or raw.get("montant"),
        "currency": payload["codeDevise"],
        "raw": raw,
        "log_id": str(log.id),
        "external_reference": log.external_reference,
        "payload_sent": payload,
    }


def apply_cbs_callback(application_id, body: dict, *, secret: str | None = None):
    """Traite un callback Perfect sur une demande de crédit."""
    from django.db import transaction

    from apps.credits.models import CreditApplication, Loan

    with transaction.atomic():
        app = (
            CreditApplication.all_tenants.select_for_update()
            .filter(pk=application_id)
            .first()
        )
        if app is None:
            raise CoreBankingError("Dossier introuvable pour ce callback CBS.")

        connector = resolve_active_connector(app.tenant_id)
        expected = str(
            (_disbursement_rules(connector).get("callback_secret") or "")
        ).strip()
        # Secret obligatoire : refuse les callbacks anonymes même hors CBS live.
        if not expected:
            raise CoreBankingError(
                "Callback CBS refusé : configurez callback_secret sur le connecteur."
            )
        if not secret or secret != expected:
            raise CoreBankingError("Secret de callback CBS invalide.")

        # États vraiment terminaux : ignorer les replays. DISBURSED reste
        # ouvert aux mises à jour CBS (n° contrat, statut déblocage…).
        hard_terminal = {
            CreditApplication.Status.CLOSED,
            CreditApplication.Status.CANCELLED,
            CreditApplication.Status.REJECTED,
        }
        if app.status in hard_terminal:
            return {
                "application_id": str(app.pk),
                "loan_id": None,
                "ignored": True,
                "detail": f"Dossier déjà en statut {app.status} — callback ignoré.",
            }

        loan = (
            Loan.all_tenants.select_for_update()
            .filter(application_id=app.pk)
            .first()
        )
        status = str(
            body.get("status")
            or body.get("context")
            or body.get("responseCode")
            or "UPDATED"
        )[:40]
        updates = {
            "cbs_disbursement_status": status,
            "cbs_disbursement_payload": body if isinstance(body, dict) else {},
        }
        if body.get("numDemande"):
            updates["cbs_demande_number"] = str(body["numDemande"])[:100]
        if body.get("refDemande"):
            updates["cbs_demande_ref"] = str(body["refDemande"])[:100]
        if body.get("numContrat"):
            updates["cbs_contract_number"] = str(body["numContrat"])[:100]
            updates["core_banking_reference"] = str(body["numContrat"])[:100]

        if loan is not None:
            for k, v in updates.items():
                setattr(loan, k, v)
            loan.save(update_fields=[*updates.keys(), "updated_at"])

        app_updates = {}
        if body.get("numDemande"):
            app_updates["cbs_demande_number"] = str(body["numDemande"])[:100]
        if body.get("refDemande"):
            app_updates["cbs_demande_ref"] = str(body["refDemande"])[:100]
        if body.get("numContrat"):
            app_updates["cbs_contract_number"] = str(body["numContrat"])[:100]
        op_date = None
        raw_date = body.get("dateOperation")
        if raw_date:
            from datetime import date as date_cls

            try:
                op_date = date_cls.fromisoformat(str(raw_date).strip()[:10])
            except ValueError:
                op_date = None
        if op_date is not None:
            app_updates["cbs_operation_date"] = op_date
        if app_updates:
            for k, v in app_updates.items():
                setattr(app, k, v)
            app.save(update_fields=[*app_updates.keys(), "updated_at"])

        loan_id = str(loan.pk) if loan else None

    # Journal INBOUND hors du verrou dossier (échec non bloquant)
    try:
        connector = resolve_active_connector(app.tenant_id)
        IntegrationLog.all_tenants.create(
            tenant_id=app.tenant_id,
            connector=connector,
            operation="CRD_CALLBACK",
            direction=IntegrationLog.Direction.INBOUND,
            request_payload=body if isinstance(body, dict) else {"raw": body},
            response_payload={"application_id": str(app.pk)},
            status=IntegrationLog.Status.SUCCESS,
            external_reference=str(
                body.get("numContrat") or body.get("refDemande") or ""
            )[:100],
            attempts=1,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Échec journalisation callback CBS")

    return {"application_id": str(app.pk), "loan_id": loan_id}
