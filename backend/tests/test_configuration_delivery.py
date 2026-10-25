"""Recette des quatre premiers lots, exclusivement sur la base de test en mémoire."""
from copy import deepcopy
from datetime import datetime, time, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.common.tenancy import tenant_context
from apps.configuration.models import ConfigurationProfile
from apps.configuration.pricing_catalog import pricing_defaults, validate_pricing
from apps.configuration.rule_catalog import DEFAULT_GRID, validate_scoring
from apps.configuration.services import (
    active_profiles, application_configuration, context_for, freeze_configuration,
    resolve_context,
)
from apps.credits.eligibility import rule_failures
from apps.credits.models import CreditApplication
from apps.credits.pricing import quote_pricing
from apps.credits.scoring import compute_custom_score
from apps.workflow.calendars import business_due_at, validate_calendar
from apps.workflow.committee import validate_committee
from apps.workflow.models import ApprovalStep, BusinessCalendar, WorkflowDefinition
from apps.workflow.services import WorkflowError, assert_workflow_structure


@pytest.fixture
def dossier(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.pk):
        return CreditApplication.objects.create(
            tenant=tenant_a, client=client_a, product=product_a,
            reference="DELIVERY", amount_requested=Decimal("100000"),
            duration_months=12, currency="XOF",
        )


@pytest.fixture
def config_admin(tenant_a, django_user_model):
    user = django_user_model.objects.create_user(
        username="delivery_admin", tenant=tenant_a, data_scope="TENANT",
    )
    user.user_permissions.add(*Permission.objects.filter(content_type__app_label="configuration"))
    api = APIClient()
    api.force_authenticate(user)
    return user, api


def profile(tenant, code="delivery", **values):
    return ConfigurationProfile.all_tenants.create(
        tenant=tenant, code=code, name=code, reason="Recette", **values,
    )


@pytest.mark.django_db
def test_publication_requires_another_author_and_preserves_immutable_version(
    tenant_a, config_admin, django_user_model,
):
    author, api = config_admin
    response = api.post("/api/v1/configuration-profiles/", {
        "code": "independent", "name": "Independent", "reason": "Recette",
        "overrides": {"analysis": {"minimum_bank_statement_months": 3}},
    }, format="json")
    assert response.status_code == 201, response.content
    url = f"/api/v1/configuration-profiles/{response.data['id']}/"
    assert api.post(url + "submit/", {}, format="json").status_code == 200
    assert api.post(url + "publish/", {}, format="json").status_code == 403
    reviewer = django_user_model.objects.create_user(username="delivery_reviewer", tenant=tenant_a)
    reviewer.user_permissions.add(*Permission.objects.filter(content_type__app_label="configuration"))
    api.force_authenticate(reviewer)
    assert api.post(url + "publish/", {}, format="json").status_code == 200
    response = api.patch(url, {"name": "Rewrite", "expected_updated_at": response.data["updated_at"]}, format="json")
    assert response.status_code == 400
    obj = ConfigurationProfile.all_tenants.get(code="independent")
    assert obj.name == "Independent" and obj.published_by == reviewer
    assert obj.created_by == author


@pytest.mark.django_db
def test_profile_api_isolates_foreign_tenant(config_admin, tenant_b):
    _, api = config_admin
    foreign = profile(tenant_b)
    response = api.get(f"/api/v1/configuration-profiles/{foreign.pk}/")
    assert response.status_code == 404
    response = api.get("/api/v1/configuration-profiles/")
    assert response.status_code == 200
    assert not response.data["results"]


@pytest.mark.django_db
def test_profile_optimistic_lock_rejects_stale_write(tenant_a, config_admin):
    user, api = config_admin
    obj = profile(tenant_a, created_by=user, updated_by=user)
    url = f"/api/v1/configuration-profiles/{obj.pk}/"
    timestamp = obj.updated_at.isoformat()
    response = api.patch(url, {"name": "First", "expected_updated_at": timestamp}, format="json")
    assert response.status_code == 200, response.content
    response = api.patch(url, {"name": "Stale", "expected_updated_at": timestamp}, format="json")
    assert response.status_code == 400
    obj.refresh_from_db()
    assert obj.name == "First"


