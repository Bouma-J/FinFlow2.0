"""Résolution déterministe et conservation des règles d'un dossier."""
import hashlib
import json
from copy import deepcopy

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q
from django.utils import timezone

from apps.credits.models import AnalysisThreshold, CreditInstructionPolicy

from .catalog import ANALYSIS_FIELDS, DETAIL_LABELS, OPERATIONAL_POLICY_KEYS, model_values
from .models import ConfigurationProfile
from .rule_catalog import rule_defaults
from .pricing_catalog import pricing_defaults
from .forms_catalog import form_defaults, validate_custom_values, protect_required_sections
from .exposure_catalog import DEFAULT_EXPOSURE
from .simulation_catalog import simulation_defaults, resolve_simulation

SECTIONS = ("policy", "thresholds", "analysis", "eligibility", "scoring", "pricing", "forms", "kyc", "references", "exposure", "simulation")


def plain(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True))


def digest(value):
    return hashlib.sha256(json.dumps(plain(value), sort_keys=True).encode()).hexdigest()


def context_for(application, individual_profile=None):
    profile = individual_profile
    if profile is None and getattr(application, "pk", None):
        reference = (application.financial_analyses.filter(is_reference=True).first()
                     or application.financial_analyses.order_by("-created_at").first())
        profile = reference.individual_profile if reference else ""
    return {
        "product": str(getattr(getattr(application, "product", None), "pk", "") or ""),
        "agency": str(getattr(application, "agency_id", "") or ""),
        "client_type": getattr(getattr(application, "client", None), "client_type", "") or "",
        "individual_profile": profile or "",
    }


def scope(profile):
    return (str(profile.product_id or ""), str(profile.agency_id or ""),
            profile.client_type, profile.individual_profile)


def specificity(profile):
    # Produit > profil particulier > type de client > agence.
    return (8 if profile.product_id else 0) + (4 if profile.individual_profile else 0) + (
        2 if profile.client_type else 0) + (1 if profile.agency_id else 0)


def matches(profile, context):
    return all(not expected or expected == context.get(key, "") for key, expected in zip(
        ("product", "agency", "client_type", "individual_profile"), scope(profile)
    ))


def active_profiles(tenant_id, *, at=None):
    now = at or timezone.now()
    candidates = ConfigurationProfile.all_tenants.filter(
        tenant_id=tenant_id, status__in=["PUBLISHED", "RETIRED"],
    ).filter(Q(effective_from__lte=now) | Q(status="RETIRED", retired_at__lte=now)).order_by("code", "-effective_from", "-version")
    latest = {}
    for profile in candidates:
        latest.setdefault(profile.code, profile)
    # Un retrait ne réactive jamais silencieusement une ancienne version.
    return [profile for profile in latest.values()
            if profile.status == "PUBLISHED" or (profile.retired_at and profile.retired_at > now)]


def resolve_context(tenant_id, context, *, at=None, candidate=None, resolve_conventions=True):
    from apps.catalog.models import CreditProduct

    product = CreditProduct.all_tenants.filter(tenant_id=tenant_id, pk=context["product"]).first() if context.get("product") else None
    policy = CreditInstructionPolicy.for_tenant(tenant_id)
    thresholds = AnalysisThreshold.for_tenant(tenant_id)
    result = {
        "schema_version": 3, "context": context,
        "policy": plain(model_values(policy)), "thresholds": plain(model_values(thresholds)),
        "analysis": {"required_fields": [], "required_detail_tables": [], "minimum_bank_statement_months": 0},
        "sources": [], "origins": {}, "frozen": False,
        **rule_defaults(),
        **form_defaults(),
        "exposure": {"rules": deepcopy(DEFAULT_EXPOSURE)},
        "simulation": simulation_defaults(),
        "pricing": pricing_defaults(product),
    }
    result["policy"]["require_final_review"] = True
    for section in SECTIONS:
        result["origins"][section] = {key: "Politique filiale" for key in result[section]}
    result["origins"]["pricing"]["product_defaults"] = "Conditions du produit à la résolution"
    result["origins"]["pricing"]["tariff"] = "Tarification existante"
    group_profiles = active_profiles(None, at=at)
    profiles = active_profiles(tenant_id, at=at) if tenant_id else []
    if candidate is not None:
        target = group_profiles if candidate.tenant_id is None else profiles
        target[:] = [profile for profile in target if profile.code != candidate.code] + [candidate]
    ordered = sorted((profile for profile in group_profiles if matches(profile, context)), key=specificity)
    ordered += sorted((profile for profile in profiles if matches(profile, context)), key=specificity)
    result["locked_keys"] = {}
    result["ignored_overrides"] = []
    for profile in ordered:
        source = {"id": str(profile.pk), "code": profile.code, "name": profile.name,
                  "version": profile.version, "specificity": specificity(profile),
                  "level": "GROUP" if profile.tenant_id is None else "TENANT",
                  "locked_keys": profile.locked_keys}
        result["sources"].append(source)
        for section in SECTIONS:
            for key, value in (profile.overrides or {}).get(section, {}).items():
                path = f"{section}.{key}"
                if profile.tenant_id is not None and path in result["locked_keys"]:
                    result["ignored_overrides"].append({"profile": str(profile.pk), "key": path})
                    continue
                result[section][key] = deepcopy(value)
                result["origins"][section][key] = f"{'Groupe · ' if profile.tenant_id is None else ''}{profile.name} v{profile.version}"
        if profile.tenant_id is None:
            for path in profile.locked_keys:
                result["locked_keys"][path] = f"Groupe · {profile.name} v{profile.version}"
    protect_required_sections(result)
    if resolve_conventions:
        from django.core.exceptions import ValidationError as DjangoValidationError
        from rest_framework.exceptions import ValidationError
        try:
            result["simulation"] = resolve_simulation(tenant_id, result["simulation"])
        except DjangoValidationError as exc:
            raise ValidationError({"simulation": exc.messages}) from exc
    result["fingerprint"] = digest({key: result[key] for key in ("context", *SECTIONS, "sources")})
    return result


