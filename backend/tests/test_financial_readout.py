"""Capacité réelle, restitution courante et historique sans mutation à la lecture."""
from datetime import date
from decimal import Decimal as D
from unittest.mock import patch

import pytest
from rest_framework.exceptions import ValidationError

from apps.configuration.rule_catalog import DEFAULT_GRID
from apps.credits.analysis_details import detail_metrics, validate_details
from apps.credits.analytics import compute_metrics, compute_score
from apps.credits.models import AnalysisThreshold, CreditApplication, FinancialAnalysis
from apps.credits.scoring import compute_custom_score
from apps.credits.serializers import FinancialAnalysisSerializer
from apps.common.tenancy import tenant_context


def calculate(client_type="INDIVIDUAL", **kwargs):
    app = CreditApplication(periodicity="MONTHLY", dependents_count=0, duration_months=12)
    analysis = FinancialAnalysis(application=app, client_type=client_type, reference_period="MONTHLY", **kwargs)
    with patch("apps.credits.analytics.guarantee_coverage", return_value=None):
        return analysis, compute_metrics(analysis, AnalysisThreshold(), configuration={"schema_version": 1, "legacy": True})


def test_loss_never_creates_favourable_ratio_or_capacity_score():
    analysis, metrics = calculate(has_side_activity=True, activity_turnover=D("100000"), activity_expenses=D("160000"), new_installment=D("20000"))
    assert metrics["weighted_income"] == D("-60000")
    assert metrics["debt_ratio"] is None
    assert metrics["flags"]["debt_ratio_ok"] is False
    assert metrics["flags"]["debt_ratio_stress_ok"] is False
    _, breakdown = compute_score(analysis, metrics, AnalysisThreshold(), grid=DEFAULT_GRID)
    assert next(part for part in breakdown["components"] if part["key"] == "capacity")["score"] == 0
    grid = {"criteria": [{"metric": "debt_ratio", "weight": "100", "bad": "50", "good": "20", "direction": "LOW"}],
            "missing_data": "RENORMALIZE", "risk_cutoffs": ["80", "65", "50", "35"]}
    score, _ = compute_custom_score(analysis, metrics, grid)
    assert score == 0


def test_group_capacity_and_contributors_include_zero_and_new_credit():
    analysis, metrics = calculate("PROFESSIONAL", members_count=10, active_contributing_members=0,
        collective_contributions=D("100000"), collective_operating_expenses=D("90000"), new_installment=D("30000"))
    assert metrics["contribution_concentration"] == 0
    assert metrics["flags"]["contributors_ok"] is False
    assert metrics["flags"]["capacity_ok"] is False
    assert metrics["safety_margin"] == D("-20000")
    _, breakdown = compute_score(analysis, metrics, AnalysisThreshold(), grid=DEFAULT_GRID)
    assert breakdown["components"][0]["score"] == 0


def test_individual_residual_includes_new_credit_and_savings():
    analysis, _ = calculate(salary_income=D("200000"), food_expense=D("150000"), existing_debt_monthly=D("10000"), new_installment=D("30000"))
    analysis._financial_schedule = [{"savings": D("20000"), "principal": D("30000"), "interest": D("0"), "total": D("50000"), "due_date": date(2026, 1, 1)}]
    with patch("apps.credits.analytics.guarantee_coverage", return_value=None):
        metrics = compute_metrics(analysis, AnalysisThreshold(), configuration={"legacy": True})
    assert metrics["total_cash_effort"] == D("60000")
    assert metrics["residual_after_loan"] == D("-10000")
    assert metrics["flags"]["disposable_ok"] is False
    assert metrics["flags"]["capacity_ok"] is False


def test_missing_installment_does_not_become_zero_or_positive_capacity():
    _, metrics = calculate(salary_income=D("200000"), new_installment=None)
    assert metrics["installment"] is None
    assert metrics["debt_ratio"] is None
    assert metrics["residual_after_loan"] is None
    assert metrics["flags"]["capacity_ok"] is None