@pytest.mark.django_db
def test_published_same_scope_is_rejected(tenant_a, config_admin):
    user, api = config_admin
    profile(tenant_a, code="existing", status="PUBLISHED", effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc))
    candidate = profile(tenant_a, code="candidate", status="REVIEW")
    response = api.post(f"/api/v1/configuration-profiles/{candidate.pk}/publish/", {}, format="json")
    assert response.status_code == 400, response.content
    candidate.refresh_from_db()
    assert candidate.status == "REVIEW" and candidate.published_by_id != user.pk


@pytest.mark.django_db
def test_retirement_does_not_reactivate_previous_version(tenant_a):
    stamp = datetime(2025, 1, 1, tzinfo=timezone.utc)
    profile(tenant_a, version=1, status="PUBLISHED", effective_from=stamp)
    profile(tenant_a, version=2, status="RETIRED", effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc), retired_at=datetime(2026, 2, 1, tzinfo=timezone.utc))
    assert active_profiles(tenant_a.pk, at=datetime(2026, 3, 1, tzinfo=timezone.utc)) == []


@pytest.mark.django_db
def test_resolution_prefers_product_to_client_profile_and_ignores_other_tenant(dossier, tenant_b):
    stamp = datetime(2025, 1, 1, tzinfo=timezone.utc)
    common = {"status": "PUBLISHED", "effective_from": stamp}
    profile(dossier.tenant, code="client", client_type="INDIVIDUAL", overrides={"analysis": {"minimum_bank_statement_months": 3}}, **common)
    profile(dossier.tenant, code="product", product=dossier.product, overrides={"analysis": {"minimum_bank_statement_months": 6}}, **common)
    profile(tenant_b, code="foreign", overrides={"analysis": {"minimum_bank_statement_months": 99}}, **common)
    result = resolve_context(dossier.tenant_id, context_for(dossier))
    assert result["analysis"]["minimum_bank_statement_months"] == 6
    assert [row["code"] for row in result["sources"]] == ["client", "product"]


@pytest.mark.django_db
@pytest.mark.parametrize("schema", [1, 2, 3])
def test_historical_capture_is_enriched_without_rewriting_original_fingerprint(dossier, schema):
    result = resolve_context(dossier.tenant_id, context_for(dossier))
    result["schema_version"] = schema
    result["fingerprint"] = f"original-v{schema}"
    if schema == 1:
        for key in ("eligibility", "scoring", "pricing"):
            result.pop(key)
            result["origins"].pop(key)
    elif schema == 2:
        result.pop("pricing")
        result["origins"].pop("pricing")
    dossier.status = "IN_APPROVAL"
    dossier.configuration_snapshot = deepcopy(result)
    rendered = application_configuration(dossier)
    assert rendered["fingerprint"] == f"original-v{schema}"
    assert rendered["frozen"]
    assert rendered["pricing"]["tariff"]["engine"] == "LEGACY"
    assert rendered["eligibility"] == {"rules": []}
    assert dossier.configuration_snapshot == result


@pytest.mark.django_db
def test_frozen_analysis_requirements_are_not_replaced_by_later_profile(dossier):
    freeze_configuration(dossier)
    original = deepcopy(dossier.configuration_snapshot)
    dossier.status = "IN_APPROVAL"
    profile(dossier.tenant, status="PUBLISHED", effective_from=datetime(2025, 1, 1, tzinfo=timezone.utc), overrides={"analysis": {"minimum_bank_statement_months": 9}})
    assert application_configuration(dossier)["analysis"] == original["analysis"]
    assert dossier.configuration_snapshot == original


def configured_pricing(**overrides):
    return {"pricing": {**pricing_defaults(), **validate_pricing({"tariff": {"engine": "CONFIGURED", "currency": "XOF", **overrides}})}, "fingerprint": "recipe"}


def priced_application(**values):
    return SimpleNamespace(status="DRAFT", amount_requested=Decimal("100000"), duration_months=12, currency="XOF", interest_rate=None, fees_rate=None, mandatory_savings_rate=None, **values)


