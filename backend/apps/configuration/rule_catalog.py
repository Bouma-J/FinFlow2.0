"""Critères autorisés : données métier explicites, sans expression exécutable."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import re

from django.core.exceptions import ValidationError


ELIGIBILITY_CRITERIA = {
    "age_years": {"label": "Âge du client à la soumission (années)", "type": "number", "clients": ["INDIVIDUAL"]},
    "age_at_maturity": {"label": "Âge à la dernière échéance (années)", "type": "number", "clients": ["INDIVIDUAL"]},
    "employment_seniority_months": {"label": "Ancienneté professionnelle (mois)", "type": "number", "clients": ["INDIVIDUAL"]},
    "activity_age_months": {"label": "Ancienneté de l'activité (mois)", "type": "number"},
    "relationship_age_months": {"label": "Ancienneté de la relation (mois)", "type": "number"},
    "personal_contribution_pct": {"label": "Apport / coût total du projet (%)", "type": "number"},
    "mandatory_savings_rate": {"label": "Taux d'épargne obligatoire (%)", "type": "number"},
    "active_loans_count": {"label": "Nombre de crédits actifs déclaré dans l'analyse", "type": "number"},
    "existing_debt_monthly": {"label": "Service mensuel des engagements existants", "type": "number"},
    "prior_max_delay_days": {"label": "Retard maximal des crédits précédents (jours)", "type": "number"},
    "internal_score": {"label": "Score financier recalculé (/100)", "type": "number"},
    "salary_domiciliation": {"label": "Domiciliation du salaire", "type": "boolean", "clients": ["INDIVIDUAL"]},
    "salary_paid_through_bank": {"label": "Salaire traçable en banque dans l'analyse", "type": "boolean", "clients": ["INDIVIDUAL"]},
    "has_credit_insurance": {"label": "Assurance du crédit", "type": "boolean"},
    "salary_verified": {"label": "Salaire vérifié", "type": "boolean", "clients": ["INDIVIDUAL"]},
    "credit_bureau_checked": {"label": "Consultation du bureau de crédit effectuée", "type": "boolean"},
    "has_payment_incidents": {"label": "Incidents de paiement déclarés", "type": "boolean"},
    "periodicity": {"label": "Périodicité du remboursement", "type": "text"},
    "repayment_mechanism": {"label": "Mécanisme de remboursement", "type": "text"},
    "employment_type": {"label": "Situation professionnelle", "type": "text", "clients": ["INDIVIDUAL"]},
    "sector": {"label": "Secteur d'activité de l'analyse", "type": "text"},
    "currency": {"label": "Devise du crédit", "type": "text"},
}

SCORE_METRICS = {
    "global_dscr": {"label": "DSCR global", "source": "metric", "clients": ["CORPORATE"]},
    "gearing": {"label": "Dettes financières / capitaux propres", "source": "metric", "clients": ["CORPORATE"]},
    "current_ratio": {"label": "Liquidité générale", "source": "metric", "clients": ["CORPORATE"]},
    "financial_autonomy": {"label": "Autonomie financière (%)", "source": "metric", "clients": ["CORPORATE"]},
    "interest_coverage": {"label": "Couverture des charges financières", "source": "metric", "clients": ["CORPORATE"]},
    "turnover_growth": {"label": "Croissance du chiffre d'affaires (%)", "source": "metric", "clients": ["CORPORATE"]},
    "debt_ratio": {"label": "Taux d'effort (%)", "source": "metric", "clients": ["INDIVIDUAL", "PROFESSIONAL"]},
    "debt_ratio_stress": {"label": "Taux d'effort sous stress (%)", "source": "metric", "clients": ["INDIVIDUAL", "PROFESSIONAL"]},
    "disposable_per_capita": {"label": "Reste à vivre mensuel par personne", "source": "metric", "clients": ["INDIVIDUAL"]},
    "guarantee_coverage": {"label": "Couverture des garanties (%)", "source": "metric"},
    "safety_margin": {"label": "Marge mensuelle de sécurité", "source": "metric"},
    "employment_seniority_months": {"label": "Ancienneté professionnelle (mois)", "source": "analysis", "clients": ["INDIVIDUAL"]},
    "activity_business_age_months": {"label": "Ancienneté de l'activité (mois)", "source": "analysis", "clients": ["INDIVIDUAL"]},
    "group_age_months": {"label": "Ancienneté du groupement (mois)", "source": "analysis", "clients": ["PROFESSIONAL"]},
    "prior_repayment_rate": {"label": "Taux de remboursement historique (%)", "source": "analysis"},
    "history_score": {"label": "Historique de remboursement (/100)", "source": "derived"},
    "information_quality_score": {"label": "Fiabilité des informations (/100)", "source": "derived"},
    "contribution_concentration": {"label": "Part des membres cotisants (%)", "source": "metric", "clients": ["PROFESSIONAL"]},
    "members_arrears_rate": {"label": "Part des membres en impayé (%)", "source": "metric", "clients": ["PROFESSIONAL"]},
}

DEFAULT_GRID = {"engine": "LEGACY", "missing_data": "RENORMALIZE", "criteria": [],
                "risk_cutoffs": ["80", "65", "50", "35"]}
EFFECTS = ["ALERT", "BLOCK_SUBMIT", "BLOCK_APPROVE", "BLOCK_SETUP"]


def rule_defaults():
    return {"eligibility": {"rules": []}, "scoring": {"grid": deepcopy(DEFAULT_GRID)}}


def number(value, label, *, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValidationError(f"{label} attend un nombre.")
    if isinstance(value, str) and len(value) > 64:
        raise ValidationError(f"Valeur trop longue : {label}.")
    try:
        result = Decimal(str(value))
        if not result.is_finite() or abs(result) > Decimal("1e16"):
            raise ValueError
        if result.as_tuple().exponent < -8 or len(result.as_tuple().digits) > 24:
            raise ValueError
        if minimum is not None and result < Decimal(str(minimum)):
            raise ValueError
        if maximum is not None and result > Decimal(str(maximum)):
            raise ValueError
    except (InvalidOperation, ValueError):
        raise ValidationError(f"Valeur hors limites : {label} (au plus 8 décimales).")
    return str(result)


def _identifier(value):
    return isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,60}", value)


def validate_eligibility(value):
    if not isinstance(value, dict) or set(value) - {"rules"}:
        raise ValidationError("Paramètres d'éligibilité inconnus.")
    if "rules" not in value:
        return {}
    rows = value["rules"]
    if not isinstance(rows, list) or len(rows) > 60:
        raise ValidationError("L'éligibilité attend au maximum 60 règles.")
    cleaned, seen = [], set()
    for row in rows:
        allowed = {"id", "criterion", "operator", "value", "effect", "missing"}
        if not isinstance(row, dict) or set(row) - allowed:
            raise ValidationError("Structure de règle d'éligibilité invalide.")
        identifier, criterion = row.get("id"), row.get("criterion")
        if not _identifier(identifier) or identifier in seen or not isinstance(criterion, str) or criterion not in ELIGIBILITY_CRITERIA:
            raise ValidationError("Identifiant de règle dupliqué ou critère d'éligibilité inconnu.")
        seen.add(identifier)
        kind, op = ELIGIBILITY_CRITERIA[criterion]["type"], row.get("operator")
        if row.get("effect") not in EFFECTS or row.get("missing", "FAIL") not in ("FAIL", "IGNORE"):
            raise ValidationError("Effet ou traitement des données manquantes invalide.")
        data = row.get("value")
        if kind == "number":
            if op not in ("gte", "lte", "eq"):
                raise ValidationError("Opérateur numérique invalide.")
            data = number(data, ELIGIBILITY_CRITERIA[criterion]["label"], minimum=0)
        elif kind == "boolean":
            if op != "eq" or type(data) is not bool:
                raise ValidationError("Une règle de vérification attend Oui ou Non.")
        else:
            if op not in ("in", "not_in") or not isinstance(data, list) or not 1 <= len(data) <= 50:
                raise ValidationError("Une règle de liste attend au moins une valeur autorisée ou exclue.")
            if any(not isinstance(item, str) or not item.strip() or len(item) > 64 for item in data):
                raise ValidationError("Valeurs de liste invalides.")
            data = sorted(set(item.strip() for item in data))
        cleaned.append({"id": identifier, "criterion": criterion, "operator": op, "value": data,
                        "effect": row["effect"], "missing": row.get("missing", "FAIL")})
    return {"rules": cleaned}


def validate_scoring(value):
    if not isinstance(value, dict) or set(value) - {"grid"}:
        raise ValidationError("Paramètres de scoring inconnus.")
    if "grid" not in value:
        return {}
    grid = value["grid"]
    if not isinstance(grid, dict) or set(grid) - set(DEFAULT_GRID):
        raise ValidationError("Structure de grille de scoring invalide.")
    engine, missing = grid.get("engine"), grid.get("missing_data")
    if engine not in ("LEGACY", "CUSTOM") or missing not in ("RENORMALIZE", "ZERO", "BLOCK_SUBMIT"):
        raise ValidationError("Moteur ou traitement des données manquantes invalide.")
    cutoffs = grid.get("risk_cutoffs")
    if not isinstance(cutoffs, list) or len(cutoffs) != 4:
        raise ValidationError("Quatre seuils sont requis pour les cinq classes de risque.")
    cutoffs = [number(item, "Seuil de risque", minimum=0, maximum=100) for item in cutoffs]
    if any(Decimal(cutoffs[index]) <= Decimal(cutoffs[index + 1]) for index in range(3)):
        raise ValidationError("Les seuils de risque doivent être strictement décroissants.")
    rows = grid.get("criteria", [])
    if not isinstance(rows, list) or len(rows) > 25 or (engine == "CUSTOM" and not rows) or (engine == "LEGACY" and rows):
        raise ValidationError("Une grille personnalisée attend de 1 à 25 critères ; la grille existante n'accepte pas de critères supplémentaires.")
    cleaned, seen, total = [], set(), Decimal("0")
    for row in rows:
        if not isinstance(row, dict) or set(row) - {"metric", "direction", "bad", "good", "weight"}:
            raise ValidationError("Structure de critère de score invalide.")
        metric, direction = row.get("metric"), row.get("direction")
        if not isinstance(metric, str) or metric not in SCORE_METRICS or metric in seen or direction not in ("HIGH", "LOW"):
            raise ValidationError("Indicateur dupliqué, inconnu ou sens de variation invalide.")
        seen.add(metric)
        bad, good = number(row.get("bad"), "Borne défavorable"), number(row.get("good"), "Borne favorable")
        if (direction == "HIGH" and Decimal(good) <= Decimal(bad)) or (direction == "LOW" and Decimal(good) >= Decimal(bad)):
            raise ValidationError("Les bornes doivent respecter le sens de variation choisi.")
        weight = number(row.get("weight"), "Pondération", minimum=Decimal("0.01"), maximum=100)
        total += Decimal(weight)
        cleaned.append({"metric": metric, "direction": direction, "bad": bad, "good": good, "weight": weight})
    if engine == "CUSTOM" and total != Decimal("100"):
        raise ValidationError("La somme des pondérations doit être exactement égale à 100 %.")
    if engine == "LEGACY" and missing != "RENORMALIZE":
        raise ValidationError("Le traitement des données manquantes de la grille existante reste inchangé. Utilisez une grille personnalisée pour l'adapter.")
    return {"grid": {"engine": engine, "missing_data": missing, "criteria": cleaned, "risk_cutoffs": cutoffs}}


def validate_rule_scope(profile):
    """Refuse les critères intrinsèquement incompatibles avec le périmètre."""
    client_type = profile.client_type
    if not client_type and profile.product_id and profile.product.client_type in {"INDIVIDUAL", "PROFESSIONAL"}:
        client_type = profile.product.client_type
    for row in profile.overrides.get("eligibility", {}).get("rules", []):
        allowed = ELIGIBILITY_CRITERIA[row["criterion"]].get("clients")
        if allowed and (not client_type or client_type not in allowed):
            raise ValidationError("Limitez le profil au type de client adapté au critère : " + ELIGIBILITY_CRITERIA[row["criterion"]]["label"])
    for row in profile.overrides.get("scoring", {}).get("grid", {}).get("criteria", []):
        allowed = SCORE_METRICS[row["metric"]].get("clients")
        if allowed and (not client_type or client_type not in allowed):
            raise ValidationError("Limitez le profil au type de client adapté à l'indicateur : " + SCORE_METRICS[row["metric"]]["label"])