def test_corporate_dscr_adds_back_interest_and_removes_adjustments():
    analysis, metrics = calculate("CORPORATE", turnover=D("1200000"), cogs=D("500000"), op_salaries=D("100000"),
        financial_charges=D("100000"), existing_debt_monthly=D("200000"), new_installment=D("300000"),
        analysis_details={"income_tax_expense": "10000", "bfr_change": "20000", "maintenance_investment": "10000", "provision_expense": "10000", "exceptional_income": "50000"})
    assert analysis.net_result == D("530000")
    assert metrics["cash_before_debt"] == D("560000")
    assert metrics["global_dscr"] == D("1.12")
    assert metrics["repayment_capacity"] == D("360000")


def test_break_even_requires_reconciled_fixed_and_variable_costs():
    _, missing = calculate("CORPORATE", turnover=D("1000"), cogs=D("400"), op_salaries=D("300"), new_installment=D("10"))
    assert missing["break_even_turnover"] is None
    assert missing["break_even_estimate"] == D("500")
    _, known = calculate("CORPORATE", turnover=D("1000"), cogs=D("400"), op_salaries=D("300"), new_installment=D("10"),
        analysis_details={"fixed_operating_costs": "200", "variable_operating_costs": "100"})
    assert known["break_even_turnover"] == D("400")
    assert known["fixed_costs_reconciled"] is True


def test_negative_previous_result_growth_uses_absolute_base():
    _, metrics = calculate("CORPORATE", turnover=D("100"), cogs=D("300"), net_result_prev=D("-100"), new_installment=D("10"))
    assert metrics["result_growth"] == D("-100")


def test_cash_flow_sorts_months_and_carries_opening_balance():
    analysis = FinancialAnalysis(analysis_details={"opening_cash_balance": "0", "cashflow": [
        {"month": "2026-02", "outflows": "100000"}, {"month": "2026-01", "inflows": "500000"},
    ]})
    metrics = detail_metrics(analysis)
    assert metrics["forecast_rows"][0]["month"] == "2026-01"
    assert metrics["forecast_lowest_flow"] == D("-100000")
    assert metrics["forecast_lowest_balance"] == D("400000")
    assert metrics["forecast_negative_flow_months"] == 1
    assert metrics["forecast_cash_deficit_months"] == 0
    assert metrics["forecast_deficit_months"] == 0


@pytest.mark.parametrize("details", [
    {"cashflow": [{"month": "2026-01", "inflows": "100"}]},
    {"opening_cash_balance": "0", "cashflow": [{"month": "2026-01"}, {"month": "2026-03"}]},
    {"opening_cash_balance": "0", "cashflow": [{"inflows": "100"}]},
])
def test_missing_opening_or_month_never_fabricates_cumulative_cash(details):
    metrics = detail_metrics(FinancialAnalysis(analysis_details=details))
    assert metrics["forecast_lowest_balance"] is None
    assert metrics["forecast_cash_deficit_months"] is None


def test_detail_reconciliations_and_product_margin():
    analysis = FinancialAnalysis(client_type="CORPORATE", turnover=D("1000000"), stock_value=D("0"), ongoing_credit_balance=D("1000"), existing_debt_monthly=D("20"),
        analysis_details={"products": [{"quantity": "2", "sale_price": "50000", "unit_cost": "10000"}],
                          "stocks": [{"quantity": "1", "unit_cost": "1000"}], "debts": [{"outstanding": "500", "monthly_payment": "20"}]})
    metrics = detail_metrics(analysis)
    assert metrics["reconstituted_margin"] == D("80000")
    assert metrics["sales_reconciled"] is False
    assert metrics["stock_reconciled"] is False
    assert metrics["outstanding_reconciled"] is False
    assert metrics["debt_service_reconciled"] is True


def test_incomplete_details_never_create_zero_aggregates():
    metrics = detail_metrics(FinancialAnalysis(analysis_details={"products": [{"quantity": "1"}], "stocks": [{}], "debts": [{}]}))
    assert metrics["reconstituted_sales"] is None
    assert metrics["inventory_net_value"] is None
    assert metrics["detailed_debt_monthly"] is None
    assert metrics["debt_service_reconciled"] is False