def test_pricing_keeps_explicit_zero_and_uses_configured_defaults():
    app = priced_application()
    app.interest_rate = Decimal("0")
    config = configured_pricing(interest_rate={"default": "12"}, fees_rate={"default": "1"})
    quote = quote_pricing(app, configuration=config, manual_fees=[])
    assert quote["rates"]["interest_rate"] == "0"
    assert quote["rates"]["fees_rate"] == "1"
    assert quote["fees"]["total"] == "1000.00"


def test_pricing_band_fee_floor_cap_and_taxes_are_calculated_exactly():
    config = configured_pricing(
        bands=[{"id": "standard", "min_amount": "100000", "max_amount": "200000", "min_months": 12, "max_months": 24, "interest_rate": "8"}],
        fees_rate={"default": "1"}, processing_tax_rate="18",
        charges=[{"code": "ADMIN", "label": "Frais administratifs", "mode": "PERCENT", "value": "0.5", "min_amount": "700", "max_amount": "900", "tax_rate": "18"}],
    )
    quote = quote_pricing(priced_application(), configuration=config, manual_fees=[])
    assert not quote["failures"]
    assert quote["band"] == "standard" and quote["rates"]["interest_rate"] == "8"
    assert quote["fees"]["total"] == "2006.00"
    assert quote["fees"]["total_taxes"] == "306.00"
    assert quote["fees"]["net_after_fees"] == "97994.00"


@pytest.mark.parametrize("change", [
    {"allow_manual_fees": False}, {"max_total_fees_pct": "0.5"}, {"currency": "EUR"},
])
def test_pricing_reports_manual_cap_and_currency_failures(change):
    quote = quote_pricing(priced_application(), configuration=configured_pricing(**change), manual_fees=[{"label": "Frais", "mode": "AMOUNT", "value": "1000"}])
    assert quote["failures"]


def test_non_negotiable_rate_rejects_explicit_departure():
    app = priced_application()
    app.interest_rate = Decimal("0")
    quote = quote_pricing(app, configuration=configured_pricing(interest_rate={"default": "8", "negotiable": False}), manual_fees=[])
    assert any("obligatoire" in item for item in quote["failures"])


def test_price_bands_overlap_at_inclusive_boundary_is_rejected():
    with pytest.raises(ValidationError, match="chevauchent"):
        configured_pricing(bands=[{"id": "a", "max_amount": "100000"}, {"id": "b", "min_amount": "100000"}])


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "1.0001", True])
def test_invalid_tariff_numbers_are_rejected(value):
    with pytest.raises(ValidationError):
        configured_pricing(interest_rate={"default": value})


@pytest.mark.parametrize("missing, expected", [("RENORMALIZE", "50.00"), ("ZERO", "25.00"), ("BLOCK_SUBMIT", None)])
def test_custom_scoring_missing_policies(missing, expected):
    grid = deepcopy(DEFAULT_GRID) | {
        "engine": "CUSTOM", "missing_data": missing,
        "criteria": [
            {"metric": "debt_ratio", "direction": "LOW", "bad": "100", "good": "0", "weight": "50"},
            {"metric": "guarantee_coverage", "direction": "HIGH", "bad": "0", "good": "100", "weight": "50"},
        ],
    }
    validated = validate_scoring({"grid": grid})["grid"]
    score, detail = compute_custom_score(SimpleNamespace(client_type="INDIVIDUAL"), {"debt_ratio": Decimal("50")}, validated)
    assert score == (Decimal(expected) if expected is not None else None)
    assert len(detail["missing_metrics"]) == 1


@pytest.mark.parametrize("phase,count", [("SUBMIT", 1), ("APPROVE", 2), ("SETUP", 3)])
def test_eligibility_blocks_carry_to_later_phases(phase, count):
    evaluation = {"checks": [{"passed": False, "effect": effect, "message": effect} for effect in ("ALERT", "BLOCK_SUBMIT", "BLOCK_APPROVE", "BLOCK_SETUP")], "scoring_failures": []}
    assert len(rule_failures(evaluation, phase)) == count


