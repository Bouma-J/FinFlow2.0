"""Plafonds internes, sans taux de conversion ni seuil réglementaire implicite."""
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError

DEFAULT_EXPOSURE = {
    "enabled": False, "currency": "", "gate": "ALERT", "include_pending": True,
    "client_limit": None, "group_limit": None, "maximum_age_days": 0,
    "require_verified_snapshot": False, "use_cbs_client_limit": False,
}


def validate_exposure(raw):
    if not isinstance(raw, dict) or set(raw) - {"rules"}:
        raise ValidationError("Paramètres d'engagements inconnus.")
    if "rules" not in raw:
        return {}
    data = raw["rules"]
    if not isinstance(data, dict) or set(data) != set(DEFAULT_EXPOSURE):
        raise ValidationError("Le paramétrage des engagements doit contenir toutes les clés du catalogue.")
    result = dict(data)
    for key in ("enabled", "include_pending", "require_verified_snapshot", "use_cbs_client_limit"):
        if type(data[key]) is not bool:
            raise ValidationError(f"Engagements : {key} attend un booléen.")
    if data["gate"] not in {"ALERT", "SUBMIT", "APPROVE", "SETUP"}:
        raise ValidationError("Étape de contrôle des engagements invalide.")
    currency = data["currency"]
    if not isinstance(currency, str) or (currency and (len(currency) != 3 or not currency.isascii() or not currency.isalpha() or not currency.isupper())):
        raise ValidationError("La devise des plafonds doit comporter trois lettres majuscules.")
    if data["enabled"] and not currency:
        raise ValidationError("Précisez la devise pour activer les plafonds.")
    if type(data["maximum_age_days"]) is not int or not 0 <= data["maximum_age_days"] <= 36500:
        raise ValidationError("L'ancienneté maximale doit être comprise entre 0 et 36500 jours.")
    for key in ("client_limit", "group_limit"):
        if data[key] is None:
            continue
        try:
            number = Decimal(str(data[key]))
            if isinstance(data[key], bool) or not number.is_finite() or number < 0 or number >= Decimal("1e16") or number.as_tuple().exponent < -2:
                raise ValueError
        except (InvalidOperation, ValueError, TypeError):
            raise ValidationError(f"Plafond invalide : {key}.")
        result[key] = str(number)
    return {"rules": result}
