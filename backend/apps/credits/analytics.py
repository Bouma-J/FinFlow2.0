"""Calculs d'analyse financière approfondie (contre-analyse) et scoring.

Regroupe l'ensemble des indicateurs dérivés (ratios de structure, de rotation,
de liquidité, rentabilité, stress test, quotité cessible) ainsi que la grille
de scoring pondérée. Les seuils utilisés proviennent de la filiale
(``AnalysisThreshold``) et restent donc paramétrables.
"""
from decimal import Decimal, InvalidOperation

Q2 = Decimal("0.01")

PERIODS_PER_YEAR = {
    "MONTHLY": Decimal("12"),
    "QUARTERLY": Decimal("4"),
    "ANNUAL": Decimal("1"),
}


def _dec(value):
    if value is None:
        return Decimal("0")
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _div(num, den):
    """Division tolérante : renvoie None si dénominateur nul."""
    num, den = _dec(num), _dec(den)
    if den == 0:
        return None
    return num / den


def _q(value):
    if value is None:
        return None
    try:
        return Decimal(value).quantize(Q2)
    except (InvalidOperation, TypeError, ValueError):
        return None


def _pct(num, den):
    r = _div(num, den)
    return r * Decimal("100") if r is not None else None


def _score_high(value, bad, good):
    """0 si <= bad, 100 si >= good, linéaire entre les deux (plus haut = mieux)."""
    if value is None:
        return None
    value, bad, good = _dec(value), _dec(bad), _dec(good)
    if good == bad:
        return Decimal("100") if value >= good else Decimal("0")
    ratio = (value - bad) / (good - bad) * Decimal("100")
    return max(Decimal("0"), min(Decimal("100"), ratio))


def _score_low(value, good, bad):
    """100 si <= good, 0 si >= bad, linéaire entre les deux (plus bas = mieux)."""
    if value is None:
        return None
    value, good, bad = _dec(value), _dec(good), _dec(bad)
    if bad == good:
        return Decimal("100") if value <= good else Decimal("0")
    ratio = (bad - value) / (bad - good) * Decimal("100")
    return max(Decimal("0"), min(Decimal("100"), ratio))


def guarantee_coverage(analysis, thresholds=None):
    """Couverture (%) du crédit par la valeur retenue des garanties ACTIVE."""
    from .collateral import guarantee_coverage_retained

    return guarantee_coverage_retained(analysis, thresholds=thresholds)


