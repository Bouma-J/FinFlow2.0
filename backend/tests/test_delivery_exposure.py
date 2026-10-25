"""Engagements documentés : cumul, preuves, publication et restitution cloisonnée."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client
from apps.common.tenancy import tenant_context
from apps.configuration.exposure_catalog import DEFAULT_EXPOSURE
from apps.configuration.services import context_for, resolve_context
from apps.credits.exposure import exposure_assessment, exposure_failures
from apps.credits.exposure_models import BorrowerGroup, CreditExposureObservation
from apps.credits.models import CreditApplication, Loan
from apps.documents.models import Document, DocumentCategory
from apps.tenants.models import Agency

pytestmark = pytest.mark.django_db


@pytest.fixture
def exposure_context(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.pk):
        actor = User.objects.create_user(username="exposure-author", tenant=tenant_a, data_scope="TENANT")
        reviewer = User.objects.create_user(username="exposure-reviewer", tenant=tenant_a, data_scope="TENANT")
        permissions = Permission.objects.filter(content_type__app_label="credits")
        actor.user_permissions.add(*permissions)
        reviewer.user_permissions.add(*permissions)
        agency = Agency.objects.create(tenant=tenant_a, code="EXP-A", name="Agence A")
        other_agency = Agency.objects.create(tenant=tenant_a, code="EXP-B", name="Agence B")
        client_a.agency = agency
        client_a.save()
        category = DocumentCategory.objects.create(tenant=tenant_a, code="EXPOSURE", label="Situation consolidée")
        app = CreditApplication.objects.create(
            tenant=tenant_a, product=product_a, client=client_a, agency=agency,
            amount_requested=Decimal("100000"), duration_months=12, currency="XOF",
            status="IN_APPROVAL", created_by=actor,
        )
    api = APIClient()
    api.force_authenticate(actor)
    config = resolve_context(tenant_a.pk, context_for(app))
    config["exposure"] = {"rules": deepcopy(DEFAULT_EXPOSURE) | {
        "enabled": True, "currency": "XOF", "gate": "SUBMIT",
        "require_verified_snapshot": True,
    }}
    app.configuration_snapshot = config
    app.save(update_fields=["configuration_snapshot"])
    with tenant_context(tenant_a.pk):
        yield SimpleNamespace(tenant=tenant_a, product=product_a, client=client_a, app=app,
                              actor=actor, reviewer=reviewer, api=api, category=category,
                              agency=agency, other_agency=other_agency, config=config)


def evidence(ctx, client=None, **changes):
    client = client or ctx.client
    return Document.all_tenants.create(
        tenant=ctx.tenant, category=ctx.category, name="Situation CBS et autres engagements",
        file="situations/situation.pdf", verification_status="VERIFIED",
        content_type=ContentType.objects.get_for_model(Client), object_id=client.pk,
        **changes,
    )


def observation(ctx, client=None, **changes):
    client = client or ctx.client
    values = {
        "tenant": ctx.tenant, "client": client, "currency": "XOF", "as_of": timezone.localdate(),
        "drawn_principal": Decimal("200000"), "undrawn_commitments": Decimal("30000"),
        "guarantees_given": Decimal("20000"), "source_reference": "SOURCE-EXTERNE",
        "evidence": evidence(ctx, client), "completeness_confirmed": True,
        "status": "VERIFIED", "created_by": ctx.actor, "updated_by": ctx.actor,
        "verified_by": ctx.reviewer, "verified_at": timezone.now(),
    }
    values.update(changes)
    return CreditExposureObservation.all_tenants.create(**values)


def related_client(ctx):
    return Client.all_tenants.create(
        tenant=ctx.tenant, reference="RELATED", first_name="Autre", last_name="Client",
        client_type="INDIVIDUAL", kyc_status="VALIDATED", agency=ctx.other_agency,
    )


def set_rules(ctx, **changes):
    ctx.config["exposure"]["rules"].update(changes)
    ctx.app.configuration_snapshot = deepcopy(ctx.config)
    ctx.app.save(update_fields=["configuration_snapshot"])


def test_complete_snapshot_includes_current_once_and_other_pending(exposure_context):
    ctx = exposure_context
    observation(ctx)
    for status in ("DRAFT", "IN_APPROVAL", "REJECTED"):
        CreditApplication.all_tenants.create(
            tenant=ctx.tenant, client=ctx.client, product=ctx.product,
            amount_requested=Decimal("40000"), duration_months=12, currency="XOF", status=status,
        )
    result = exposure_assessment(ctx.app)
    assert Decimal(result["client_total"]) == Decimal("390000")
    assert Decimal(result["members"][0]["pending_total"]) == Decimal("140000")
    assert not result["failures"] and result["complete"]


def test_pending_switch_still_includes_current_request(exposure_context):
    ctx = exposure_context
    observation(ctx)
    set_rules(ctx, include_pending=False)
    result = exposure_assessment(ctx.app)
    assert Decimal(result["client_total"]) == Decimal("350000")


def test_group_cumul_does_not_add_initial_local_principal_twice(exposure_context):
    ctx = exposure_context
    other = related_client(ctx)
    baseline = observation(ctx)
    observation(ctx, other, drawn_principal=Decimal("50000"), undrawn_commitments=0, guarantees_given=0)
    group = BorrowerGroup.all_tenants.create(tenant=ctx.tenant, code="ECONOMIC", name="Groupe", reason="Contrôle commun")
    group.clients.add(ctx.client, other)
    old_app = CreditApplication.all_tenants.create(
        tenant=ctx.tenant, client=ctx.client, product=ctx.product, amount_requested=Decimal("200000"),
        duration_months=12, currency="XOF", status="DISBURSED",
    )
    local_loan = Loan.all_tenants.create(tenant=ctx.tenant, application=old_app, principal=Decimal("200000"), interest_rate=10, duration_months=12, disbursed_at=timezone.localdate(), first_due_date=timezone.localdate() + timedelta(days=30))
    # Ce prêt fait déjà partie de la situation externe, il la précède.
    Loan.all_tenants.filter(pk=local_loan.pk).update(created_at=baseline.created_at - timedelta(seconds=1))
    result = exposure_assessment(ctx.app)
    assert Decimal(result["group_total"]) == Decimal("400000")
    current = next(row for row in result["members"] if row["client"] == str(ctx.client.pk))
    assert Decimal(current["local_initial_principal"]) == Decimal("200000")
    set_rules(ctx, group_limit="399999.99")
    assert any("plafond" in message and "groupe" in message for message in exposure_assessment(ctx.app)["failures"])


@pytest.mark.parametrize("changes,fragment", [
    ({"as_of": timezone.localdate() - timedelta(days=31)}, "ancienne"),
    ({"currency": "EUR"}, "Aucune situation"),
    ({"completeness_confirmed": False}, "Aucune situation"),
])
def test_missing_or_stale_external_values_block_with_evidence(exposure_context, changes, fragment):
    ctx = exposure_context
    observation(ctx, **changes)
    set_rules(ctx, maximum_age_days=30)
    assert any(fragment in message for message in exposure_assessment(ctx.app)["failures"])


def test_revoked_new_snapshot_does_not_reactivate_old_one(exposure_context):
    ctx = exposure_context
    observation(ctx, as_of=timezone.localdate() - timedelta(days=1))
    revoked = observation(ctx, status="REVOKED")
    result = exposure_assessment(ctx.app)
    assert result["client_total"] is None
    assert result["members"][0]["observation"] is None
    assert result["failures"]
    assert revoked.status == "REVOKED"


@pytest.mark.parametrize("change", [{"file": ""}, {"is_deleted": True}, {"verification_status": "PENDING"}, {"expiry_date": timezone.localdate() - timedelta(days=1)}])
def test_evidence_changes_invalidate_assessment(exposure_context, change):
    ctx = exposure_context
    doc = evidence(ctx, **change) if "file" not in change and "verification_status" not in change else evidence(ctx)
    if "file" in change or "verification_status" in change:
        for key, value in change.items():
            setattr(doc, key, value)
        doc.save()
    observation(ctx, evidence=doc)
    result = exposure_assessment(ctx.app)
    assert not result["complete"]
    assert any("Justificatif" in message for message in result["failures"])


def test_foreign_currency_request_is_not_silently_converted(exposure_context):
    ctx = exposure_context
    observation(ctx)
    CreditApplication.all_tenants.create(tenant=ctx.tenant, client=ctx.client, product=ctx.product,
        amount_requested=Decimal("1000"), duration_months=12, currency="EUR", status="IN_APPROVAL")
    result = exposure_assessment(ctx.app)
    assert result["client_total"] is None
    assert any("devise" in message for message in result["failures"])


@pytest.mark.parametrize("stage,blocked", [("SUBMIT", False), ("APPROVE", True), ("SETUP", True)])
def test_exposure_gate_carries_forward(exposure_context, stage, blocked):
    ctx = exposure_context
    set_rules(ctx, gate="APPROVE")
    assert bool(exposure_failures(ctx.app, stage)) is blocked


def test_observation_api_requires_independent_verifier_and_then_is_immutable(exposure_context):
    ctx = exposure_context
    doc = evidence(ctx)
    response = ctx.api.post("/api/v1/credit-exposure-observations/", {
        "client": str(ctx.client.pk), "currency": "XOF", "as_of": str(timezone.localdate()),
        "drawn_principal": "200000", "source_reference": "EXTERNAL-CBS-REF",
        "evidence": str(doc.pk), "completeness_confirmed": True,
    }, format="json")
    assert response.status_code == 201, response.content
    url = f"/api/v1/credit-exposure-observations/{response.data['id']}/"
    assert ctx.api.post(url + "verify/", {}, format="json").status_code == 403
    ctx.api.force_authenticate(ctx.reviewer)
    verified = ctx.api.post(url + "verify/", {}, format="json")
    assert verified.status_code == 200, verified.content
    assert verified.data["status"] == "VERIFIED"
    mutated = ctx.api.patch(url, {"drawn_principal": "0"}, format="json")
    assert mutated.status_code == 400
    obj = CreditExposureObservation.all_tenants.get(pk=verified.data["id"])
    assert obj.drawn_principal == Decimal("200000")
    assert ctx.api.delete(url).status_code == 405


def test_group_api_rejects_foreign_client(exposure_context, tenant_b):
    ctx = exposure_context
    foreign = Client.all_tenants.create(tenant=tenant_b, reference="EXTERNAL", first_name="Foreign", client_type="INDIVIDUAL")
    response = ctx.api.post("/api/v1/borrower-groups/", {
        "code": "cross-tenant", "name": "Cross", "reason": "Test",
        "clients": [str(ctx.client.pk), str(foreign.pk)],
    }, format="json")
    assert response.status_code == 400, response.content
    assert not BorrowerGroup.all_tenants.filter(code="cross-tenant").exists()


def test_observation_api_isolates_foreign_tenant(exposure_context, tenant_b):
    ctx = exposure_context
    item = observation(ctx)
    foreign_user = User.objects.create_user(username="exposure-foreign", tenant=tenant_b, data_scope="TENANT")
    foreign_user.user_permissions.add(*Permission.objects.filter(content_type__app_label="credits"))
    ctx.api.force_authenticate(foreign_user)
    assert ctx.api.get(f"/api/v1/credit-exposure-observations/{item.pk}/").status_code == 404


def test_dossier_exposure_requires_observation_permission(exposure_context):
    ctx = exposure_context
    user = User.objects.create_user(username="dossier-only", tenant=ctx.tenant, data_scope="TENANT")
    user.user_permissions.add(Permission.objects.get(content_type__app_label="credits", codename="view_creditapplication"))
    ctx.api.force_authenticate(user)
    assert ctx.api.get(f"/api/v1/credit-applications/{ctx.app.pk}/exposure/").status_code == 403


def test_restricted_exposure_does_not_reveal_hidden_member_or_group_amount(exposure_context):
    ctx = exposure_context
    other = related_client(ctx)
    observation(ctx)
    observation(ctx, other, drawn_principal=Decimal("777777"), undrawn_commitments=0, guarantees_given=0, source_reference="SECRET-OTHER-AGENCY")
    group = BorrowerGroup.all_tenants.create(tenant=ctx.tenant, code="PRIVATE", name="Private", reason="Liens")
    group.clients.add(ctx.client, other)
    set_rules(ctx, group_limit="500000")
    user = User.objects.create_user(username="restricted-exposure", tenant=ctx.tenant, agency=ctx.agency, data_scope="AGENCY")
    user.user_permissions.add(*Permission.objects.filter(content_type__app_label="credits", codename__in=["view_creditapplication", "view_creditexposureobservation", "view_borrowergroup"]))
    ctx.api.force_authenticate(user)
    response = ctx.api.get(f"/api/v1/credit-applications/{ctx.app.pk}/exposure/")
    assert response.status_code == 200, response.content
    assert response.data["restricted"] and response.data["group_total"] is None
    assert [row["client"] for row in response.data["members"]] == [str(ctx.client.pk)]
    for secret in (str(other.pk), "777777", "1127777", "SECRET-OTHER-AGENCY"):
        assert secret not in str(response.data)
    listed = ctx.api.get("/api/v1/borrower-groups/")
    assert listed.status_code == 200
    assert listed.data["results"] == []


@pytest.mark.parametrize("limit,synced,fragment", [
    (None, None, "indisponible"),
    (Decimal("400000"), timezone.now() - timedelta(days=31), "actualisé"),
    (Decimal("300000"), timezone.now(), "dépassé"),
])
def test_cbs_client_limit_must_be_dated_fresh_and_sufficient(exposure_context, limit, synced, fragment):
    ctx = exposure_context
    observation(ctx)
    ctx.client.cbs_credit_limit, ctx.client.cbs_synced_at = limit, synced
    ctx.client.save()
    set_rules(ctx, use_cbs_client_limit=True, maximum_age_days=30)
    assert any(fragment in message for message in exposure_assessment(ctx.app)["failures"])


def test_latest_writer_cannot_verify_observation(exposure_context):
    ctx = exposure_context
    item = observation(ctx, status="DRAFT", updated_by=ctx.reviewer, verified_at=None, verified_by=None)
    ctx.api.force_authenticate(ctx.reviewer)
    response = ctx.api.post(f"/api/v1/credit-exposure-observations/{item.pk}/verify/", {}, format="json")
    assert response.status_code == 403
    item.refresh_from_db()
    assert item.status == "DRAFT"


def test_document_removed_after_draft_prevents_verification(exposure_context):
    ctx = exposure_context
    item = observation(ctx, status="DRAFT", verified_at=None, verified_by=None)
    item.evidence.file = ""
    item.evidence.save()
    ctx.api.force_authenticate(ctx.reviewer)
    response = ctx.api.post(f"/api/v1/credit-exposure-observations/{item.pk}/verify/", {}, format="json")
    assert response.status_code == 400
    item.refresh_from_db()
    assert item.status == "DRAFT"


def test_client_limit_exact_boundary_and_disabled_rule(exposure_context):
    ctx = exposure_context
    observation(ctx)
    set_rules(ctx, client_limit="350000")
    assert not exposure_assessment(ctx.app)["failures"]
    set_rules(ctx, client_limit="349999.99")
    assert any("plafond client" in message for message in exposure_assessment(ctx.app)["failures"])
    set_rules(ctx, enabled=False)
    assert not exposure_failures(ctx.app, "SETUP")


def test_document_reassigned_after_draft_prevents_verification(exposure_context):
    ctx = exposure_context
    item = observation(ctx, status="DRAFT", verified_at=None, verified_by=None)
    other = related_client(ctx)
    item.evidence.object_id = other.pk
    item.evidence.save()
    ctx.api.force_authenticate(ctx.reviewer)
    response = ctx.api.post(f"/api/v1/credit-exposure-observations/{item.pk}/verify/", {}, format="json")
    assert response.status_code == 400
    item.refresh_from_db()
    assert item.status == "DRAFT"


def test_document_reassigned_after_verification_invalidates_assessment(exposure_context):
    ctx = exposure_context
    item = observation(ctx)
    other = related_client(ctx)
    item.evidence.object_id = other.pk
    item.evidence.save()
    result = exposure_assessment(ctx.app)
    assert not result["complete"]
    assert result["failures"]


@pytest.mark.parametrize("reason", ["created_after", "disbursed_after"])
def test_local_setup_after_external_snapshot_requires_refresh(exposure_context, reason):
    ctx = exposure_context
    baseline = observation(ctx, as_of=timezone.localdate() - timedelta(days=1) if reason == "disbursed_after" else timezone.localdate())
    other_app = CreditApplication.all_tenants.create(
        tenant=ctx.tenant, client=ctx.client, product=ctx.product,
        amount_requested=Decimal("50000"), duration_months=12, currency="XOF", status="DISBURSED",
    )
    loan = Loan.all_tenants.create(
        tenant=ctx.tenant, application=other_app, principal=Decimal("50000"),
        interest_rate=10, duration_months=12, disbursed_at=timezone.localdate(),
        first_due_date=timezone.localdate() + timedelta(days=30),
    )
    if reason == "disbursed_after":
        Loan.all_tenants.filter(pk=loan.pk).update(created_at=baseline.created_at - timedelta(seconds=1))
    else:
        Loan.all_tenants.filter(pk=loan.pk).update(created_at=baseline.created_at + timedelta(seconds=1))
    result = exposure_assessment(ctx.app)
    assert not result["complete"] and result["group_total"] is None
    assert any("postérieure" in message for message in result["failures"])


@pytest.mark.parametrize("status", ["DISBURSED", "CLOSED", "REJECTED", "CANCELLED"])
def test_finished_application_is_not_added_as_new_exposure(exposure_context, status):
    ctx = exposure_context
    observation(ctx)
    ctx.app.status = status
    ctx.app.save(update_fields=["status"])
    result = exposure_assessment(ctx.app)
    assert Decimal(result["client_total"]) == Decimal("250000")
    assert Decimal(result["members"][0]["pending_total"]) == 0