def test_missing_income_under_stress_is_not_removed_from_score():
    analysis, _ = calculate(salary_income=D("100000"), new_installment=D("10000"))
    with patch("apps.credits.analytics.guarantee_coverage", return_value=None):
        metrics = compute_metrics(analysis, AnalysisThreshold(stress_pct=D("100")), configuration={"legacy": True})
    assert metrics["debt_ratio_stress"] is None
    assert metrics["flags"]["debt_ratio_stress_ok"] is False
    _, breakdown = compute_score(analysis, metrics, AnalysisThreshold(), grid=DEFAULT_GRID)
    assert next(part for part in breakdown["components"] if part["key"] == "debt")["score"] == 0


def test_forecast_new_service_compares_actual_calendar_months():
    analysis, _ = calculate(salary_income=D("100000"), new_installment=D("10000"),
        analysis_details={"opening_cash_balance": "0", "cashflow": [{"month": "2026-01", "new_service": "10000"}]})
    analysis._financial_schedule = [{"savings": D("1000"), "principal": D("10000"), "interest": D("0"), "total": D("11000"), "due_date": date(2026, 1, 15)}]
    with patch("apps.credits.analytics.guarantee_coverage", return_value=None):
        metrics = compute_metrics(analysis, AnalysisThreshold(), configuration={"legacy": True})
    assert metrics["forecast_rows"][0]["expected_new_service"] == D("11000")
    assert metrics["forecast_service_reconciled"] is False


def test_explicit_zero_detail_replaces_historical_assets():
    analysis = FinancialAnalysis(cash_available=D("10000"), fixed_assets=D("50000"),
        analysis_details={"cash_detail_mode": "DETAIL", "fixed_assets_detail_mode": "DETAIL"})
    assert analysis.effective_cash_available == 0
    assert analysis.effective_fixed_assets == 0


@pytest.mark.parametrize("details", [
    {"opening_cash_balance": "NaN"}, {"income_tax_expense": "-1"}, {"purchase_stress_pct": "101"},
    {"cash_detail_mode": "unknown"}, {"bfr_change": "Infinity"}, {"fixed_operating_costs": []},
])
def test_reject_invalid_supplements(details):
    with pytest.raises(ValidationError):
        validate_details(details)


def test_optional_signed_zero_values_remain_distinct_from_unknown():
    assert validate_details({"opening_cash_balance": "-100", "declared_equity": "0", "fixed_operating_costs": ""})["declared_equity"] == "0"


@pytest.mark.django_db
def test_api_current_indicators_are_coherent_and_get_does_not_save(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(tenant=tenant_a, client=client_a, product=product_a, reference="READOUT", amount_requested=100000, duration_months=12)
        analysis = FinancialAnalysis.objects.create(tenant=tenant_a, application=app, salary_income=D("200000"))
        FinancialAnalysis.objects.filter(pk=analysis.pk).update(debt_ratio=D("5"), new_installment=D("10000"))
        analysis.refresh_from_db()
        with patch.object(FinancialAnalysis, "_compute_new_installment", return_value=D("100000")):
            data = FinancialAnalysisSerializer(analysis).data
        assert data["debt_ratio"] == 50
        assert data["metrics"]["debt_ratio"] == data["debt_ratio"]
        assert data["new_installment"] == 100000
        assert data["recorded_indicators"]["debt_ratio"] == 5
        analysis.refresh_from_db()
        assert analysis.debt_ratio == D("5")


@pytest.mark.django_db
def test_reference_selection_is_applied_with_only_one_reference(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(tenant=tenant_a, client=client_a, product=product_a, reference="REF-CHOICE", amount_requested=100000, duration_months=12)
        first = FinancialAnalysis.objects.create(tenant=tenant_a, application=app, salary_income=100000)
        serializer = FinancialAnalysisSerializer(data={"application": str(app.id), "salary_income": "200000", "is_reference": True})
        assert serializer.is_valid(), serializer.errors
        second = serializer.save(tenant=tenant_a)
        first.refresh_from_db()
        assert second.is_reference and not first.is_reference
        assert app.financial_analyses.filter(is_reference=True).count() == 1