def calendar(**changes):
    return {"timezone": "Africa/Abidjan", "working_days": [0, 1, 2, 3, 4], "opening_time": "08:00:00", "closing_time": "17:00:00", "holidays": [], **changes}


def test_business_calendar_skips_weekend_holiday_and_closed_hours():
    start = datetime(2026, 10, 23, 16, tzinfo=timezone.utc)  # vendredi
    due = business_due_at(start, 3, calendar(holidays=["2026-10-26"]))
    assert due == datetime(2026, 10, 27, 10, tzinfo=timezone.utc)


def test_business_calendar_observes_daylight_saving_timezone():
    due = business_due_at(datetime(2026, 10, 23, 15, tzinfo=timezone.utc), 3, calendar(timezone="Europe/London"))
    assert due == datetime(2026, 10, 26, 10, tzinfo=timezone.utc)


@pytest.mark.parametrize("change", [{"working_days": []}, {"working_days": [True]}, {"working_days": [1, 1]}, {"opening_time": "17:00"}, {"timezone": "Unknown/Nowhere"}, {"holidays": ["2026-10-20", "2026-10-20"]}])
def test_invalid_business_calendar_rejected(change):
    with pytest.raises(ValueError):
        validate_calendar(calendar(**change))


def test_explicit_steps_require_parallel_for_shared_applicable_order():
    definition = SimpleNamespace(execution_mode="EXPLICIT_MODE", min_amount=None, max_amount=None)
    steps = [SimpleNamespace(order=1, mode="SEQUENTIAL", sla_mode="CALENDAR", min_amount=None, max_amount=None) for _ in range(2)]
    with pytest.raises(WorkflowError, match="parallèles"):
        assert_workflow_structure(definition, steps)
    definition.execution_mode = "LEGACY_ORDER"
    assert_workflow_structure(definition, steps)
    definition.execution_mode = "EXPLICIT_MODE"
    for step in steps:
        step.mode = "PARALLEL"
    assert_workflow_structure(definition, steps)


@pytest.mark.django_db
@pytest.mark.parametrize("majority,abstentions,votes,succeeds", [
    ("SIMPLE", "INCLUDE", ["FOR", "FOR", "ABSTAIN"], True),
    ("SIMPLE", "INCLUDE", ["FOR", "ABSTAIN", "ABSTAIN"], False),
    ("SIMPLE", "EXCLUDE", ["FOR", "ABSTAIN", "ABSTAIN"], True),
    ("QUALIFIED", "INCLUDE", ["FOR", "FOR", "AGAINST"], True),
    ("UNANIMOUS", "INCLUDE", ["FOR", "FOR", "ABSTAIN"], False),
    ("UNANIMOUS", "EXCLUDE", ["FOR", "FOR", "ABSTAIN"], True),
    ("SIMPLE", "EXCLUDE", ["ABSTAIN", "ABSTAIN", "ABSTAIN"], False),
])
def test_committee_exact_majorities(tenant_a, django_user_model, majority, abstentions, votes, succeeds):
    members = [django_user_model.objects.create_user(username=f"voter_{index}", tenant=tenant_a) for index in range(3)]
    step = SimpleNamespace(committee_quorum=3, committee_record_required=True, committee_majority=majority, committee_abstentions=abstentions, committee_majority_numerator=2, committee_majority_denominator=3, committee_pv_required=True)
    task = SimpleNamespace(step=step, tenant_id=tenant_a.pk, instance=SimpleNamespace(target=SimpleNamespace(), amount=Decimal("100000")))
    record = {"participants": [{"user": str(member.pk), "vote": vote} for member, vote in zip(members, votes)]}
    with patch("apps.workflow.services.user_can_act", return_value=True), patch("apps.workflow.services._get_credit_application", return_value=None):
        if succeeds:
            result = validate_committee(task, members[0], record)
            assert result["counts"]["eligible"] == 3
        else:
            with pytest.raises(WorkflowError, match="majorité"):
                validate_committee(task, members[0], record)


