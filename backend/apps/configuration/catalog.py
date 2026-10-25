"""Catalogue typé, partagé par les API, l'interface et la validation serveur."""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import models

from apps.credits.analysis_details import DETAIL_SCHEMAS
from apps.credits.models import AnalysisThreshold, CreditInstructionPolicy, FinancialAnalysis
from .rule_catalog import ELIGIBILITY_CRITERIA, SCORE_METRICS, DEFAULT_GRID, validate_eligibility, validate_scoring
from .pricing_catalog import DEFAULT_TARIFF, validate_pricing
from .forms_catalog import (ANALYSIS_SECTIONS, OPTIONAL_SECTIONS, native_kyc_fields, document_fields, form_defaults,
                            validate_forms, validate_kyc, validate_references)
from .exposure_catalog import DEFAULT_EXPOSURE, validate_exposure
from .simulation_catalog import simulation_defaults, validate_simulation


EXCLUDED = {"id", "tenant", "created_at", "updated_at", "require_final_review"}
OPERATIONAL_POLICY_KEYS = {"setup_execution_role", "require_setup_authorizer_separation", "require_setup_four_eyes"}
DETAIL_LABELS = {"products": "fiches produits et ventes", "stocks": "inventaire des stocks",
                 "debts": "engagements et dettes", "cashflow": "plan de trésorerie", "history": "historique financier"}
POLICY_LABELS = {
    "require_credit_contracts": "Contrats de crédit obligatoires",
    "require_credit_signed_contracts": "Signature des contrats de crédit obligatoire",
    "require_surety_contracts": "Contrats de cautionnement obligatoires",
    "require_setup_request": "Demande préalable de transmission au CBS",
    "require_setup_four_eyes": "Demandeur et exécutant distincts",
    "risk_mode": "Méthode de détermination du risque",
    "approval_validity_days": "Validité de l'accord (jours ; 0 = sans limite)",
    "max_analysis_age_days": "Ancienneté maximale de l'analyse (jours ; 0 = sans limite)",
    "setup_execution_role": "Fonction chargée de transmettre au CBS",
    "require_setup_authorizer_separation": "Autorisateur et exécutant distincts",
    "recheck_kyc_on_setup": "Revérifier le KYC avant mise en place",
    "require_verified_documents": "Exiger des documents vérifiés",
}
ANALYSIS_FIELDS = {
    field.name: field for field in FinancialAnalysis._meta.fields
    if field.editable and isinstance(field, (models.DecimalField, models.IntegerField,
                                             models.BooleanField, models.DateField,
                                             models.CharField, models.TextField))
    and field.name not in {"client_type", "author_role", "recommendation", "individual_profile",
                           "is_reference", "new_installment", "repayment_capacity", "debt_ratio", "dscr",
                           "debt_ratio_stress", "dscr_stress", "guarantee_coverage", "internal_score"}
    and field.name not in EXCLUDED
}


def model_values(instance):
    return {field.name: getattr(instance, field.name)
            for field in instance._meta.fields if field.name not in EXCLUDED}


def _fields(model):
    result = []
    defaults = model()
    for field in model._meta.fields:
        if field.name in EXCLUDED:
            continue
        kind = "boolean" if isinstance(field, models.BooleanField) else (
            "choice" if field.choices else "integer" if isinstance(field, models.IntegerField) else "decimal"
        )
        result.append({"key": field.name, "label": POLICY_LABELS.get(field.name, str(field.verbose_name)) if model is CreditInstructionPolicy else str(field.verbose_name), "type": kind,
                       "choices": [{"value": value, "label": str(label)} for value, label in field.choices or []],
                       "default": getattr(defaults, field.name),
                       "operational": field.name in OPERATIONAL_POLICY_KEYS})
    return result


