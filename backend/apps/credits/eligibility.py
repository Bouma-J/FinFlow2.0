"""Évaluation des règles d'offre avec résultats explicites par étape."""
from decimal import Decimal, InvalidOperation

from dateutil.relativedelta import relativedelta
from django.utils import timezone

from apps.configuration.rule_catalog import ELIGIBILITY_CRITERIA


def _months(start, end):
    if not start or start > end:
        return None
    delta = relativedelta(end, start)
    return delta.years * 12 + delta.months


def _years(birth, end):
    if not birth or birth > end:
        return None
    return relativedelta(end, birth).years


def eligibility_values(application, reference, score, as_of):
    client = application.client
    birth = getattr(client, "birth_date", None)
    duration = application.duration_months
    maturity = application.last_due_date or (as_of + relativedelta(months=duration) if duration else None)
    cost, contribution = application.project_total_cost, application.personal_contribution
    values = {
        "age_years": _years(birth, as_of),
        "age_at_maturity": _years(birth, maturity) if maturity else None,
        "activity_age_months": _months(application.activity_start_date, as_of),
        "relationship_age_months": _months(application.relationship_start_date, as_of),
        "personal_contribution_pct": Decimal(contribution) / Decimal(cost) * 100 if cost and cost > 0 and contribution is not None else None,
        "mandatory_savings_rate": application.mandatory_savings_rate,
        "salary_domiciliation": application.salary_domiciliation,
        "has_credit_insurance": application.has_credit_insurance,
        "periodicity": application.periodicity or None,
        "repayment_mechanism": application.repayment_mechanism or None,
        "currency": application.currency or None,
        "internal_score": score,
    }
    fields = ("employment_seniority_months", "active_loans_count", "existing_debt_monthly",
              "prior_max_delay_days", "salary_verified", "credit_bureau_checked",
              "has_payment_incidents", "employment_type", "sector", "salary_paid_through_bank")
    for field in fields:
        value = getattr(reference, field, None) if reference else None
        values[field] = None if value == "" else value
    if reference and client.client_type == "INDIVIDUAL" and reference.activity_business_age_months is not None:
        values["activity_age_months"] = reference.activity_business_age_months
    if reference and client.client_type == "PROFESSIONAL" and reference.group_age_months is not None:
        values["activity_age_months"] = reference.group_age_months
    return values


def assess_rules(application, *, configuration=None, reference=None):
    from apps.configuration.services import application_configuration
    from .analytics import compute_metrics, compute_score
    from .models import AnalysisThreshold

    config = configuration or application_configuration(application)
    if reference is None:
        reference = (application.financial_analyses.filter(is_reference=True).first()
                     or application.financial_analyses.order_by("-created_at").first())
    score, breakdown = None, {"total": None, "components": [], "missing_metrics": []}
    if reference:
        # L'aperçu d'un candidat peut fournir ses propres seuils et sa grille.
        th = AnalysisThreshold(tenant_id=application.tenant_id)
        for key, value in config["thresholds"].items():
            setattr(th, key, th._meta.get_field(key).to_python(value))
        metrics = compute_metrics(reference, th, configuration=config)
        score, breakdown = compute_score(reference, metrics, th, grid=config["scoring"]["grid"])
    submitted = application.submitted_at
    as_of = timezone.localdate(submitted) if submitted else timezone.localdate()
    # La date d'évaluation de la soumission est conservée dans la capture.
    captured = config.get("captured_at")
    if captured:
        from django.utils.dateparse import parse_datetime
        captured_at = parse_datetime(captured)
        if captured_at:
            as_of = timezone.localdate(captured_at)
    values = eligibility_values(application, reference, score, as_of)
    checks = []
    for rule in config["eligibility"]["rules"]:
        definition = ELIGIBILITY_CRITERIA[rule["criterion"]]
        value = values.get(rule["criterion"])
        if definition.get("clients") and application.client.client_type not in definition["clients"]:
            value = None
        missing = value is None
        if missing:
            passed = None if rule["missing"] == "IGNORE" else False
        elif definition["type"] == "number":
            try:
                actual, expected = Decimal(str(value)), Decimal(rule["value"])
                if not actual.is_finite():
                    raise ValueError
                passed = {"gte": actual >= expected, "lte": actual <= expected, "eq": actual == expected}[rule["operator"]]
            except (InvalidOperation, ValueError):
                missing, passed = True, None if rule["missing"] == "IGNORE" else False
        elif definition["type"] == "boolean":
            passed = value is rule["value"]
        else:
            contained = str(value) in rule["value"]
            passed = contained if rule["operator"] == "in" else not contained
        message = ""
        if passed is False:
            operators = {"gte": "au moins", "lte": "au maximum", "eq": "égal à", "in": "parmi", "not_in": "hors de"}
            def display(data):
                if isinstance(data, bool):
                    return "Oui" if data else "Non"
                if isinstance(data, list):
                    return ", ".join(data)
                if isinstance(data, Decimal):
                    return format(data.quantize(Decimal("0.01")), "f")
                return str(data)
            expected = operators[rule["operator"]] + " " + display(rule["value"])
            message = (f"{definition['label']} : donnée manquante ; attendu {expected}." if missing
                       else f"{definition['label']} : {display(value)} ; attendu {expected}.")
        elif missing:
            message = f"{definition['label']} : donnée manquante, contrôle ignoré selon la configuration."
        checks.append({"id": rule["id"], "criterion": rule["criterion"], "label": definition["label"],
                       "operator": rule["operator"], "expected": rule["value"], "actual": value,
                       "passed": passed, "missing": missing, "effect": rule["effect"], "message": message})
    score_failures = []
    grid = config["scoring"]["grid"]
    if grid["engine"] == "CUSTOM" and grid["missing_data"] == "BLOCK_SUBMIT":
        if not reference:
            score_failures.append("Une analyse est requise pour calculer le score personnalisé.")
        elif breakdown.get("missing_metrics"):
            score_failures.append("Score incomplet : " + ", ".join(breakdown["missing_metrics"]) + ".")
    risk_class = None if score is None else next((index + 1 for index, cutoff in enumerate(grid["risk_cutoffs"])
                                                 if score >= Decimal(cutoff)), 5)
    return {"as_of": as_of, "checks": checks, "score": score, "score_risk_level": risk_class, "score_breakdown": breakdown,
            "scoring_failures": score_failures, "scoring_engine": grid["engine"],
            "risk_cutoffs": grid["risk_cutoffs"]}


def rule_failures(evaluation, phase):
    effects = {
        "SUBMIT": {"BLOCK_SUBMIT"},
        "APPROVE": {"BLOCK_SUBMIT", "BLOCK_APPROVE"},
        "SETUP": {"BLOCK_SUBMIT", "BLOCK_APPROVE", "BLOCK_SETUP"},
    }[phase]
    failures = [check["message"] for check in evaluation["checks"]
                if check["passed"] is False and check["effect"] in effects]
    return failures + evaluation["scoring_failures"]


def assert_configured_rules(application, phase):
    from apps.workflow.services import WorkflowError

    failures = rule_failures(assess_rules(application), phase)
    if failures:
        raise WorkflowError(" ".join(failures))
