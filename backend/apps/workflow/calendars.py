"""Délais ouvrés calculés sur une copie du calendrier au démarrage du circuit."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def validate_calendar(values):
    """Validation partagée entre API et moteur (y compris données hors API)."""
    days = values["working_days"]
    if (
        not isinstance(days, list)
        or not days
        or any(type(day) is not int or day not in range(7) for day in days)
        or len(set(days)) != len(days)
    ):
        raise ValueError(
            "Sélectionnez des jours ouvrés distincts (lundi = 0, dimanche = 6)."
        )
    try:
        ZoneInfo(values["timezone"])
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise ValueError("Le fuseau horaire IANA est inconnu.")
    opening = time.fromisoformat(str(values["opening_time"]))
    closing = time.fromisoformat(str(values["closing_time"]))
    if opening.tzinfo or closing.tzinfo or opening >= closing:
        raise ValueError(
            "L'heure de fermeture doit suivre l'ouverture dans la même journée."
        )
    holidays = values["holidays"]
    if not isinstance(holidays, list) or len(holidays) > 2000:
        raise ValueError("Le calendrier accepte au maximum 2 000 jours fériés.")
    clean = []
    for item in holidays:
        if not isinstance(item, str):
            raise ValueError("Chaque jour férié doit être une date AAAA-MM-JJ.")
        parsed = date.fromisoformat(item)
        if parsed.isoformat() != item or not 1900 <= parsed.year <= 2200:
            raise ValueError(
                "Chaque jour férié doit être une date AAAA-MM-JJ entre 1900 et 2200."
            )
        clean.append(item)
    if len(set(clean)) != len(clean):
        raise ValueError("Un jour férié ne doit être renseigné qu'une fois.")


def capture_calendar(calendar):
    if calendar is None:
        return {}
    values = {
        name: getattr(calendar, name)
        for name in (
            "timezone",
            "working_days",
            "opening_time",
            "closing_time",
            "holidays",
        )
    }
    validate_calendar(values)
    return {
        "id": str(calendar.pk),
        "code": calendar.code,
        "name": calendar.name,
        "updated_at": calendar.updated_at.isoformat(),
        **values,
        "opening_time": calendar.opening_time.isoformat(),
        "closing_time": calendar.closing_time.isoformat(),
    }


def business_due_at(start, hours, calendar):
    validate_calendar(calendar)
    zone = ZoneInfo(calendar["timezone"])
    opening = time.fromisoformat(calendar["opening_time"])
    closing = time.fromisoformat(calendar["closing_time"])
    holidays = set(calendar["holidays"])
    cursor = start.astimezone(timezone.utc)
    current_date = cursor.astimezone(zone).date()
    remaining = hours * 3600
    # Borne défensive : pas de boucle illimitée sur un calendrier inutilisable.
    for _ in range(36600):
        if (
            current_date.weekday() in calendar["working_days"]
            and current_date.isoformat() not in holidays
        ):
            begin = datetime.combine(current_date, opening, zone).astimezone(
                timezone.utc
            )
            end = datetime.combine(current_date, closing, zone).astimezone(timezone.utc)
            available_from = max(cursor, begin)
            available = max(0, (end - available_from).total_seconds())
            if remaining <= available:
                return available_from + timedelta(seconds=remaining)
            remaining -= available
        current_date += timedelta(days=1)
    raise ValueError("Le délai dépasse la capacité du calendrier ouvré (100 ans).")