@pytest.mark.django_db
def test_committee_rejects_creator_vote_and_foreign_member(tenant_a, tenant_b, django_user_model):
    creator = django_user_model.objects.create_user(username="creator_vote", tenant=tenant_a)
    foreign = django_user_model.objects.create_user(username="foreign_vote", tenant=tenant_b)
    step = SimpleNamespace(committee_quorum=1, committee_record_required=True)
    task = SimpleNamespace(step=step, tenant_id=tenant_a.pk, instance=SimpleNamespace(target=SimpleNamespace(created_by_id=creator.pk), amount=Decimal("100000")))
    with patch("apps.workflow.services.user_can_act", return_value=True), patch("apps.workflow.services._get_credit_application", return_value=None):
        with pytest.raises(WorkflowError, match="initiateur"):
            validate_committee(task, creator, {"participants": [{"user": str(creator.pk), "vote": "FOR"}]})
        with pytest.raises(WorkflowError, match="autre filiale"):
            validate_committee(task, creator, {"participants": [{"user": str(foreign.pk), "vote": "FOR"}]})


@pytest.mark.django_db
def test_workflow_retains_calendar_for_later_steps(dossier):
    from apps.workflow.services import _open_tasks_for_order, start_workflow

    with tenant_context(dossier.tenant_id):
        business = BusinessCalendar.objects.create(
            tenant=dossier.tenant, code="CAPTURE", name="Capture",
            opening_time=time(8), closing_time=time(17),
        )
        definition = WorkflowDefinition.objects.create(
            tenant=dossier.tenant, code="CALENDAR-TEST", name="Calendar",
            business_calendar=business,
        )
        group = Group.objects.create(name="delivery_calendar_group")
        steps = [ApprovalStep.objects.create(
            tenant=dossier.tenant, definition=definition, required_group=group,
            name=f"Step {index}", order=index, sla_hours=3,
            sla_mode="BUSINESS", step_kind="DECISIONAL",
        ) for index in (1, 2)]
        now = datetime(2026, 10, 23, 16, tzinfo=timezone.utc)
        with patch("apps.workflow.services.timezone.now", return_value=now), patch("apps.notifications.services.schedule_step_notifications"):
            instance = start_workflow(dossier, amount=dossier.amount_requested, definition=definition)
            assert instance.tasks.get(step=steps[0]).due_at == datetime(2026, 10, 26, 10, tzinfo=timezone.utc)
            business.holidays = ["2026-10-26"]
            business.save()
            _open_tasks_for_order(instance, steps, 2)
        assert instance.tasks.get(step=steps[1]).due_at == datetime(2026, 10, 26, 10, tzinfo=timezone.utc)
        assert instance.calendar_snapshot["holidays"] == []


@pytest.mark.django_db
@pytest.mark.parametrize("mode,has_deadline", [("LEGACY_ORDER", True), ("EXPLICIT_MODE", False)])
def test_zero_sla_preserves_legacy_and_explicit_semantics(dossier, mode, has_deadline):
    from apps.workflow.services import start_workflow

    with tenant_context(dossier.tenant_id):
        definition = WorkflowDefinition.objects.create(
            tenant=dossier.tenant, code="ZERO-SLA", name="Zero",
            execution_mode=mode,
        )
        group = Group.objects.create(name="delivery_zero_group")
        ApprovalStep.objects.create(
            tenant=dossier.tenant, definition=definition, required_group=group,
            name="Decision", order=1, sla_hours=0, step_kind="DECISIONAL",
        )
        with patch("apps.notifications.services.schedule_step_notifications"):
            instance = start_workflow(dossier, amount=dossier.amount_requested, definition=definition)
        assert (instance.tasks.get().due_at is not None) is has_deadline


@pytest.mark.django_db
@pytest.mark.parametrize("schema", [1, 2])
def test_new_tariff_does_not_apply_retroactively_to_old_snapshot(dossier, schema):
    config = resolve_context(dossier.tenant_id, context_for(dossier))
    config["schema_version"] = schema
    config.pop("pricing")
    config["origins"].pop("pricing")
    dossier.configuration_snapshot = config
    dossier.status = "IN_APPROVAL"
    profile(dossier.tenant, status="PUBLISHED", effective_from=datetime(2025, 1, 1, tzinfo=timezone.utc), overrides={"pricing": {"tariff": configured_pricing(fees_rate={"default": "10"})["pricing"]["tariff"]}})
    rendered = application_configuration(dossier)
    assert rendered["pricing"]["tariff"]["engine"] == "LEGACY"
    assert rendered["fingerprint"] == config["fingerprint"]