def application_configuration(application, *, individual_profile=None):
    frozen = getattr(application, "configuration_snapshot", None)
    if (frozen and getattr(application, "status", "DRAFT") in {"DRAFT", "RETURNED"}
            and frozen.get("context") != context_for(application, individual_profile)):
        frozen = None
    if isinstance(frozen, dict) and frozen.get("schema_version") in {1, 2, 3}:
        result = deepcopy(frozen)
        # Les anciennes captures gardent leur empreinte et les moteurs historiques.
        for section, defaults in rule_defaults().items():
            result.setdefault(section, defaults)
            result["origins"].setdefault(section, {key: "Règles historiques conservées" for key in defaults})
        for section, defaults in {**form_defaults(), "exposure": {"rules": deepcopy(DEFAULT_EXPOSURE)}, "simulation": simulation_defaults()}.items():
            result.setdefault(section, defaults)
            result["origins"].setdefault(section, {key: "Règles historiques conservées" for key in defaults})
        result.setdefault("pricing", pricing_defaults(getattr(application, "product", None)))
        result["origins"].setdefault("pricing", {key: "Tarification historique" for key in result["pricing"]})
        result["frozen"] = True
        # L'organisation de l'exécution suit toujours la décision de gestion courante.
        current = resolve_context(application.tenant_id, result["context"], resolve_conventions=False)
        for key in OPERATIONAL_POLICY_KEYS:
            result["policy"][key] = current["policy"][key]
            result["origins"]["policy"][key] = current["origins"]["policy"][key]
        return result
    context = context_for(application, individual_profile)
    if getattr(application, "status", "DRAFT") not in {"DRAFT", "RETURNED"}:
        # Pas d'adaptation rétroactive des dossiers historiques déjà soumis.
        result = resolve_context(application.tenant_id, {}, resolve_conventions=False)
        result["context"] = context
        result["sources"] = []
        policy = CreditInstructionPolicy.for_tenant(application.tenant_id)
        thresholds = AnalysisThreshold.for_tenant(application.tenant_id)
        result["policy"] = plain(model_values(policy)) | {"require_final_review": True}
        result["thresholds"] = plain(model_values(thresholds))
        result["analysis"] = {"required_fields": [], "required_detail_tables": [], "minimum_bank_statement_months": 0}
        result.update(rule_defaults())
        result.update(form_defaults())
        result["exposure"] = {"rules": deepcopy(DEFAULT_EXPOSURE)}
        result["simulation"] = simulation_defaults()
        result["pricing"] = pricing_defaults(getattr(application, "product", None))
        result["origins"] = {section: {key: "Politique filiale" for key in result[section]}
                             for section in SECTIONS}
        current = resolve_context(application.tenant_id, context, resolve_conventions=False)
        for key in OPERATIONAL_POLICY_KEYS:
            result["policy"][key] = current["policy"][key]
            result["origins"]["policy"][key] = current["origins"]["policy"][key]
        # Conserver l'empreinte du premier lot pour les dossiers historiques.
        result["fingerprint"] = digest({key: result[key] for key in ("context", "policy", "thresholds", "analysis", "sources")})
        result["legacy"] = True
        return result
    return resolve_context(application.tenant_id, context)


def effective_policy(application):
    base = CreditInstructionPolicy.for_tenant(application.tenant_id)
    result = application_configuration(application)
    for key, value in result["policy"].items():
        setattr(base, key, value)
    base.require_final_review = True
    base.configuration_fingerprint = result["fingerprint"]
    return base


def effective_thresholds(application, *, individual_profile=None):
    base = AnalysisThreshold.for_tenant(application.tenant_id)
    result = application_configuration(application, individual_profile=individual_profile)
    for key, value in result["thresholds"].items():
        setattr(base, key, base._meta.get_field(key).to_python(value))
    return base


def freeze_configuration(application):
    stored = getattr(application, "configuration_snapshot", None)
    if stored and stored.get("context") == context_for(application):
        return
    application.configuration_snapshot = {}
    result = application_configuration(application)
    result["captured_at"] = timezone.now().isoformat()
    application.configuration_snapshot = result


def analysis_requirement_failures(application, reference):
    config = application_configuration(application)
    rules = config["analysis"]
    failures = []
    if reference is None:
        return ["Ajoutez une analyse financière de référence."]
    from django.core.exceptions import ValidationError
    try:
        validate_custom_values(config["forms"]["analysis_fields"], getattr(reference, "custom_fields", {}) or {}, require=True)
    except ValidationError as exc:
        failures.extend(exc.messages)
    for key in rules.get("required_fields", []):
        value = getattr(reference, key, None)
        # Zéro est une valeur renseignée valide ; une vérification booléenne doit être confirmée.
        missing = value is None or (isinstance(value, str) and not value.strip()) or (isinstance(value, bool) and not value)
        if missing:
            failures.append(f"Analyse : {ANALYSIS_FIELDS[key].verbose_name} est requis.")
    details = reference.analysis_details or {}
    for key in rules.get("required_detail_tables", []):
        rows = details.get(key, [])
        if not rows or not any(any(value not in (None, "") for value in row.values()) for row in rows):
            failures.append(f"Analyse : complétez le tableau « {DETAIL_LABELS.get(key, key)} ».")
    months = rules.get("minimum_bank_statement_months", 0)
    if (reference.bank_statement_months or 0) < months:
        failures.append(f"Analyse : examinez au moins {months} mois de relevés.")
    return failures
