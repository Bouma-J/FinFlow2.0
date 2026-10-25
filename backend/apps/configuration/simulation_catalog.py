"""Conventions explicites de calcul, distinctes de toute règle réglementaire."""
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID

from django.core.exceptions import ValidationError


DEFAULT_CONVENTIONS = {
    "engine": "LEGACY", "day_count": "ACT365_FIXED", "amount_step": "0.01",
    "rounding": "HALF_UP", "due_adjustment": "NONE", "interest_dates": "NOMINAL",
    "calendar": None,
}
CHOICES = {
    "engine": {"LEGACY", "CONFIGURED"},
    "day_count": {"ACT365_FIXED", "ACT360", "30E360"},
    "rounding": {"HALF_UP", "HALF_EVEN"},
    "due_adjustment": {"NONE", "FOLLOWING", "MODIFIED_FOLLOWING", "PRECEDING"},
    "interest_dates": {"NOMINAL", "ADJUSTED"},
}


def simulation_defaults():
    return {"conventions": deepcopy(DEFAULT_CONVENTIONS)}


def validate_simulation(value):
    if not isinstance(value, dict) or set(value) - {"conventions"}:
        raise ValidationError("Paramètres de simulation inconnus.")
    if "conventions" not in value:
        return {}
    return {"conventions": normalize_conventions(value["conventions"])}


def normalize_conventions(raw, *, allow_snapshot=False):
    keys = set(DEFAULT_CONVENTIONS) | ({"calendar_snapshot", "periods_per_year"} if allow_snapshot else set())
    if not isinstance(raw, dict) or set(raw) - keys:
        raise ValidationError("Conventions de calcul invalides ou champs inconnus.")
    result = deepcopy(DEFAULT_CONVENTIONS) | deepcopy(raw)
    for key, choices in CHOICES.items():
        if not isinstance(result[key], str) or result[key] not in choices:
            raise ValidationError(f"Convention de calcul invalide : {key}.")
    try:
        step = Decimal(str(result["amount_step"]))
        if isinstance(result["amount_step"], bool) or not step.is_finite() or not Decimal("0.01") <= step <= Decimal("1000") or step.as_tuple().exponent < -2:
            raise ValueError
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError("Le pas d'arrondi doit être compris entre 0,01 et 1 000 avec deux décimales maximum.")
    result["amount_step"] = str(step)
    if result["calendar"]:
        try:
            result["calendar"] = str(UUID(str(result["calendar"])))
        except (ValueError, TypeError, AttributeError):
            raise ValidationError("Identifiant de calendrier invalide.")
    elif result["calendar"] is not None:
        raise ValidationError("Le calendrier doit être un identifiant ou null.")
    if result["engine"] == "CONFIGURED" and result["due_adjustment"] != "NONE" and result["calendar"] is None:
        raise ValidationError("Un calendrier ouvré de la filiale est requis pour ajuster les échéances.")
    if allow_snapshot and result.get("calendar_snapshot"):
        snapshot = result["calendar_snapshot"]
        if not isinstance(snapshot, dict) or set(snapshot) - {"id", "name", "working_days", "holidays"}:
            raise ValidationError("Copie de calendrier invalide.")
        days = snapshot.get("working_days")
        holidays = snapshot.get("holidays")
        if not isinstance(days, list) or not days or any(isinstance(day, bool) or not isinstance(day, int) or day not in range(7) for day in days) or len(days) != len(set(days)):
            raise ValidationError("Jours ouvrés invalides dans le calendrier conservé.")
        if not isinstance(holidays, list) or len(holidays) > 2000:
            raise ValidationError("Dates fériées invalides dans le calendrier conservé.")
        try:
            for day in holidays:
                if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
                    raise ValueError
        except (ValueError, TypeError):
            raise ValidationError("Date fériée invalide dans le calendrier conservé.")
        if snapshot.get("id") != result["calendar"]:
            raise ValidationError("Le calendrier conservé ne correspond pas au calendrier choisi.")
    if allow_snapshot and "periods_per_year" in result:
        frequencies = result["periods_per_year"]
        if not isinstance(frequencies, dict) or len(frequencies) > 7 or any(not isinstance(key, str) or isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10000 for key, value in frequencies.items()):
            raise ValidationError("Fréquences conservées invalides.")
    return result


def resolve_simulation(tenant_id, value):
    """À appeler après composition des profils, avant calcul de l'empreinte."""
    result = validate_simulation(value) or simulation_defaults()
    conventions = result["conventions"]
    if conventions["engine"] == "LEGACY":
        return result
    from apps.credits.models import _PERIODS_PER_YEAR
    from apps.catalog.models import LoanPeriodicity
    conventions["periods_per_year"] = dict(_PERIODS_PER_YEAR)
    for item in LoanPeriodicity.all_tenants.filter(tenant_id=tenant_id, is_active=True, code__in=_PERIODS_PER_YEAR):
        if item.periods_per_year:
            conventions["periods_per_year"][item.code] = int(item.periods_per_year)
    if not conventions["calendar"]:
        return result
    from apps.workflow.models import BusinessCalendar
    calendar = BusinessCalendar.all_tenants.filter(pk=conventions["calendar"], tenant_id=tenant_id, is_active=True).first()
    if calendar is None:
        raise ValidationError("Le calendrier de simulation doit être actif et appartenir à la filiale du dossier.")
    conventions["calendar_snapshot"] = {
        "id": str(calendar.pk), "name": calendar.name,
        "working_days": list(calendar.working_days), "holidays": list(calendar.holidays),
    }
    normalize_conventions(conventions, allow_snapshot=True)
    return result
