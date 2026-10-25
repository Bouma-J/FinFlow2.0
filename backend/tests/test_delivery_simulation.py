"""Recette des conventions partagées et de la conservation des calendriers."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError

from apps.configuration.simulation_catalog import (
    DEFAULT_CONVENTIONS, resolve_simulation, validate_simulation,
)
from apps.credits.services import compute_amortization_schedule
from apps.credits.simulation import adjust_due_date, year_fraction


def rules(**changes):
    return deepcopy(DEFAULT_CONVENTIONS) | {"engine": "CONFIGURED"} | changes


def schedule(**changes):
    kwargs = {"principal": "100000", "annual_rate": "12", "duration_months": 12,
              "start_date": date(2026, 1, 1), "conventions": rules()}
    kwargs.update(changes)
    return compute_amortization_schedule(**kwargs)


def calendar_rules(**changes):
    identifier = str(uuid4())
    return rules(calendar=identifier, calendar_snapshot={"id": identifier, "name": "Calendrier validé", "working_days": [0, 1, 2, 3, 4], "holidays": ["2026-08-31"]}, **changes)


@pytest.mark.parametrize("day_count,expected", [("ACT365_FIXED", Decimal(29) / 365), ("ACT360", Decimal(29) / 360), ("30E360", Decimal(30) / 360)])
def test_leap_year_day_count(day_count, expected):
    assert year_fraction(date(2024, 2, 1), date(2024, 3, 1), day_count) == expected


def test_30e360_is_eurobond_not_isda_end_of_february():
    assert year_fraction(date(2026, 1, 31), date(2026, 2, 28), "30E360") == Decimal(28) / 360
    assert year_fraction(date(2026, 1, 31), date(2026, 3, 31), "30E360") == Decimal(60) / 360


@pytest.mark.parametrize("mechanism", ["DEGRESSIVE", "CONSTANT", "IN_FINE", "BULLET"])
@pytest.mark.parametrize("day_count", ["ACT365_FIXED", "ACT360", "30E360"])
def test_every_mechanism_reconciles_principal_and_costs(mechanism, day_count):
    rows = schedule(principal="123456.78", mechanism=mechanism, savings_rate="2.5", conventions=rules(day_count=day_count))
    assert sum(row["principal"] for row in rows) == Decimal("123456.78")
    assert rows[-1]["balance"] == 0
    assert all(row["balance"] >= 0 and row["interest"] >= 0 for row in rows)
    assert all(row["institution_due"] == row["principal"] + row["interest"] for row in rows)
    assert all(row["total"] == row["institution_due"] + row["savings"] for row in rows)
    if mechanism == "BULLET":
        assert len(rows) == 1


def test_zero_interest_and_final_residual_are_exact():
    rows = schedule(principal="1000.00", annual_rate="0")
    assert rows[0]["principal"] == Decimal("83.33")
    assert rows[-1]["principal"] == Decimal("83.37")
    assert sum(row["interest"] for row in rows) == 0


def test_rounding_cannot_silently_turn_amortizing_loan_into_in_fine():
    with pytest.raises(ValueError, match="amortir"):
        schedule(principal="1000", annual_rate="0", duration_months=12, conventions=rules(amount_step="1000"))


@pytest.mark.django_db
def test_periodicity_frequency_is_frozen_and_incoherent_mapping_refused(tenant_a):
    from apps.catalog.models import LoanPeriodicity
    item = LoanPeriodicity.all_tenants.create(tenant=tenant_a, code="MONTHLY", label="Mensuelle", periods_per_year=12)
    snapshot = resolve_simulation(tenant_a.pk, {"conventions": rules()})
    before = schedule(tenant_id=tenant_a.pk, conventions=snapshot["conventions"])
    item.periods_per_year = 24
    item.save()
    assert schedule(tenant_id=tenant_a.pk, conventions=snapshot["conventions"]) == before
    changed = resolve_simulation(tenant_a.pk, {"conventions": rules()})
    with pytest.raises(ValueError, match="fréquence"):
        schedule(tenant_id=tenant_a.pk, conventions=changed["conventions"])


def test_first_period_uses_effective_dates_in_configured_mode():
    rows = schedule(mechanism="IN_FINE", first_due_date=date(2026, 1, 16), conventions=rules(day_count="ACT360"))
    assert rows[0]["interest"] == Decimal("500.00")  # 100000 × 12% × 15/360


def test_rounding_is_explicit():
    options = {"principal": "1000", "annual_rate": "5", "duration_months": 1, "start_date": date(2026, 1, 1), "first_due_date": date(2026, 4, 1), "mechanism": "IN_FINE"}
    up = schedule(**options, conventions=rules(day_count="ACT360", amount_step="1", rounding="HALF_UP"))
    even = schedule(**options, conventions=rules(day_count="ACT360", amount_step="1", rounding="HALF_EVEN"))
    assert up[0]["interest"] == 13
    assert even[0]["interest"] == 12


@pytest.mark.parametrize("adjustment,expected", [("FOLLOWING", date(2026, 9, 1)), ("MODIFIED_FOLLOWING", date(2026, 8, 28)), ("PRECEDING", date(2026, 8, 28))])
def test_weekend_holiday_and_modified_month_boundary(adjustment, expected):
    assert adjust_due_date(date(2026, 8, 30), calendar_rules(due_adjustment=adjustment)) == expected


def test_interest_can_follow_adjusted_dates():
    base = calendar_rules(due_adjustment="FOLLOWING", day_count="ACT360")
    nominal = schedule(start_date=date(2026, 8, 1), first_due_date=date(2026, 8, 30), duration_months=1, mechanism="IN_FINE", conventions=base)
    adjusted = schedule(start_date=date(2026, 8, 1), first_due_date=date(2026, 8, 30), duration_months=1, mechanism="IN_FINE", conventions=base | {"interest_dates": "ADJUSTED"})
    assert nominal[0]["interest"] == Decimal("966.67")
    assert adjusted[0]["interest"] == Decimal("1033.33")
    assert adjusted[0]["nominal_due_date"] == date(2026, 8, 30)
    assert adjusted[0]["due_date"] == date(2026, 9, 1)


def test_adjustment_cannot_create_negative_first_accrual():
    with pytest.raises(ValueError, match="précède"):
        schedule(start_date=date(2026, 8, 29), first_due_date=date(2026, 8, 30), conventions=calendar_rules(due_adjustment="PRECEDING", interest_dates="ADJUSTED"))


def test_historical_engine_is_identical_when_explicitly_selected():
    values = {"principal": "100000", "annual_rate": "12", "duration_months": 12, "start_date": date(2026, 1, 1), "first_due_date": date(2026, 1, 16)}
    assert compute_amortization_schedule(**values) == compute_amortization_schedule(**values, conventions=DEFAULT_CONVENTIONS)


@pytest.mark.parametrize("changes", [{"day_count": "ACTACT"}, {"amount_step": "NaN"}, {"amount_step": "0"}, {"amount_step": "0.001"}, {"rounding": "UP"}, {"calendar": "inventé"}, {"due_adjustment": "FOLLOWING"}, {"calendar_snapshot": {}}])
def test_unknown_unsafe_or_forged_conventions_rejected(changes):
    with pytest.raises(ValidationError):
        validate_simulation({"conventions": rules(**changes)})


@pytest.mark.django_db
def test_calendar_snapshot_is_tenant_scoped_and_immutable(tenant_a, tenant_b):
    from apps.workflow.models import BusinessCalendar
    calendar = BusinessCalendar.all_tenants.create(tenant=tenant_a, code="SIM", name="Calendrier", working_days=[0, 1, 2, 3, 4], holidays=["2026-08-31"])
    raw = {"conventions": rules(calendar=str(calendar.pk), due_adjustment="FOLLOWING")}
    with pytest.raises(ValidationError, match="filiale"):
        resolve_simulation(tenant_b.pk, raw)
    snapshot = resolve_simulation(tenant_a.pk, raw)
    calendar.holidays = []
    calendar.is_active = False
    calendar.save()
    assert snapshot["conventions"]["calendar_snapshot"]["holidays"] == ["2026-08-31"]
    assert adjust_due_date(date(2026, 8, 30), snapshot["conventions"]) == date(2026, 9, 1)
    with pytest.raises(ValidationError, match="actif"):
        resolve_simulation(tenant_a.pk, raw)


def test_calculation_rejects_unknown_periodicity_instead_of_guessing():
    with pytest.raises(ValueError, match="périodicité"):
        schedule(periodicity="CUSTOM_CBS_ONLY")


@pytest.mark.django_db
def test_financial_capacity_uses_exact_same_conventions(tenant_a, product_a, client_a):
    from apps.common.tenancy import tenant_context
    from apps.configuration.services import resolve_context
    from apps.credits.models import CreditApplication, FinancialAnalysis
    with tenant_context(tenant_a.pk):
        app = CreditApplication.objects.create(tenant=tenant_a, client=client_a, product=product_a, amount_requested=Decimal("100000"), interest_rate=Decimal("12"), duration_months=12, first_due_date=date(2026, 2, 1))
        config = resolve_context(tenant_a.pk, {"product": str(product_a.pk)})
        config["captured_at"] = "2026-01-01T00:00:00+00:00"
        config["simulation"] = {"conventions": rules(day_count="ACT360")}
        analysis = FinancialAnalysis(application=app, tenant=tenant_a)
        expected = max(row["institution_due"] for row in schedule(first_due_date=app.first_due_date, conventions=config["simulation"]["conventions"]))
        assert analysis._compute_new_installment(config) == expected


@pytest.mark.django_db
def test_simulation_endpoint_uses_published_conventions(tenant_a, product_a):
    from django.contrib.auth.models import Permission
    from django.utils import timezone
    from rest_framework.test import APIRequestFactory, force_authenticate
    from apps.accounts.models import User
    from apps.common.tenancy import tenant_context
    from apps.configuration.models import ConfigurationProfile
    from apps.credits.views import CreditApplicationViewSet
    actor = User.objects.create_user(username="simulation_reader", tenant=tenant_a, data_scope="TENANT")
    actor.user_permissions.add(Permission.objects.get(content_type__app_label="credits", codename="view_creditapplication"))
    with tenant_context(tenant_a.pk):
        ConfigurationProfile.objects.create(tenant=tenant_a, code="SIM", name="Conventions", status="PUBLISHED", effective_from=timezone.now(), overrides={"simulation": {"conventions": rules(day_count="ACT360")}})
        request = APIRequestFactory().post("/api/credit-applications/simulate/", {"product": str(product_a.pk), "amount": "100000", "annual_rate": "12", "months": 1, "mechanism": "IN_FINE", "simulation_date": "2026-01-01", "first_due_date": "2026-01-16"}, format="json")
        force_authenticate(request, actor)
        response = CreditApplicationViewSet.as_view({"post": "simulate"})(request)
        assert response.status_code == 200, response.data
        assert response.data["schedule"][0]["interest"] == Decimal("500.00")
        assert response.data["simulation_conventions"]["day_count"] == "ACT360"


@pytest.mark.django_db
def test_setup_preflight_prevents_bad_dates_before_cbs_and_reuses_schedule(tenant_a, product_a, client_a, monkeypatch):
    from unittest.mock import Mock
    from apps.accounts.models import User
    from apps.common.tenancy import tenant_context
    from apps.configuration.services import resolve_context
    from apps.credits import services
    from apps.credits.models import CreditApplication, CreditInstructionPolicy
    from apps.workflow.services import WorkflowError
    from apps.credits.simulation import prepare_setup_schedule
    from apps.corebanking import disbursement as cbs_module
    from apps.credits import setup_authorization

    actor = User.objects.create_user(username="setup_unit", tenant=tenant_a, data_scope="TENANT")
    with tenant_context(tenant_a.pk):
        CreditInstructionPolicy.objects.create(tenant=tenant_a, require_setup_request=False, require_setup_four_eyes=False)
        app = CreditApplication.objects.create(tenant=tenant_a, client=client_a, product=product_a, amount_requested=Decimal("100000"), interest_rate=Decimal("12"), duration_months=3, first_due_date=date(2026, 1, 16), status="APPROVED", setup_authorization={"authorized_at": "unit"})
        config = resolve_context(tenant_a.pk, {"product": str(product_a.pk), "client_type": "INDIVIDUAL", "agency": "", "individual_profile": ""})
        config["captured_at"] = "2026-01-01T00:00:00+00:00"
        config["simulation"] = {"conventions": rules(day_count="ACT360")}
        app.configuration_snapshot = config
        app.save(update_fields=["configuration_snapshot"])
        # Ces contrôles sont testés dans la recette gouvernance ; ici seuls
        # l'ordre de calcul et l'absence d'appel externe réel sont concernés.
        monkeypatch.setattr(services, "_assert_disbursement_prerequisites", lambda *args, **kwargs: None)
        monkeypatch.setattr(setup_authorization, "assert_setup_authorization", lambda *args, **kwargs: None)
        cbs = Mock(return_value={"num_contrat": "TEST-ONLY", "raw": {}})
        monkeypatch.setattr(cbs_module, "submit_credit_to_cbs", cbs)
        with pytest.raises(WorkflowError, match="avant transmission"):
            services.disburse_application(app, disburse_date=date(2026, 2, 1), user=actor)
        cbs.assert_not_called()
        prepared = prepare_setup_schedule(app, date(2026, 1, 1))
        loan = services.disburse_application(app, disburse_date=date(2026, 1, 1), user=actor)
        cbs.assert_called_once()
        installments = list(loan.installments.order_by("number"))
        assert len(installments) == len(prepared["schedule"])
        for saved, computed in zip(installments, prepared["schedule"]):
            assert saved.principal_due == computed["principal"]
            assert saved.interest_due == computed["interest"]
            assert saved.due_date == computed["due_date"]