@pytest.mark.django_db
def test_profile_publisher_cannot_be_latest_writer(tenant_a, config_admin, django_user_model):
    writer, api = config_admin
    author = django_user_model.objects.create_user(username="different_author", tenant=tenant_a)
    obj = profile(tenant_a, created_by=author, updated_by=writer, status="REVIEW")
    response = api.post(f"/api/v1/configuration-profiles/{obj.pk}/publish/", {}, format="json")
    assert response.status_code == 403


@pytest.mark.django_db
def test_foreign_product_reference_cannot_be_attached_to_profile(tenant_b, config_admin):
    from apps.catalog.models import CreditProduct, ProductCategory

    _, api = config_admin
    with tenant_context(tenant_b.pk):
        category = ProductCategory.objects.create(tenant=tenant_b, code="FOREIGN", label="Foreign")
        product = CreditProduct.objects.create(tenant=tenant_b, category=category, code="FOREIGN", label="Foreign", amount_min=Decimal("1"), amount_max=Decimal("100000"), interest_rate=Decimal("5"))
    response = api.post("/api/v1/configuration-profiles/", {"code": "cross-tenant", "name": "Cross", "product": str(product.pk)}, format="json")
    assert response.status_code == 400
    assert not ConfigurationProfile.all_tenants.filter(code="cross-tenant").exists()


@pytest.mark.django_db
def test_profile_preview_requires_dossier_permission(dossier, config_admin):
    _, api = config_admin
    candidate = profile(dossier.tenant)
    before = deepcopy(dossier.configuration_snapshot)
    response = api.post(f"/api/v1/configuration-profiles/{candidate.pk}/preview/", {"application": str(dossier.pk)}, format="json")
    assert response.status_code == 403
    dossier.refresh_from_db()
    assert dossier.configuration_snapshot == before and dossier.status == "DRAFT"


@pytest.mark.django_db
@pytest.mark.parametrize("path,model,values", [
    ("credit-instruction-policy", "CreditInstructionPolicy", {"require_field_visit": True}),
    ("analysis-thresholds", "AnalysisThreshold", {"max_debt_ratio": "25"}),
])
def test_legacy_parameters_get_does_not_create_record_and_writes_are_versioned(
    config_admin, path, model, values,
):
    from apps.credits import models

    user, api = config_admin
    user.user_permissions.add(*Permission.objects.filter(content_type__app_label="credits", content_type__model__in=["creditinstructionpolicy", "analysisthreshold"]))
    selected = getattr(models, model)
    initial = selected.all_tenants.count()
    response = api.get(f"/api/v1/{path}/current/")
    assert response.status_code == 200, response.content
    assert selected.all_tenants.count() == initial
    response = api.patch(f"/api/v1/{path}/current/", values, format="json")
    assert response.status_code == 400, response.content
    assert "versionn" in str(response.data)
    assert selected.all_tenants.count() == initial


@pytest.mark.django_db
def test_review_permission_alone_does_not_grant_credit_administrator_function(dossier, django_user_model):
    dossier.status = "APPROVED"
    dossier.save(update_fields=["status"])
    user = django_user_model.objects.create_user(username="permission-only-reviewer", tenant=dossier.tenant, data_scope="TENANT")
    user.user_permissions.add(*Permission.objects.filter(
        content_type__app_label="credits", codename__in=["view_creditapplication", "review_setup_creditapplication"],
    ))
    api = APIClient()
    api.force_authenticate(user)
    response = api.post(f"/api/v1/credit-applications/{dossier.pk}/setup-review/", {
        "comment": "Contrôles déclarés par un utilisateur sans fonction administration crédit.",
        "checks": {key: True for key in ("kyc", "contribution", "collateral", "terms", "insurance")},
    }, format="json")
    assert response.status_code == 403
    dossier.refresh_from_db()
    assert dossier.setup_review == {}