def parameter_catalog():
    from apps.catalog.models import Currency, LoanPeriodicity
    from apps.common.tenancy import get_current_tenant_id
    from apps.credits.models import Periodicity, RepaymentMechanism

    tenant_id = get_current_tenant_id()
    reference_choices = {
        "employment_type": list(FinancialAnalysis.EmploymentType.choices),
        "sector": list(FinancialAnalysis._meta.get_field("sector").choices),
        "repayment_mechanism": list(RepaymentMechanism.choices),
        "periodicity": [(item.code, item.label) for item in LoanPeriodicity.all_tenants.filter(tenant_id=tenant_id, is_active=True)] or list(Periodicity.choices),
        "currency": [(item.code, item.label) for item in Currency.all_tenants.filter(tenant_id=tenant_id, is_active=True)],
    }
    return {
        "policy": _fields(CreditInstructionPolicy),
        "thresholds": _fields(AnalysisThreshold),
        "analysis_fields": [{"key": key, "label": str(field.verbose_name)} for key, field in ANALYSIS_FIELDS.items()],
        "detail_tables": list(DETAIL_SCHEMAS),
        "eligibility_criteria": [{"key": key, **definition,
                                  "choices": [{"value": value, "label": str(label)} for value, label in reference_choices.get(key, [])]}
                                 for key, definition in ELIGIBILITY_CRITERIA.items()],
        "score_metrics": [{"key": key, **definition} for key, definition in SCORE_METRICS.items()],
        "default_grid": DEFAULT_GRID,
        "default_tariff": DEFAULT_TARIFF,
        "default_forms": form_defaults()["forms"], "default_kyc": form_defaults()["kyc"],
        "default_references": form_defaults()["references"], "default_exposure": DEFAULT_EXPOSURE,
        "default_simulation": simulation_defaults()["conventions"],
        "form_sections": [{"id": key, "label": label, "can_hide": key in OPTIONAL_SECTIONS} for key, label in ANALYSIS_SECTIONS.items()],
        "kyc_fields": [{"key": key, "label": label} for key, label in native_kyc_fields().items()],
        "kyc_documents": [{"key": key, "label": label} for key, label in document_fields().items()],
        "precedence": ["Valeurs initiales filiale", "Socles Groupe", "Adaptations filiale : agence", "Type de client", "Profil particulier", "Produit (sauf verrous Groupe)"],
        "locked_rules": ["Contrôle et autorisation de l'administrateur crédit", "Confirmation CBS en exploitation réelle", "Isolation des filiales et habilitations"],
        "modules": [
            {"key": "policy", "label": "Politique de crédit", "available": True},
            {"key": "thresholds", "label": "Seuils d'analyse", "available": True},
            {"key": "analysis", "label": "Exigences de l'analyse", "available": True},
            {"key": "scoring", "label": "Grilles de scoring", "available": True},
            {"key": "eligibility", "label": "Éligibilité des produits", "available": True},
            {"key": "pricing", "label": "Tarification des crédits", "available": True},
            {"key": "forms", "label": "Formulaires et champs additionnels", "available": True},
            {"key": "kyc", "label": "Exigences KYC", "available": True},
            {"key": "references", "label": "Référentiels clients", "available": True},
            {"key": "exposure", "label": "Engagements et plafonds", "available": True},
            {"key": "simulation", "label": "Conventions du simulateur", "available": True},
            {"key": "workflow", "label": "Circuits : administration existante", "available": False},
            {"key": "documents", "label": "Contrats et GED : administrations existantes", "available": False},
        ],
    }


def validate_overrides(value):
    if not isinstance(value, dict) or set(value) - {"policy", "thresholds", "analysis", "eligibility", "scoring", "pricing", "forms", "kyc", "references", "exposure", "simulation"}:
        raise ValidationError("Rubrique de configuration inconnue.")
    normalized = {}
    for section, model in (("policy", CreditInstructionPolicy), ("thresholds", AnalysisThreshold)):
        raw = value.get(section, {})
        if not isinstance(raw, dict):
            raise ValidationError(f"{section} doit être un objet.")
        fields = {field.name: field for field in model._meta.fields if field.name not in EXCLUDED}
        if set(raw) - set(fields):
            raise ValidationError(f"Paramètres inconnus ou protégés dans {section} : {', '.join(sorted(set(raw) - set(fields)))}.")
        normalized[section] = {}
        for key, data in raw.items():
            field = fields[key]
            if isinstance(field, models.BooleanField) and not isinstance(data, bool):
                raise ValidationError(f"{section}.{key} attend un booléen.")
            if isinstance(field, (models.DecimalField, models.IntegerField)):
                if isinstance(data, bool):
                    raise ValidationError(f"{section}.{key} attend un nombre.")
                try:
                    number = Decimal(str(data))
                    if not number.is_finite() or number < 0:
                        raise ValueError
                    if isinstance(field, models.IntegerField) and (number != int(number) or number > 36500):
                        raise ValueError
                    bounded = (key.startswith("haircut_") or key in {
                        "max_debt_ratio", "max_leverage_ratio", "min_financial_autonomy", "stress_pct",
                        "transferable_quota_fraction", "informal_income_weight",
                    })
                    if bounded and number > 100:
                        raise ValueError
                except (InvalidOperation, ValueError, TypeError, OverflowError):
                    raise ValidationError(f"Valeur hors limites pour {section}.{key}.")
            cleaned = field.clean(data, model())
            normalized[section][key] = str(cleaned) if isinstance(cleaned, Decimal) else cleaned
    analysis = value.get("analysis", {})
    allowed = {"required_fields", "required_detail_tables", "minimum_bank_statement_months"}
    if not isinstance(analysis, dict) or set(analysis) - allowed:
        raise ValidationError("Exigences d'analyse inconnues.")
    normalized["analysis"] = {}
    for key, choices in (("required_fields", ANALYSIS_FIELDS), ("required_detail_tables", DETAIL_SCHEMAS)):
        if key not in analysis:
            continue
        entries = analysis[key]
        if not isinstance(entries, list) or any(not isinstance(item, str) or item not in choices for item in entries):
            raise ValidationError(f"Liste invalide pour analysis.{key}.")
        normalized["analysis"][key] = sorted(set(entries))
    if "minimum_bank_statement_months" in analysis:
        months = analysis["minimum_bank_statement_months"]
        if type(months) is not int or not 0 <= months <= 120:
            raise ValidationError("Le nombre de mois de relevés doit être compris entre 0 et 120.")
        normalized["analysis"]["minimum_bank_statement_months"] = months
    normalized["eligibility"] = validate_eligibility(value.get("eligibility", {}))
    normalized["scoring"] = validate_scoring(value.get("scoring", {}))
    normalized["pricing"] = validate_pricing(value.get("pricing", {}))
    normalized["forms"] = validate_forms(value.get("forms", {}))
    normalized["kyc"] = validate_kyc(value.get("kyc", {}))
    normalized["references"] = validate_references(value.get("references", {}))
    normalized["exposure"] = validate_exposure(value.get("exposure", {}))
    normalized["simulation"] = validate_simulation(value.get("simulation", {}))
    return normalized
