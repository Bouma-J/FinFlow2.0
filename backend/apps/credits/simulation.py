"""Échéanciers configurés : décompte de jours, arrondis et dates ouvrées."""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP, localcontext

from apps.configuration.simulation_catalog import DEFAULT_CONVENTIONS, normalize_conventions


def conventions_for_application(application, configuration=None):
    if configuration is None:
        from apps.configuration.services import application_configuration
        configuration = application_configuration(application)
    return normalize_conventions(configuration.get("simulation", {}).get("conventions", DEFAULT_CONVENTIONS), allow_snapshot=True)


def prepare_setup_schedule(application, start_date):
    """Calcul préalable à l'appel CBS, réutilisé pour créer le prêt local."""
    from .amounts import reference_amount
    from .pricing import quote_pricing
    from .services import _add_periods, _next_business_day, compute_amortization_schedule

    conventions = conventions_for_application(application)
    quote = quote_pricing(application)
    if quote["failures"]:
        raise ValueError(" ".join(quote["failures"]))
    principal = reference_amount(application) or application.amount_requested
    first = application.first_due_date
    if first is None:
        first = _add_periods(start_date, application.periodicity, 1)
        if conventions["engine"] == "LEGACY":
            first = _next_business_day(first)
    rows = compute_amortization_schedule(
        principal, quote["rates"]["interest_rate"], application.duration_months,
        periodicity=application.periodicity, start_date=start_date, first_due_date=first,
        savings_rate=quote["rates"]["mandatory_savings_rate"],
        mechanism=application.repayment_mechanism or "DEGRESSIVE",
        tenant_id=application.tenant_id, conventions=conventions,
    )
    return {"principal": principal, "rate": Decimal(quote["rates"]["interest_rate"]),
            "savings_rate": Decimal(quote["rates"]["mandatory_savings_rate"]),
            "first_due": rows[0]["due_date"] if conventions["engine"] == "CONFIGURED" else first,
            "schedule": rows}


def year_fraction(start, end, convention):
    if end < start:
        raise ValueError("La fin d'une période d'intérêts précède son début.")
    if convention == "30E360":
        days = (end.year - start.year) * 360 + (end.month - start.month) * 30 + min(end.day, 30) - min(start.day, 30)
        return Decimal(days) / Decimal(360)
    if convention not in {"ACT365_FIXED", "ACT360"}:
        raise ValueError("Convention de décompte des jours inconnue.")
    return Decimal((end - start).days) / Decimal(365 if convention == "ACT365_FIXED" else 360)


def adjust_due_date(day, conventions):
    method = conventions["due_adjustment"]
    if method == "NONE":
        return day
    snapshot = conventions.get("calendar_snapshot")
    if not snapshot:
        raise ValueError("Le calendrier ouvré conservé est requis pour ajuster les échéances.")
    days = set(snapshot["working_days"])
    holidays = set(snapshot["holidays"])

    def find(direction):
        candidate = day
        # Un calendrier dont des années entières sont fermées n'autorise pas
        # une boucle sans borne ni un report silencieux sur une autre année.
        for _ in range(367):
            if candidate.weekday() in days and candidate.isoformat() not in holidays:
                return candidate
            candidate += timedelta(days=direction)
        raise ValueError("Aucun jour ouvré trouvé dans les 366 jours autour de l'échéance.")

    if method == "PRECEDING":
        return find(-1)
    following = find(1)
    if method == "MODIFIED_FOLLOWING" and (following.year, following.month) != (day.year, day.month):
        return find(-1)
    return following


def configured_schedule(principal, annual_rate, duration_months, *, periodicity, start_date, first_due_date, savings_rate, mechanism, tenant_id, conventions):
    from .services import _add_periods, period_count

    rules = normalize_conventions(conventions, allow_snapshot=True)
    if periodicity not in {"DAILY", "WEEKLY", "BIMONTHLY", "MONTHLY", "QUARTERLY", "SEMIANNUAL", "ANNUAL"}:
        raise ValueError("Cette périodicité ne dispose pas d'une convention de dates prise en charge.")
    if mechanism not in {"DEGRESSIVE", "CONSTANT", "IN_FINE", "BULLET"}:
        raise ValueError("Mécanisme de remboursement non pris en charge.")
    from .models import _PERIODS_PER_YEAR
    expected_frequency = _PERIODS_PER_YEAR[periodicity]
    frequency = rules.get("periods_per_year", {}).get(periodicity, expected_frequency)
    if frequency != expected_frequency:
        raise ValueError("La fréquence conservée du référentiel ne correspond pas à la convention de dates de cette périodicité.")
    principal, annual_rate, savings_rate = Decimal(principal), Decimal(annual_rate or 0), Decimal(savings_rate or 0)
    if not all(value.is_finite() for value in (principal, annual_rate, savings_rate)) or principal <= 0 or annual_rate < 0 or not Decimal(0) <= savings_rate <= Decimal(100):
        raise ValueError("Capital, taux annuel ou taux d'épargne invalide.")
    # Le référentiel courant ne doit pas réécrire une durée déjà conservée.
    count = period_count(duration_months, periodicity)
    if not 1 <= count <= 20000:
        raise ValueError("Le calcul configuré accepte entre 1 et 20 000 échéances.")
    first = first_due_date or _add_periods(start_date, periodicity, 1)
    if first <= start_date:
        raise ValueError("La première échéance doit suivre la date d'effet.")
    nominal_dates = [_add_periods(first, periodicity, index) for index in range(count)]
    if mechanism == "BULLET":
        nominal_dates = [nominal_dates[-1]]
    due_dates = [adjust_due_date(day, rules) for day in nominal_dates]
    accrual_dates = nominal_dates if rules["interest_dates"] == "NOMINAL" else due_dates
    previous = start_date
    rates = []
    for end in accrual_dates:
        rates.append(annual_rate / Decimal(100) * year_fraction(previous, end, rules["day_count"]))
        previous = end
    step = Decimal(rules["amount_step"])
    rounding = ROUND_HALF_UP if rules["rounding"] == "HALF_UP" else ROUND_HALF_EVEN

    def rounded(value):
        return ((value / step).quantize(Decimal(1), rounding=rounding) * step).quantize(Decimal("0.01"))

    # L'annuité résout exactement les facteurs d'intérêt des dates retenues,
    # y compris une première période irrégulière, avant arrondis monétaires.
    with localcontext() as context:
        context.prec = 40
        discount, denominator = Decimal(1), Decimal(0)
        for rate in rates:
            discount /= Decimal(1) + rate
            denominator += discount
        payment = rounded(principal / denominator)
    savings = rounded(principal * savings_rate / Decimal(100))
    balance, schedule = principal, []
    for index, (nominal, due, rate) in enumerate(zip(nominal_dates, due_dates, rates), 1):
        interest = rounded(balance * rate)
        last = index == len(rates)
        if mechanism in {"IN_FINE", "BULLET"}:
            capital = balance if last else Decimal(0)
        elif last:
            capital = balance
        else:
            if payment <= interest and balance > 0:
                raise ValueError("Le pas d'arrondi ne permet pas d'amortir le capital : réduire ce pas.")
            capital = min(balance, max(Decimal(0), payment - interest))
        balance -= capital
        institution = capital + interest
        schedule.append({"number": index, "nominal_due_date": nominal, "due_date": due,
                         "principal": capital, "interest": interest, "savings": savings,
                         "institution_due": institution, "total": institution + savings, "balance": balance})
    return schedule
