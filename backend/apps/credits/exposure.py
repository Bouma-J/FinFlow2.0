"""Consolidation par client et relations économiques, sans conversion implicite."""
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from apps.configuration.exposure_catalog import DEFAULT_EXPOSURE
from apps.configuration.services import application_configuration
from .amounts import reference_amount
from .exposure_models import BorrowerGroup, CreditExposureObservation
from .models import CreditApplication, Loan

PENDING_STATUSES = {"SUBMITTED", "IN_APPROVAL", "APPROVED", "CONTRACT_GENERATED", "DISBURSEMENT_PENDING"}


def evidence_matches_client(observation):
    from django.contrib.contenttypes.models import ContentType
    from apps.clients.models import Client
    evidence = observation.evidence
    if evidence.tenant_id != observation.tenant_id:
        return False
    if evidence.content_type_id == ContentType.objects.get_for_model(Client).pk:
        return str(evidence.object_id) == str(observation.client_id)
    if evidence.content_type_id == ContentType.objects.get_for_model(CreditApplication).pk:
        return CreditApplication.all_tenants.filter(pk=evidence.object_id, tenant_id=observation.tenant_id, client_id=observation.client_id).exists()
    return False


def exposure_assessment(application, *, configuration=None):
    config = configuration or application_configuration(application)
    rules = config.get("exposure", {}).get("rules", DEFAULT_EXPOSURE)
    today = timezone.localdate()
    groups = BorrowerGroup.all_tenants.filter(tenant_id=application.tenant_id, is_active=True, clients=application.client_id)
    member_ids = {application.client_id}
    # Union des groupes directement déclarés, sans inventer une contagion transitive.
    for group in groups:
        member_ids.update(group.clients.filter(tenant_id=application.tenant_id).values_list("pk", flat=True))
    from apps.clients.models import Client
    members = Client.all_tenants.filter(tenant_id=application.tenant_id, pk__in=member_ids).order_by("pk")
    currency = rules["currency"] or application.currency
    failures, rows = [], []
    client_total, group_total = None, Decimal("0")
    for member in members:
        observation = CreditExposureObservation.all_tenants.filter(
            tenant_id=application.tenant_id, client=member, currency=currency,
            status__in=["VERIFIED", "REVOKED"], as_of__lte=today,
        ).select_related("evidence").order_by("-as_of", "-verified_at", "-pk").first()
        if observation and (observation.status != "VERIFIED" or not observation.completeness_confirmed):
            # Révoquer la plus récente ne réactive pas une ancienne preuve.
            observation = None
        issues = []
        if observation:
            document = observation.evidence
            if document.is_deleted or not document.file or not evidence_matches_client(observation) or document.verification_status != "VERIFIED" or (document.expiry_date and document.expiry_date < today):
                issues.append("Justificatif absent, non vérifié ou expiré.")
            if Loan.all_tenants.filter(tenant_id=application.tenant_id, application__client=member,
                application__currency=currency).filter(
                    Q(disbursed_at__gt=observation.as_of) | Q(created_at__gt=observation.created_at)
                ).exists():
                issues.append("Une mise en place locale est postérieure à la situation externe : actualisez les engagements pour éviter un sous-décompte.")
            if rules["maximum_age_days"] and (today - observation.as_of).days > rules["maximum_age_days"]:
                issues.append("Situation d'engagements trop ancienne.")
            external_total = observation.drawn_principal + observation.undrawn_commitments + observation.guarantees_given
        else:
            external_total = None
            issues.append("Aucune situation consolidée complète et vérifiée dans la devise du contrôle.")
        pending = Decimal("0")
        incompatible_pending = False
        if rules["include_pending"]:
            applications = CreditApplication.all_tenants.filter(
                tenant_id=application.tenant_id, client=member, status__in=PENDING_STATUSES,
            ).exclude(pk=application.pk)
            for other in applications:
                amount = reference_amount(other) or Decimal("0")
                if other.currency != currency and amount:
                    incompatible_pending = True
                else:
                    pending += amount
        other_pending = pending
        current_application = None
        if member.pk == application.client_id and application.status in PENDING_STATUSES | {"DRAFT", "RETURNED"}:
            if application.currency != currency:
                incompatible_pending = True
            else:
                current_application = reference_amount(application) or Decimal("0")
                pending += current_application
        if incompatible_pending:
            issues.append("Des demandes sont dans une autre devise ; aucune conversion automatique n'est appliquée.")
        total = external_total + pending if external_total is not None and not incompatible_pending else None
        # Le capital initial local est un repère ; il ne représente pas le capital restant dû CBS.
        local_principal = sum(Loan.all_tenants.filter(
            tenant_id=application.tenant_id, application__client=member,
            application__currency=currency, status__in=["ACTIVE", "DEFAULTED"],
        ).values_list("principal", flat=True), Decimal("0"))
        rows.append({
            "client": str(member.pk), "observation": str(observation.pk) if observation else None,
            "as_of": str(observation.as_of) if observation else None,
            "source_reference": observation.source_reference if observation else "",
            "external_total": str(external_total) if external_total is not None else None,
            "pending_total": str(pending), "other_pending_total": str(other_pending),
            "current_application_amount": str(current_application) if current_application is not None else None,
            "total": str(total) if total is not None else None,
            "local_initial_principal": str(local_principal), "issues": issues,
        })
        if member.pk == application.client_id:
            client_total = total
        if total is None or issues:
            group_total = None
        elif group_total is not None:
            group_total += total
        if issues and (rules["require_verified_snapshot"] or rules["group_limit"] is not None or (member.pk == application.client_id and (rules["client_limit"] is not None or rules["use_cbs_client_limit"]))):
            failures.extend(f"Engagements : {message}" for message in issues)
    if rules["enabled"]:
        if application.currency != currency:
            failures.append("La devise du dossier ne correspond pas à la devise des plafonds.")
        for total, limit, label in ((client_total, rules["client_limit"], "client"), (group_total, rules["group_limit"], "groupe lié")):
            if limit is not None and total is not None and total > Decimal(limit):
                failures.append(f"Le plafond {label} est dépassé.")
        if rules["use_cbs_client_limit"]:
            client = application.client
            if client.cbs_credit_limit is None or not client.cbs_synced_at:
                failures.append("Le plafond client CBS daté est indisponible.")
            elif rules["maximum_age_days"] and (today - timezone.localtime(client.cbs_synced_at).date()).days > rules["maximum_age_days"]:
                failures.append("Le plafond client CBS doit être actualisé.")
            elif client_total is not None and client_total > client.cbs_credit_limit:
                failures.append("Le plafond client communiqué par le CBS est dépassé.")
    else:
        failures = []
    return {
        "enabled": rules["enabled"], "gate": rules["gate"], "currency": currency,
        "client_total": str(client_total) if client_total is not None else None,
        "group_total": str(group_total) if group_total is not None else None,
        "has_linked_group": len(member_ids) > 1,
        "client_limit": rules["client_limit"], "group_limit": rules["group_limit"],
        "members": rows, "failures": list(dict.fromkeys(failures)),
        "complete": bool(rows) and all(not row["issues"] for row in rows),
        "note": "Situations externes saisies et vérifiées sur justificatif. Les demandes en circuit s'ajoutent ; le portefeuille local n'est pas ajouté une seconde fois. Les relations sont limitées à la filiale. Aucun taux de conversion n'est présumé.",
    }


def exposure_failures(application, stage):
    result = exposure_assessment(application)
    order = {"SUBMIT": 1, "APPROVE": 2, "SETUP": 3}
    blocking = result["enabled"] and result["gate"] != "ALERT" and order.get(stage, 0) >= order.get(result["gate"], 99)
    return result["failures"] if blocking else []


def assert_exposure(application, stage):
    from apps.workflow.services import WorkflowError
    failures = exposure_failures(application, stage)
    if failures:
        raise WorkflowError(" ".join(failures))
