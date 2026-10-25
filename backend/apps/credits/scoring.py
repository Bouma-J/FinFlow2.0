"""Grilles financières bornées, explicables et conservées avec le dossier."""
from decimal import Decimal, InvalidOperation

from apps.configuration.rule_catalog import DEFAULT_GRID, SCORE_METRICS


def scoring_grid(analysis):
    from apps.configuration.services import application_configuration

    config = application_configuration(analysis.application, individual_profile=analysis.individual_profile)
    return config.get("scoring", {}).get("grid", DEFAULT_GRID)


def compute_custom_score(analysis, metrics, grid):
    from .analytics import _history_score, _information_quality_score, _score_high, _score_low

    parts, numerator, denominator, missing = [], Decimal("0"), Decimal("0"), []
    for criterion in grid["criteria"]:
        key = criterion["metric"]
        definition = SCORE_METRICS[key]
        applicable = not definition.get("clients") or analysis.client_type in definition["clients"]
        if not applicable:
            raw = None
        elif key == "history_score":
            raw = _history_score(analysis)
        elif key == "information_quality_score":
            raw = _information_quality_score(analysis)
        elif definition["source"] == "analysis":
            raw = getattr(analysis, key, None)
        else:
            raw = metrics.get(key)
        try:
            numeric = Decimal(str(raw)) if raw is not None else None
            if numeric is not None and not numeric.is_finite():
                numeric = None
        except (InvalidOperation, ValueError, TypeError):
            numeric = None
        weight = Decimal(criterion["weight"])
        invalid_income = ((key == "debt_ratio" and metrics.get("income_positive") is False)
                          or (key == "debt_ratio_stress" and metrics.get("stress_income_positive") is False))
        if invalid_income:
            # Un dénominateur non positif est un risque connu, pas une pièce
            # absente dont la renormalisation pourrait améliorer le score.
            score = Decimal("0")
            denominator += weight
        elif numeric is None:
            score = None
            missing.append(definition["label"])
            if grid["missing_data"] == "ZERO":
                denominator += weight
        else:
            score = (_score_high(numeric, criterion["bad"], criterion["good"])
                     if criterion["direction"] == "HIGH" else _score_low(numeric, criterion["good"], criterion["bad"]))
            denominator += weight
            numerator += score * weight
        parts.append({"key": key, "label": definition["label"], "score": float(score.quantize(Decimal("0.01"))) if score is not None else None,
                      "weight": float(weight), "raw_value": str(numeric) if numeric is not None else None,
                      "bad": criterion["bad"], "good": criterion["good"], "direction": criterion["direction"], "missing": numeric is None})
    total = numerator / denominator if denominator else None
    if missing and grid["missing_data"] == "BLOCK_SUBMIT":
        total = None
    total = total.quantize(Decimal("0.01")) if total is not None else None
    return total, {"total": float(total) if total is not None else None, "components": parts,
                   "engine": "CUSTOM", "missing_data": grid["missing_data"], "missing_metrics": missing,
                   "complete": not missing, "effective_weight": float(denominator), "risk_cutoffs": grid["risk_cutoffs"]}
