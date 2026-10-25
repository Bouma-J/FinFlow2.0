"""Dérivation du niveau de risque workflow depuis l'analyse de référence."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation


def _dec(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


def risk_level_from_analysis(analysis) -> int | None:
    """
    Mappe l'analyse de référence vers risk_level (1–5) pour le circuit.

    Priorité : recommendation, sinon score interne (/100).
    """
    if analysis is None:
        return None

    from .instruction_policy import get_instruction_policy
    from .scoring import scoring_grid

    policy = get_instruction_policy(analysis.tenant_id, application=analysis.application)
    rec = (getattr(analysis, "recommendation", None) or "").upper()
    recommendation_risk = {"UNFAVORABLE": 5, "CONDITIONAL": 3, "FAVORABLE": 2}.get(rec)
    score = _dec(getattr(analysis, "internal_score", None))
    cutoffs = [Decimal(str(value)) for value in scoring_grid(analysis)["risk_cutoffs"]]
    score_risk = None if score is None else next((index + 1 for index, limit in enumerate(cutoffs) if score >= limit), 5)
    if policy.risk_mode == "SCORE":
        return score_risk if score_risk is not None else recommendation_risk
    if policy.risk_mode == "CONSERVATIVE":
        values = [value for value in (score_risk, recommendation_risk) if value is not None]
        return max(values) if values else None
    return recommendation_risk if recommendation_risk is not None else score_risk
