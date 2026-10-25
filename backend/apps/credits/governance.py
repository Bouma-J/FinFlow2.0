"""Preuves de décision et contrôles de mise en place dans le CBS."""
import hashlib
import json
from datetime import date

from django.core.serializers.json import DjangoJSONEncoder
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from apps.workflow.services import WorkflowError


def plain(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True))


def snapshot(application):
    from apps.documents.models import Document

    ct = ContentType.objects.get_for_model(application)
    reference = application.financial_analyses.filter(is_reference=True).first()
    application_data = application.__class__.all_tenants.filter(pk=application.pk).values().get()
    application_data.pop("approval_snapshot", None)
    application_data.pop("setup_review", None)
    application_data.pop("setup_authorization", None)
    result = {
        "captured_at": timezone.now(),
        "application": application_data,
        "client": application.client.__class__.all_tenants.filter(pk=application.client_id).values(
            "id", "reference", "client_type", "first_name", "last_name", "company_name",
            "kyc_status", "kyc_validated_at", "id_document_expiry_date",
        ).get(),
        "analysis": reference.__class__.all_tenants.filter(pk=reference.pk).values().get() if reference else None,
        "analysis_documents": list(reference.documents.values("id", "file", "label")) if reference else [],
        "credit_documents": list(application.documents.values("id", "file", "label")),
        "documents": list(Document.all_tenants.filter(content_type=ct, object_id=application.pk).values("id", "name", "sha256", "version", "verification_status", "expiry_date")),
        "guarantees": list(application.guarantees.values()),
        "sureties": list(application.surety_engagements.values()),
        "contracts": list(application.generated_contracts.values("id", "template_name", "status", "signed_at", "signed_file", "file", "context_snapshot")),
    }
    if (application.configuration_snapshot or {}).get("schema_version", 1) >= 2:
        from .eligibility import assess_rules

        result["rules_evaluation"] = assess_rules(application)
    if (application.configuration_snapshot or {}).get("schema_version", 1) >= 3:
        from .pricing import quote_pricing
        result["pricing_quote"] = quote_pricing(application)
    if (application.configuration_snapshot or {}).get("exposure", {}).get("rules", {}).get("enabled"):
        from .exposure import exposure_assessment
        result["exposure"] = exposure_assessment(application)
    if "kyc" in (application.configuration_snapshot or {}):
        from apps.clients.models import Client
        from apps.clients.compliance import kyc_evidence
        result["kyc_evidence"] = kyc_evidence(application.client, application.configuration_snapshot)
        result["kyc_evidence"]["documents"] = list(Document.all_tenants.filter(tenant_id=application.tenant_id,
                content_type=ContentType.objects.get_for_model(Client), object_id=application.client_id,
            ).order_by("id").values("id", "sha256", "version", "verification_status", "expiry_date"))
    return plain(result)


def fingerprint(application):
    # Les preuves de signature et formalisation peuvent être complétées après
    # accord ; les termes financiers approuvés doivent rester identiques.
    from .amounts import reference_amount

    # Les DecimalField sont normalisés à la relecture en base (10 devient
    # 10.000). Toujours comparer les valeurs persistées, jamais leur type
    # Python temporaire au moment de la sauvegarde.
    application = application.__class__.all_tenants.get(pk=application.pk)

    data = {name: getattr(application, name) for name in (
        "client_id", "product_id", "duration_months", "interest_rate", "currency",
        "periodicity", "repayment_mechanism", "first_due_date", "fees_rate",
        "mandatory_savings_rate", "personal_contribution", "has_credit_insurance",
    )}
    data["amount"] = reference_amount(application)
    if application.financing_object_id:
        data["financing_object_id"] = str(application.financing_object_id)
    data["extra_fees"] = list(application.extra_fees.order_by("sort_order", "id").values("id", "label", "mode", "value"))
    if (application.configuration_snapshot or {}).get("schema_version", 1) >= 3:
        from .pricing import quote_pricing
        data["pricing_quote"] = quote_pricing(application)
    reference = application.financial_analyses.filter(is_reference=True).first()
    if reference:
        data["analysis"] = reference.__class__.all_tenants.filter(pk=reference.pk).values().get()
        for key in ("updated_at", "created_at", "new_installment", "repayment_capacity", "debt_ratio", "dscr", "debt_ratio_stress", "dscr_stress", "guarantee_coverage", "internal_score", "score_breakdown"):
            data["analysis"].pop(key, None)
        if "forms" not in (application.configuration_snapshot or {}):
            data["analysis"].pop("custom_fields", None)
    return hashlib.sha256(json.dumps(plain(data), sort_keys=True).encode()).hexdigest()


def freeze_approval(application):
    application.approval_snapshot = snapshot(application)
    # Évite l'imbrication des photographies précédentes.
    application.approval_snapshot["application"].pop("approval_snapshot", None)
    application.approval_snapshot["application"].pop("setup_review", None)
    application.approval_fingerprint = fingerprint(application)
    application.setup_review = {}
    application.setup_authorization = {}
    application.save(update_fields=["approval_snapshot", "approval_fingerprint", "setup_review", "setup_authorization", "updated_at"])