def compute_metrics(analysis, th, configuration=None, *, recalculate_installment=False):
    """Renvoie l'ensemble des indicateurs dérivés + les drapeaux de conformité."""
    from apps.configuration.services import application_configuration
    configuration = configuration if configuration is not None else application_configuration(analysis.application, individual_profile=analysis.individual_profile)
    if recalculate_installment or (configuration.get("schema_version", 1) >= 3 and not configuration.get("legacy")):
        from copy import copy
        analysis = copy(analysis)
        analysis.new_installment = analysis._compute_new_installment(configuration=configuration)
    stress = _dec(th.stress_pct) / Decimal("100")
    ppy = PERIODS_PER_YEAR.get(analysis.reference_period, Decimal("12"))

    # Toute l'évaluation de capacité est ramenée au mois. L'échéance brute
    # reste disponible séparément pour garder la lecture du contrat.
    installment = _dec(analysis.monthly_new_installment)
    existing = _dec(analysis.existing_debt_monthly)
    global_service = installment + existing
    known_installment = analysis.new_installment is not None
    from .analysis_details import detail_amount
    schedule = getattr(analysis, "_financial_schedule", None) or []
    savings = max((_dec(row.get("savings")) for row in schedule), default=Decimal("0"))
    factor = installment / _dec(analysis.new_installment) if _dec(analysis.new_installment) else Decimal("1")
    monthly_savings = savings * factor
    total_effort = global_service + monthly_savings

    m = {}
    m["installment"] = _q(installment)
    m["contractual_installment"] = _q(analysis.new_installment)
    m["existing_debt_monthly"] = _q(existing)
    m["global_debt_service"] = _q(global_service)
    m["monthly_savings"] = _q(monthly_savings)
    m["calculation_rates"] = getattr(analysis, "_financial_rates", {})
    m["total_cash_effort"] = _q(total_effort)
    m["peak_cash_payment"] = _q(max((_dec(row.get("total", _dec(row.get("principal")) + _dec(row.get("interest")))) for row in schedule), default=None))
    m["average_monthly_cash_payment"] = _q(sum((_dec(row.get("total", _dec(row.get("principal")) + _dec(row.get("interest")))) for row in schedule), Decimal("0")) / Decimal(analysis.application.duration_months)) if schedule and analysis.application.duration_months else None
    m["guarantee_coverage"] = _q(guarantee_coverage(analysis, th))

    flags = {}

    if analysis.is_corporate:
        gross_margin = analysis.gross_margin
        cash_flow = analysis.cash_flow
        monthly_cash_flow = analysis.monthly_cash_flow
        # Pont explicite du résultat vers un flux récurrent avant service dette.
        before_debt = (cash_flow + _dec(analysis.financial_charges)
                       - detail_amount(analysis, "exceptional_income") + detail_amount(analysis, "exceptional_expense")
                       - detail_amount(analysis, "bfr_change") - detail_amount(analysis, "maintenance_investment")) * ppy / Decimal("12")
        annual_turnover = _dec(analysis.turnover) * ppy
        annual_cogs = _dec(analysis.cogs) * ppy
        annual_net = analysis.net_result * ppy

        current_assets = (
            _dec(analysis.stock_value) + _dec(analysis.receivables)
            + analysis.effective_cash_available
            + _dec(analysis.other_current_assets)
        )
        current_liabilities = (
            _dec(analysis.supplier_debt) + _dec(analysis.short_term_debt)
            + _dec(analysis.tax_social_debt) + _dec(analysis.other_current_debt)
            + max(Decimal("0"), _dec(analysis.ongoing_credit_balance) - _dec(analysis.long_term_debt))
        )
        bfr = analysis.bfr
        fr = (
            analysis.equity + _dec(analysis.long_term_debt)
            + _dec(analysis.shareholder_debt)
            - analysis.effective_fixed_assets
        )
        treasury_net = fr - bfr
        has_forecast = (
            _dec(analysis.projected_monthly_inflows) != 0
            or _dec(analysis.projected_monthly_outflows) != 0
        )
        forecast_surplus = analysis.projected_monthly_surplus
        repayment_cash_flow = (
            min(before_debt, forecast_surplus)
            if has_forecast else before_debt
        )
        purchase_shock = _dec(analysis.cogs) * ppy / 12 * detail_amount(analysis, "purchase_stress_pct") / 100
        collection_shock = annual_turnover / 360 * detail_amount(analysis, "receivable_delay_days")
        stressed_cash_flow = before_debt - _dec(analysis.turnover) * ppy / 12 * stress - purchase_shock - collection_shock
        if has_forecast:
            forecast_stress = (_dec(analysis.projected_monthly_inflows) * (1 - stress)
                               - _dec(analysis.projected_monthly_outflows) - purchase_shock - collection_shock)
            stressed_cash_flow = min(stressed_cash_flow, forecast_stress)

        m.update({
            "monthly_cash_flow": _q(monthly_cash_flow),
            "cash_before_debt": _q(before_debt),
            "repayment_capacity": _q(repayment_cash_flow - existing),
            "annual_cash_flow": _q(cash_flow * ppy),
            "forecast_monthly_surplus": _q(forecast_surplus)
            if has_forecast else None,
            "repayment_cash_flow": _q(repayment_cash_flow),
            "stress_cash_available": _q(stressed_cash_flow),
            "current_assets": _q(current_assets),
            "current_liabilities": _q(current_liabilities),
            "working_capital": _q(fr),
            "bfr": _q(bfr),
            "treasury_net": _q(treasury_net),
            "bfr_days": _q(
                _div(bfr, annual_turnover) * Decimal("360")
                if annual_turnover else None
            ),
            "dso_days": _q(
                _div((_dec(analysis.receivables) + detail_amount(analysis, "opening_receivables", _dec(analysis.receivables))) / 2, annual_turnover) * Decimal("360")
                if annual_turnover else None
            ),
            "dpo_days": _q(
                _div((_dec(analysis.supplier_debt) + detail_amount(analysis, "opening_supplier_debt", _dec(analysis.supplier_debt))) / 2,
                     detail_amount(analysis, "period_purchases", _dec(analysis.cogs)) * ppy) * Decimal("360")
                if detail_amount(analysis, "period_purchases", _dec(analysis.cogs)) > 0 else None
            ),
            "dio_days": _q(
                _div((_dec(analysis.stock_value) + detail_amount(analysis, "opening_stock", _dec(analysis.stock_value))) / 2, annual_cogs) * Decimal("360")
                if annual_cogs else None
            ),
            "current_ratio": _q(_div(current_assets, current_liabilities)),
            "quick_ratio": _q(
                _div(current_assets - _dec(analysis.stock_value),
                     current_liabilities)
            ),
            "financial_autonomy": _q(_pct(analysis.equity, analysis.total_assets)),
            "gearing": _q(_div(_dec(analysis.ongoing_credit_balance), analysis.equity))
            if analysis.equity > 0 else None,
            "solvency_ratio": _q(_pct(analysis.total_debts,
                                        analysis.total_assets)),
            "interest_coverage": _q(_div(analysis.ebe,
                                         _dec(analysis.financial_charges))),
            "roe": _q(_pct(annual_net, analysis.equity)) if analysis.equity > 0 else None,
            "roa": _q(_pct(annual_net, analysis.total_assets)),
            "dscr": _q(_div(repayment_cash_flow, installment)),
            "global_dscr": _q(_div(repayment_cash_flow, global_service)),
            "dscr_stress": _q(_div(stressed_cash_flow, global_service)),
            "turnover_growth": _q(
                _pct(_dec(analysis.turnover) - _dec(analysis.turnover_prev),
                     analysis.turnover_prev)
                if _dec(analysis.turnover_prev) else None
            ),
            "result_growth": _q(
                _pct(analysis.net_result - _dec(analysis.net_result_prev),
                     abs(_dec(analysis.net_result_prev)))
                if _dec(analysis.net_result_prev) else None
            ),
            "safety_margin": _q(repayment_cash_flow - total_effort),
            "equity_gap": _q(analysis.equity - detail_amount(analysis, "declared_equity")) if detail_amount(analysis, "declared_equity", None) is not None else None,
        })

        # Point mort (seuil de rentabilité) sur charges fixes / taux de marge.
        gm_rate = _div(gross_margin, analysis.turnover)
        fixed_costs = (
            analysis.total_operating_expenses + _dec(analysis.depreciation)
            + _dec(analysis.financial_charges)
        )
        m["break_even_estimate"] = _q(
            _div(fixed_costs, gm_rate) if gm_rate else None
        )
        fixed = detail_amount(analysis, "fixed_operating_costs", None)
        variable = detail_amount(analysis, "variable_operating_costs", None)
        costs_reconciled = abs(fixed + variable - analysis.total_operating_expenses) <= Decimal("0.01") if fixed is not None and variable is not None else None
        contribution = _dec(analysis.turnover) - _dec(analysis.cogs) - (variable or 0)
        contribution_rate = _div(contribution, analysis.turnover)
        m["fixed_costs_reconciled"] = costs_reconciled
        m["break_even_turnover"] = _q(_div(fixed + _dec(analysis.depreciation) + _dec(analysis.financial_charges), contribution_rate)) if costs_reconciled and contribution_rate and contribution_rate > 0 else None

        flags = {
            "capacity_ok": repayment_cash_flow > 0 and repayment_cash_flow >= total_effort,
            "dscr_ok": _cmp_ge(m["global_dscr"], th.min_dscr),
            "dscr_stress_ok": _cmp_ge(m["dscr_stress"], th.min_dscr),
            "leverage_ok": _cmp_le(m["solvency_ratio"], th.max_leverage_ratio),
            "gearing_ok": _cmp_le(m["gearing"], th.max_gearing),
            "autonomy_ok": _cmp_ge(m["financial_autonomy"],
                                   th.min_financial_autonomy),
            "current_ratio_ok": _cmp_ge(m["current_ratio"], th.min_current_ratio),
            "interest_coverage_ok": _cmp_ge(m["interest_coverage"],
                                            th.min_interest_coverage),
            "guarantee_ok": _cmp_ge(m["guarantee_coverage"],
                                    th.min_guarantee_coverage),
        }
    elif analysis.is_groupement:
        collective_income = (
            _dec(analysis.collective_contributions)
            + _dec(analysis.collective_other_income)
            + _dec(analysis.group_activity_turnover)
        ) * ppy / Decimal("12")
        collective_charges = (
            _dec(analysis.collective_operating_expenses)
            + _dec(analysis.group_activity_expenses)
        ) * ppy / Decimal("12")
        net_capacity = analysis.monthly_collective_capacity - existing
        stressed = collective_income * (Decimal("1") - stress)

        m.update({
            "collective_income": _q(collective_income),
            "collective_charges": _q(collective_charges),
            "collective_capacity": _q(analysis.monthly_collective_capacity),
            "collective_net_capacity": _q(net_capacity),
            "income_positive": collective_income > 0,
            "stress_income_positive": stressed > 0,
            "repayment_capacity": _q(net_capacity),
            "global_dscr": _q(_div(analysis.monthly_collective_capacity, global_service)),
            "debt_ratio": _q(_pct(global_service, collective_income)) if collective_income > 0 else None,
            "debt_ratio_stress": _q(_pct(global_service, stressed)) if stressed > 0 else None,
            "safety_margin": _q(net_capacity - installment - monthly_savings),
            "stress_residual": _q(stressed - collective_charges - total_effort),
            "members_count": analysis.members_count,
            "active_contributing_members": analysis.active_contributing_members,
            "solidarity_commitment": analysis.solidarity_commitment,
            "members_with_arrears": analysis.members_with_arrears,
        })
        concentration = None
        if analysis.members_count and analysis.active_contributing_members is not None:
            concentration = _pct(
                analysis.active_contributing_members, analysis.members_count
            )
        m["contribution_concentration"] = _q(concentration)
        arrears_rate = None
        if analysis.members_count and analysis.members_with_arrears is not None:
            arrears_rate = _pct(
                analysis.members_with_arrears, analysis.members_count
            )
        m["members_arrears_rate"] = _q(arrears_rate)

        flags = {
            "debt_ratio_ok": _cmp_le(m["debt_ratio"], th.max_debt_ratio) if collective_income > 0 else False,
            "debt_ratio_stress_ok": _cmp_le(
                m["debt_ratio_stress"], th.max_debt_ratio
            ) if stressed > 0 else False,
            "capacity_ok": net_capacity > 0 and net_capacity >= installment + monthly_savings,
            "capacity_stress_ok": stressed - collective_charges >= total_effort and stressed > collective_charges,
            "members_ok": bool(
                analysis.members_count and analysis.members_count > 0
            ),
            "solidarity_ok": analysis.solidarity_commitment,
            "contributors_ok": analysis.active_contributing_members > 0 if analysis.active_contributing_members is not None else None,
            "guarantee_ok": _cmp_ge(
                m["guarantee_coverage"], th.min_guarantee_coverage
            ),
        }
    else:
        income = analysis.monthly_total_income
        stable_income = (
            _dec(analysis.salary_income) + _dec(analysis.spouse_income)
            + _dec(analysis.rental_income) + _dec(analysis.pension_income)
        ) * ppy / Decimal("12")
        weight = analysis.informal_income_weight
        weight = _dec(weight) if weight is not None else _dec(th.informal_income_weight)
        weighted_income = stable_income + (
            _dec(analysis.other_activity_income) + _dec(analysis.other_income)
            + _dec(analysis.variable_income)
        ) * ppy / Decimal("12") * weight / Decimal("100")
        if analysis.has_side_activity:
            weighted_income += (analysis.monthly_activity_net * weight / Decimal("100")
                                if analysis.monthly_activity_net >= 0 else analysis.monthly_activity_net)

        stressed_income = weighted_income - max(Decimal("0"), weighted_income) * stress
        if analysis.has_side_activity:
            activity_loss = (_dec(analysis.activity_turnover) * stress
                             + _dec(analysis.activity_purchases) * detail_amount(analysis, "purchase_stress_pct") / 100) * ppy / 12
            activity_stressed = analysis.monthly_activity_net - activity_loss
            activity_retained = analysis.monthly_activity_net * weight / 100 if analysis.monthly_activity_net >= 0 else analysis.monthly_activity_net
            activity_stressed_retained = activity_stressed * weight / 100 if activity_stressed >= 0 else activity_stressed
            stressed_income = weighted_income - activity_retained - max(Decimal("0"), weighted_income - activity_retained) * stress + activity_stressed_retained
        frac = _dec(th.transferable_quota_fraction) / Decimal("100")
        monthly_net_salary = _dec(analysis.net_salary) * ppy / Decimal("12")
        monthly_salary_deductions = (
            _dec(analysis.salary_deductions) * ppy / Decimal("12")
        )
        quota_amount = monthly_net_salary * frac
        quota_available = quota_amount - monthly_salary_deductions

        m.update({
            "income_positive": weighted_income > 0,
            "stress_income_positive": stressed_income > 0,
            "income_weight": _q(weight),
            "household_charges_monthly": _q(analysis.monthly_household_charges),
            "declared_disposable_before_loan": _q(analysis.disposable_income),
            "repayment_capacity": _q(weighted_income - analysis.monthly_household_charges - existing),
            "stress_residual": _q(stressed_income - analysis.monthly_household_charges - total_effort),
            "weighted_income": _q(weighted_income),
            "activity_net": _q(analysis.monthly_activity_net)
            if analysis.has_side_activity else None,
            "declared_income": _q(income),
            "residual_after_loan": _q(
                weighted_income - analysis.monthly_household_charges - total_effort
            ),
            "debt_ratio": _q(_pct(global_service, weighted_income)) if weighted_income > 0 else None,
            "debt_ratio_weighted": _q(_pct(global_service, weighted_income)) if weighted_income > 0 else None,
            "debt_ratio_stress": _q(_pct(global_service, stressed_income)) if stressed_income > 0 else None,
            "transferable_quota_amount": _q(quota_amount),
            "transferable_quota_available": _q(quota_available),
            "safety_margin": _q(
                weighted_income - analysis.monthly_household_charges - total_effort
            ),
            "disposable_per_capita": _q(
                _div(
                    weighted_income - analysis.monthly_household_charges - total_effort,
                    Decimal(analysis.dependents_count) + Decimal("1"),
                )
            ) if analysis.dependents_count is not None else None,
        })

        flags = {
            "debt_ratio_ok": _cmp_le(m["debt_ratio"], th.max_debt_ratio) if weighted_income > 0 else False,
            "debt_ratio_stress_ok": _cmp_le(m["debt_ratio_stress"],
                                            th.max_debt_ratio) if stressed_income > 0 else False,
            "disposable_ok": weighted_income - analysis.monthly_household_charges - total_effort >= 0 and weighted_income > 0,
            "capacity_ok": weighted_income - analysis.monthly_household_charges >= total_effort and weighted_income > 0,
            "capacity_stress_ok": stressed_income - analysis.monthly_household_charges >= total_effort and stressed_income > 0,
            "living_wage_ok": (
                _cmp_ge(m["disposable_per_capita"], th.min_living_wage_per_capita)
                if _dec(th.min_living_wage_per_capita) > 0 else None
            ),
            "quota_ok": (
                installment <= quota_available
                if monthly_net_salary > 0 else None
            ),
            "guarantee_ok": _cmp_ge(m["guarantee_coverage"],
                                    th.min_guarantee_coverage),
        }

    if not analysis.is_corporate and m.get("income_positive") is False:
        flags["debt_ratio_stress_ok"] = False
    if not known_installment:
        for key in ("installment", "monthly_savings", "global_debt_service", "total_cash_effort", "safety_margin", "residual_after_loan", "disposable_per_capita", "debt_ratio", "debt_ratio_weighted", "debt_ratio_stress", "dscr", "global_dscr", "dscr_stress", "stress_residual"):
            m[key] = None
        for key in ("capacity_ok", "disposable_ok", "capacity_stress_ok", "debt_ratio_ok", "debt_ratio_stress_ok", "dscr_ok", "dscr_stress_ok", "living_wage_ok", "quota_ok"):
            if key in flags:
                flags[key] = None
    m["installment_known"] = known_installment
    m["flags"] = flags
    m["information_quality_score"] = _information_quality_score(analysis)
    from .analysis_details import detail_metrics

    m.update(detail_metrics(analysis))
    if m.get("forecast_rows") and schedule:
        expected = {}
        for row in schedule:
            month = row["due_date"].isoformat()[:7]
            expected[month] = expected.get(month, Decimal("0")) + _dec(row.get("total", _dec(row.get("principal")) + _dec(row.get("interest"))))
        for row in m["forecast_rows"]:
            row["expected_new_service"] = expected.get(row["month"], Decimal("0"))
            row["service_gap"] = row["new_service"] - row["expected_new_service"]
        m["forecast_service_reconciled"] = all(abs(row["service_gap"]) <= Decimal("0.01") for row in m["forecast_rows"])
    if analysis.is_individual and analysis.has_side_activity:
        assets = sum((_dec(getattr(analysis, key)) for key in ("activity_stock_value", "activity_receivables", "activity_cash_available", "activity_fixed_assets")), Decimal("0"))
        m.update({"activity_assets": _q(assets), "activity_working_capital_need": _q(_dec(analysis.activity_stock_value) + _dec(analysis.activity_receivables) - _dec(analysis.activity_supplier_debt)),
                  "activity_net_margin_pct": _q(_pct(analysis.activity_net, analysis.activity_turnover)) if _dec(analysis.activity_turnover) > 0 else None})
    return m


