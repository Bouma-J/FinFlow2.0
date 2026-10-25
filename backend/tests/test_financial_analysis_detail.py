"""Régressions : périodes, bilan et reconstitution des engagements."""
from decimal import Decimal

import pytest
from rest_framework.exceptions import ValidationError

from apps.common.tenancy import tenant_context
from apps.credits.analysis_details import validate_details, detail_metrics
from apps.credits.models import CreditApplication, FinancialAnalysis, AnalysisThreshold
from apps.credits.analytics import compute_metrics
from apps.credits.serializers import FinancialAnalysisSerializer
from django.http import QueryDict
from unittest.mock import patch


@pytest.mark.parametrize("value", [
    {"stocks": [{"quantity": "10", "unit_cost": "20", "impaired_value": "201"}]},
    {"debts": [{"monthly_payment": "NaN"}]},
    {"cashflow": [{"month": "2026-01"}, {"month": "2026-01"}]},
    {"products": [{"quantity": "-1"}]},
])
def test_reject_invalid_reconstitution(value):
    with pytest.raises(ValidationError):
        validate_details(value)


def test_signed_history_and_seasonal_deficit():
    details = validate_details({
        "history": [{"net_result": "-100"}],
        "cashflow": [{"month": "2026-01", "inflows": "100", "outflows": "150"}],
    })
    analysis = FinancialAnalysis(analysis_details=details)
    assert detail_metrics(analysis)["forecast_lowest_flow"] == Decimal("-50")
    assert detail_metrics(analysis)["forecast_lowest_balance"] is None
    assert detail_metrics(analysis)["forecast_deficit_months"] == 1


@pytest.mark.django_db
def test_monthly_capacity_and_weighted_income(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a, client=client_a, product=product_a,
            reference="FA-PERIOD", amount_requested=100000, duration_months=12,
        )
        analysis = FinancialAnalysis.objects.create(
            tenant=tenant_a, application=app, reference_period="ANNUAL",
            salary_income=1200000, other_income=120000, food_expense=240000,
            informal_income_weight=50, existing_debt_monthly=5000,
        )
        assert analysis.repayment_capacity == Decimal("80000")
        assert analysis.disposable_income == Decimal("85000")
        metrics = compute_metrics(analysis, AnalysisThreshold.for_tenant(tenant_a.id))
        assert metrics["weighted_income"] == Decimal("105000")
        analysis.food_expense = 360000
        analysis.save(update_fields=["food_expense"])
        analysis.refresh_from_db()
        assert analysis.repayment_capacity == Decimal("70000")


def test_long_term_debt_is_part_of_total():
    analysis = FinancialAnalysis(
        ongoing_credit_balance=1000, long_term_debt=700,
        supplier_debt=100, tax_social_debt=50, shareholder_debt=20,
    )
    assert analysis.total_debts == Decimal("1170")
    serializer = FinancialAnalysisSerializer()
    with pytest.raises(ValidationError):
        serializer.validate({"long_term_debt": Decimal("1001"), "ongoing_credit_balance": Decimal("1000")})


def test_details_decode_from_multipart_form():
    serializer = FinancialAnalysisSerializer()
    data = QueryDict("analysis_details=%7B%22products%22%3A%5B%7B%22quantity%22%3A%222%22%7D%5D%7D")
    field = serializer.fields["analysis_details"]
    assert field.run_validation(field.get_value(data)) == {"products": [{"quantity": "2"}]}


@pytest.mark.django_db
def test_in_fine_retains_final_installment(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a, client=client_a, product=product_a,
            reference="FA-BULLET", amount_requested=1000, duration_months=12,
        )
        analysis = FinancialAnalysis(tenant=tenant_a, application=app)
        with patch("apps.credits.services.compute_amortization_schedule", return_value=[
            {"principal": Decimal("0"), "interest": Decimal("100")},
            {"principal": Decimal("1000"), "interest": Decimal("100")},
        ]):
            assert analysis._compute_new_installment() == Decimal("1100")


@pytest.mark.django_db
def test_corporate_capacity_annual_to_monthly(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        client_a.client_type = "CORPORATE"
        client_a.save(update_fields=["client_type"])
        app = CreditApplication.objects.create(
            tenant=tenant_a, client=client_a, product=product_a,
            reference="FA-CORP", amount_requested=100000, duration_months=12,
        )
        analysis = FinancialAnalysis.objects.create(
            tenant=tenant_a, application=app, reference_period="ANNUAL",
            turnover=2400000, cogs=1200000, existing_debt_monthly=10000,
            projected_monthly_inflows=100000, projected_monthly_outflows=20000,
        )
        assert analysis.repayment_capacity == Decimal("70000")
        metrics = compute_metrics(analysis, AnalysisThreshold.for_tenant(tenant_a.id))
        assert metrics["monthly_cash_flow"] == Decimal("100000")
        assert metrics["repayment_cash_flow"] == Decimal("80000")
        assert analysis.dscr.quantize(Decimal("0.01")) == metrics["global_dscr"]