def verified_checklist(application):
    """Exige des documents GED réels, vérifiés, non expirés et de la filiale."""
    from apps.documents.models import Document
    from apps.catalog.models import ChecklistItem

    ct = ContentType.objects.get_for_model(application)
    documents = Document.all_tenants.filter(
        tenant_id=application.tenant_id, content_type=ct, object_id=application.pk,
        verification_status="VERIFIED", is_deleted=False,
    ).exclude(file="")
    documents = documents.filter(expiry_date__isnull=True) | documents.filter(expiry_date__gte=date.today())
    matched = {str(d.category.code).casefold() for d in documents.select_related("category")}
    matched.update(str(d.category.label).casefold() for d in documents.select_related("category"))
    matched.update(str(d.name).casefold() for d in documents)
    missing = [item.label for item in ChecklistItem.objects.filter(product=application.product, is_mandatory=True)
               if item.label.strip().casefold() not in matched]
    return missing


def setup_checks(application):
    from .instruction_policy import get_instruction_policy
    from .eligibility import assess_rules, rule_failures

    policy = get_instruction_policy(application.tenant_id, application=application)
    failures = rule_failures(assess_rules(application), "SETUP")
    from apps.catalog.cbs_mapping import resolve_application_cbs

    cbs = resolve_application_cbs(application)
    if cbs["requires_real"] or not cbs["connector_id"]:
        failures += [f"{e['field']} : {e['message']}" for e in cbs["errors"]]
    from .exposure import exposure_failures
    failures += exposure_failures(application, "SETUP")
    if policy.recheck_kyc_on_setup:
        from apps.clients.compliance import kyc_failures
        failures += kyc_failures(application.client, application=application)
    from .pricing import quote_pricing
    failures += quote_pricing(application)["failures"]
    if policy.recheck_kyc_on_setup and application.client.kyc_status != "VALIDATED":
        failures.append("Le KYC doit être valide au moment de la mise en place.")
    if policy.recheck_kyc_on_setup and application.client.id_document_expiry_date and application.client.id_document_expiry_date < date.today():
        failures.append("La pièce d'identité du client est expirée : actualisez le KYC.")
    if policy.approval_validity_days:
        if not application.decision_date:
            failures.append("La date de décision est requise pour contrôler la validité de l'accord.")
        elif (date.today() - application.decision_date).days > policy.approval_validity_days:
            failures.append("L'accord a expiré : une nouvelle décision est nécessaire.")
    if application.approval_fingerprint and fingerprint(application) != application.approval_fingerprint:
        failures.append("Les conditions financières ont changé depuis l'accord : réexaminer le dossier.")
    current_guarantees = {str(row["id"]): row for row in application.guarantees.values()}
    for original in (application.approval_snapshot or {}).get("guarantees", []):
        if original.get("status") != "ACTIVE":
            continue
        current = current_guarantees.get(str(original["id"]))
        if not current or current.get("status") != "ACTIVE":
            failures.append("Une garantie de l'accord n'est plus active : réexaminer le dossier.")
            break
        from decimal import Decimal
        if Decimal(str(current.get("current_value") or 0)) < Decimal(str(original.get("current_value") or 0)):
            failures.append("La valeur d'une garantie de l'accord a diminué : réexaminer le dossier.")
            break
    current_sureties = {str(row["id"]): row for row in application.surety_engagements.values()}
    for original in (application.approval_snapshot or {}).get("sureties", []):
        if original.get("status") != "ACTIVE":
            continue
        current = current_sureties.get(str(original["id"]))
        from decimal import Decimal

        if (
            not current
            or current.get("status") != "ACTIVE"
            or str(current.get("surety_id")) != str(original.get("surety_id"))
            or Decimal(str(current.get("amount") or 0)) < Decimal(str(original.get("amount") or 0))
        ):
            failures.append("Un engagement de caution de l'accord a été retiré, remplacé ou réduit : réexaminer le dossier.")
            break
    if policy.max_analysis_age_days:
        ref = application.financial_analyses.filter(is_reference=True).first()
        if ref is None or ref.analysis_date is None or (date.today() - ref.analysis_date).days > policy.max_analysis_age_days:
            failures.append("L'analyse financière doit être actualisée.")
    if application.has_credit_insurance:
        if application.insurance_expiry_date and application.insurance_expiry_date < date.today():
            failures.append("La couverture d'assurance est expirée.")
        if not application.insurance_policy_number or not application.insurance_expiry_date:
            failures.append("Renseignez le numéro de police et la fin de couverture d'assurance.")
    if policy.require_verified_documents:
        missing = verified_checklist(application)
        if missing:
            failures.append("Pièces vérifiées manquantes ou expirées : " + ", ".join(missing))
    return failures


def assert_setup_review(application):
    failures = setup_checks(application)
    if failures:
        raise WorkflowError(" ".join(failures))
    from .setup_authorization import review_is_current

    if not review_is_current(application):
        raise WorkflowError("L'administrateur crédit doit valider le contrôle final à jour avant l'autorisation de mise en place.")


def evidence_fingerprint(application):
    data = snapshot(application)
    evidence = {key: data[key] for key in ("documents", "analysis_documents", "credit_documents", "guarantees", "sureties", "contracts")}
    # Une liste relationnelle peut être lue dans un ordre différent sans
    # changement métier : le tri rend l'empreinte indépendante de cet ordre.
    for rows in evidence.values():
        rows.sort(key=lambda row: str(row["id"]))
    evidence["insurance"] = {"policy": application.insurance_policy_number, "expiry": str(application.insurance_expiry_date or "")}
    evidence["client"] = data["client"]
    if "rules_evaluation" in data:
        evidence["rules_evaluation"] = data["rules_evaluation"]
    if "pricing_quote" in data:
        evidence["pricing_quote"] = data["pricing_quote"]
    if "exposure" in data:
        evidence["exposure"] = data["exposure"]
    if "kyc_evidence" in data:
        evidence["kyc_evidence"] = data["kyc_evidence"]
    return hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