def _cmp_ge(value, threshold):
    if value is None:
        return None
    return _dec(value) >= _dec(threshold)


def _cmp_le(value, threshold):
    if value is None:
        return None
    return _dec(value) <= _dec(threshold)


def _history_score(analysis):
    """Score historique (0-100) : incidents, taux de remboursement, retards."""
    score = Decimal("100")
    if analysis.has_payment_incidents:
        score -= Decimal("40")
    rate = analysis.prior_repayment_rate
    if rate is not None:
        # Un taux < 100 % pénalise proportionnellement.
        score = min(score, _dec(rate))
    delay = analysis.prior_max_delay_days or analysis.max_days_late
    if delay:
        score -= min(Decimal("40"), _dec(delay))
    return max(Decimal("0"), min(Decimal("100"), score))


def _information_quality_score(analysis):
    """Apprécie la traçabilité sans transformer une pièce manquante en refus.

    Les coefficients restent internes et le score est un outil d'aide à la
    décision : l'établissement conserve ses seuils et son jugement de crédit.
    """
    base = {
        "DECLARED": Decimal("30"),
        "PARTIALLY_VERIFIED": Decimal("55"),
        "VERIFIED": Decimal("80"),
        "AUDITED": Decimal("100"),
    }.get(getattr(analysis, "information_quality", ""), Decimal("30"))
    checks = [
        getattr(analysis, "financial_documents_verified", False),
        getattr(analysis, "field_visit_confirmed", False),
    ]
    if analysis.is_corporate or analysis.has_side_activity:
        checks.extend([
            getattr(analysis, "stock_count_verified", False),
            getattr(analysis, "cash_position_verified", False),
        ])
    if checks:
        base = max(base, Decimal(sum(bool(value) for value in checks))
                   / Decimal(len(checks)) * Decimal("100"))
    return min(Decimal("100"), base)


def compute_score(analysis, m, th, *, grid=None):
    """Grille de scoring pondérée → (score /100, détail par composante)."""
    from .scoring import compute_custom_score, scoring_grid

    grid = grid if grid is not None else scoring_grid(analysis)
    if grid["engine"] == "CUSTOM":
        return compute_custom_score(analysis, m, grid)
    parts = []

    guarantee_s = _score_high(
        m.get("guarantee_coverage"),
        bad=Decimal("50"),
        good=_dec(th.min_guarantee_coverage) * Decimal("1.2"),
    )
    history_s = _history_score(analysis)

    if analysis.is_corporate:
        capacity_s = _score_high(m.get("global_dscr"), bad=Decimal("1"),
                                 good=_dec(th.min_dscr) * Decimal("1.6"))
        debt_s = _score_low(m.get("gearing"), good=Decimal("0.5"),
                            bad=_dec(th.max_gearing))
        if analysis.equity <= 0:
            debt_s = Decimal("0")
        autonomy_s = _score_high(m.get("financial_autonomy"), bad=Decimal("0"),
                                 good=_dec(th.min_financial_autonomy) * Decimal("2"))
        liquidity_s = _score_high(m.get("current_ratio"), bad=Decimal("0.5"),
                                  good=_dec(th.min_current_ratio) * Decimal("1.5"))
        structure_s = _avg([autonomy_s, liquidity_s])
        parts = [
            ("capacity", "Capacité de remboursement (DSCR)", capacity_s, 30),
            ("debt", "Endettement / gearing", debt_s, 20),
            ("structure", "Structure financière", structure_s, 20),
            ("guarantee", "Garanties réelles", guarantee_s, 15),
            ("history", "Historique de remboursement", history_s, 15),
        ]
    elif analysis.is_groupement:
        capacity_s = _score_low(
            m.get("debt_ratio"),
            good=_dec(th.max_debt_ratio) * Decimal("0.5"),
            bad=_dec(th.max_debt_ratio) * Decimal("1.25"),
        )
        debt_s = _score_low(
            m.get("debt_ratio_stress"),
            good=_dec(th.max_debt_ratio) * Decimal("0.6"),
            bad=_dec(th.max_debt_ratio) * Decimal("1.4"),
        )
        solidarity_s = (
            Decimal("100") if analysis.solidarity_commitment else Decimal("40")
        )
        concentration = m.get("contribution_concentration")
        concentration_s = _score_high(
            concentration, bad=Decimal("20"), good=Decimal("80")
        )
        arrears_s = _score_low(
            m.get("members_arrears_rate"), good=Decimal("0"), bad=Decimal("25")
        )
        structure_s = _avg([solidarity_s, concentration_s, arrears_s])
        parts = [
            ("capacity", "Capacité collective", capacity_s, 35),
            ("debt", "Effort collectif sous stress", debt_s, 20),
            ("structure", "Solidarité & cotisations", structure_s, 15),
            ("guarantee", "Garanties réelles", guarantee_s, 15),
            ("history", "Historique de remboursement", history_s, 15),
        ]
    else:
        capacity_s = _score_low(m.get("debt_ratio"),
                                good=_dec(th.max_debt_ratio) * Decimal("0.5"),
                                bad=_dec(th.max_debt_ratio) * Decimal("1.25"))
        debt_s = _score_low(m.get("debt_ratio_stress"),
                            good=_dec(th.max_debt_ratio) * Decimal("0.6"),
                            bad=_dec(th.max_debt_ratio) * Decimal("1.4"))
        # Stabilité : quotité respectée + ancienneté.
        quota_ok = m.get("flags", {}).get("quota_ok")
        stability_s = Decimal("60")
        if quota_ok is True:
            stability_s = Decimal("100")
        elif quota_ok is False:
            stability_s = Decimal("20")
        seniority = (
            analysis.activity_business_age_months
            if analysis.individual_profile == "INDEPENDANT"
            else analysis.employment_seniority_months
        )
        if seniority is not None:
            stability_s = _avg([
                stability_s,
                _score_high(seniority, bad=Decimal("0"), good=Decimal("24")),
            ])
        parts = [
            ("capacity", "Taux d'effort / reste à vivre", capacity_s, 35),
            ("debt", "Endettement sous stress", debt_s, 20),
            ("stability", "Stabilité & quotité", stability_s, 15),
            ("guarantee", "Garanties réelles", guarantee_s, 15),
            ("history", "Historique de remboursement", history_s, 15),
        ]

    total_weight = Decimal("0")
    # Un taux d'effort faible ne remplace pas la couverture effective du prêt.
    if not analysis.is_corporate and (m.get("income_positive") is False or m.get("flags", {}).get("capacity_ok") is False):
        parts = [(key, label, Decimal("0") if key == "capacity" else value, weight)
                 for key, label, value, weight in parts]
    if not analysis.is_corporate and m.get("stress_income_positive") is False:
        parts = [(key, label, Decimal("0") if key == "debt" else value, weight)
                 for key, label, value, weight in parts]
    weighted = Decimal("0")
    breakdown = []
    for key, label, value, weight in parts:
        w = Decimal(weight)
        if value is None:
            breakdown.append({
                "key": key, "label": label, "score": None, "weight": weight,
            })
            continue
        total_weight += w
        weighted += _dec(value) * w
        breakdown.append({
            "key": key, "label": label,
            "score": float(_dec(value).quantize(Q2)), "weight": weight,
        })

    score = (weighted / total_weight) if total_weight else None
    return (_q(score), {"total": float(_q(score)) if score is not None else None,
                        "components": breakdown, "engine": "LEGACY", "risk_cutoffs": grid["risk_cutoffs"],
                        "missing_data": "RENORMALIZE", "missing_metrics": [part["label"] for part in breakdown if part["score"] is None],
                        "effective_weight": float(total_weight)})


def _avg(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return sum(vals, Decimal("0")) / Decimal(len(vals))
