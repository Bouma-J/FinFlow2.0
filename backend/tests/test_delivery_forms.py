"""Formulaires, KYC et référentiels, sur SQLite mémoire uniquement."""
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.clients.compliance import client_configuration, cbs_reference_value, kyc_failures, kyc_evidence
from apps.clients.models import Client
from apps.configuration.catalog import validate_overrides
from apps.configuration.forms_catalog import form_defaults, validate_custom_values, validate_forms, validate_references
from apps.configuration.models import ConfigurationProfile
from apps.configuration.services import analysis_requirement_failures, application_configuration, freeze_configuration, resolve_context
from apps.corebanking.models import CoreBankingConnector
from apps.credits.models import CreditApplication
from apps.tenants.models import Agency

pytestmark = pytest.mark.django_db


def definition(code="custom", kind="text", required=False, choices=None):
    return {"id": code, "label": code, "type": kind, "required": required, "choices": choices or []}


def published(tenant, overrides, code="forms", **kwargs):
    return ConfigurationProfile.all_tenants.create(tenant=tenant, code=code, name=code, status="PUBLISHED",
        effective_from=timezone.now() - timedelta(days=1), overrides=overrides, **kwargs)


@pytest.fixture
def client_api(tenant_a, django_user_model):
    user = django_user_model.objects.create(username="forms-client-admin", tenant=tenant_a, data_scope="TENANT")
    user.user_permissions.add(*Permission.objects.filter(content_type__app_label__in=["clients", "credits"]))
    api = APIClient()
    api.force_authenticate(user)
    return api


@pytest.mark.parametrize("kind,value,expected", [
    ("text", "Valeur", "Valeur"), ("number", "0", "0"), ("number", "-3.25", "-3.25"),
    ("boolean", False, False), ("date", "2026-01-10", "2026-01-10"), ("choice", "A", "A"),
])
def test_custom_values_types(kind, value, expected):
    field = definition(kind=kind, required=True, choices=["A", "B"] if kind == "choice" else [])
    assert validate_custom_values([field], {"custom": value}, require=True)["custom"] == expected


@pytest.mark.parametrize("kind,value", [("boolean", "false"), ("number", True), ("number", "NaN"), ("number", "Infinity"), ("number", "1000000000000000000"), ("date", "2026-02-30"), ("date", "20260101"), ("text", {"x": 1}), ("choice", "C")])
def test_invalid_custom_values_refused(kind, value):
    with pytest.raises(ValidationError):
        validate_custom_values([definition(kind=kind, choices=["A"] if kind == "choice" else [])], {"custom": value})


def test_retired_custom_values_preserved_but_cannot_be_injected():
    assert validate_custom_values([], {}, previous={"legacy": "kept"}) == {"legacy": "kept"}
    assert validate_custom_values([], {"legacy": "kept"}, previous={"legacy": "kept"}) == {"legacy": "kept"}
    with pytest.raises(ValidationError):
        validate_custom_values([], {"legacy": "changed"}, previous={"legacy": "kept"})


def test_borrower_form_persists_typed_fields_and_allows_incomplete_draft(tenant_a, client_api):
    published(tenant_a, {"forms": {"client_fields": [definition("checked", "boolean", True), definition("amount", "number")]}})
    response = client_api.post("/api/v1/clients/", {"client_type": "INDIVIDUAL", "last_name": "Draft", "custom_fields": {"amount": "0", "checked": False}}, format="json")
    assert response.status_code == 201, response.data
    client = Client.all_tenants.get(pk=response.data["id"])
    assert client.custom_fields == {"amount": "0", "checked": False}
    response = client_api.post("/api/v1/clients/", {"client_type": "INDIVIDUAL", "last_name": "Incomplete"}, format="json")
    assert response.status_code == 201, response.data
    response = client_api.patch(f"/api/v1/clients/{client.pk}/", {"custom_fields": {"unknown": "injected"}}, format="json")
    assert response.status_code == 400


def test_custom_fields_multipart_json_supported(tenant_a, client_api):
    published(tenant_a, {"forms": {"client_fields": [definition("checked", "boolean")]}})
    response = client_api.post("/api/v1/clients/", {"client_type": "INDIVIDUAL", "last_name": "Multipart", "custom_fields": '{"checked": false}'}, format="multipart")
    assert response.status_code == 201, response.data
    assert response.data["custom_fields"]["checked"] is False


def test_kyc_requires_native_fields_documents_and_custom(tenant_a, client_a):
    published(tenant_a, {"kyc": {"required_fields": ["phone"], "required_documents": ["id_document_scan"], "check_expiry": True, "validity_days": 10},
                         "forms": {"client_fields": [definition(required=True)]}})
    failures = kyc_failures(client_a)
    assert len(failures) == 5
    client_a.phone = "01020304"
    client_a.id_document_scan = "clients/test.pdf"
    client_a.id_document_expiry_date = timezone.localdate() + timedelta(days=1)
    client_a.kyc_validated_at = timezone.localdate()
    client_a.custom_fields = {"custom": "Provided"}
    assert kyc_failures(client_a) == []
    assert kyc_failures(client_a, at=timezone.localdate() + timedelta(days=12))


def test_validate_kyc_is_checked_and_date_comes_from_server(tenant_a, client_a, client_api):
    published(tenant_a, {"kyc": {"required_fields": ["phone"]}})
    client_a.kyc_status = "PENDING"
    client_a.save()
    url = f"/api/v1/clients/{client_a.pk}/"
    response = client_api.patch(url, {"kyc_status": "VALIDATED"}, format="json")
    assert response.status_code == 400
    response = client_api.patch(url, {"kyc_status": "VALIDATED", "phone": "010203", "kyc_validated_at": "2099-01-01"}, format="json")
    assert response.status_code == 200, response.data
    assert response.data["kyc_validated_at"] == timezone.localdate().isoformat()


def test_expiry_uses_manager_identity_for_legal_entity(tenant_a, client_a):
    published(tenant_a, {"kyc": {"check_expiry": True}})
    client_a.client_type = "CORPORATE"
    client_a.id_document_expiry_date = timezone.localdate() + timedelta(days=10)
    assert kyc_failures(client_a)
    client_a.manager_id_document_expiry_date = timezone.localdate()
    assert kyc_failures(client_a) == []


def test_product_kyc_frozen_separately_from_client_baseline(tenant_a, client_a, product_a, client_api):
    fields = [definition("local_product", required=True)]
    published(tenant_a, {"kyc": {"required_fields": ["phone"]}, "forms": {"client_fields": fields}}, product=product_a)
    application = CreditApplication.all_tenants.create(tenant=tenant_a, client=client_a, product=product_a,
        reference="FORMS-KYC", amount_requested="100000", duration_months=12)
    assert client_configuration(client_a)["forms"]["client_fields"] == []
    freeze_configuration(application)
    application.status = "SUBMITTED"
    application.save()
    response = client_api.get("/api/v1/clients/form-configuration/", {"application": str(application.pk), "client": str(client_a.pk)})
    assert response.status_code == 200, response.data
    assert response.data["frozen"] is True
    assert response.data["forms"]["client_fields"] == fields
    response = client_api.patch(f"/api/v1/clients/{client_a.pk}/", {"configuration_application": str(application.pk), "phone": "0102", "custom_fields": {"local_product": "Dossier requirement"}}, format="json")
    assert response.status_code == 200, response.data
    client_a.refresh_from_db()
    assert kyc_failures(client_a, application=application) == []


def test_dossier_context_cannot_cross_clients_or_tenants(tenant_a, tenant_b, client_a, product_a, client_api):
    foreign = Client.all_tenants.create(tenant=tenant_b, client_type="INDIVIDUAL", last_name="Foreign")
    app = CreditApplication.all_tenants.create(tenant=tenant_a, client=client_a, product=product_a,
        reference="CONTEXT", amount_requested="100000", duration_months=12)
    response = client_api.get("/api/v1/clients/form-configuration/", {"application": str(app.pk), "client": str(foreign.pk)})
    assert response.status_code == 400
    agency = Agency.objects.create(tenant=tenant_b, code="FOREIGN", name="Foreign")
    response = client_api.get("/api/v1/clients/form-configuration/", {"agency": str(agency.pk)})
    assert response.status_code == 403


def test_tenant_scope_can_load_form_configuration_for_any_local_agency(tenant_a, client_api):
    agency = Agency.objects.create(tenant=tenant_a, code="SECOND", name="Autre agence")

    client_context = client_api.get(
        "/api/v1/clients/form-configuration/",
        {"client_type": "INDIVIDUAL", "agency": str(agency.pk)},
    )
    assert client_context.status_code == 200, client_context.data

    credit_context = client_api.get(
        "/api/v1/credit-applications/configuration-context/",
        {"client_type": "INDIVIDUAL", "agency": str(agency.pk)},
    )
    assert credit_context.status_code == 200, credit_context.data


def test_credit_form_context_marks_financing_object_requirement_by_connector_mode(tenant_a, client_api):
    url = "/api/v1/credit-applications/configuration-context/"
    params = {"client_type": "INDIVIDUAL"}

    response = client_api.get(url, params)
    assert response.status_code == 200, response.data
    assert response.data["financing_object_required"] is False

    connector = CoreBankingConnector.objects.create(
        tenant=tenant_a,
        name="Recette locale",
        protocol="REST",
        mapping_rules={"disbursement": {"mode": "LOCAL"}},
        is_active=True,
    )
    response = client_api.get(url, params)
    assert response.status_code == 200, response.data
    assert response.data["financing_object_required"] is False

    connector.mapping_rules = {"disbursement": {"mode": "CBS"}}
    connector.save(update_fields=["mapping_rules"])
    response = client_api.get(url, params)
    assert response.status_code == 200, response.data
    assert response.data["financing_object_required"] is True


def test_reference_extensions_retain_inactive_values_but_reject_new_assignment(tenant_a, client_a, client_api):
    entries = [{"code": "CUSTOM", "label": "Civilité locale", "active": True, "cbs_code": "EXT-01"},
               {"code": "MR", "label": "Monsieur", "active": False, "cbs_code": ""}]
    published(tenant_a, {"references": {"civility": entries}})
    client_a.civility = "MR"
    client_a.save()
    response = client_api.patch(f"/api/v1/clients/{client_a.pk}/", {"civility": "MR"}, format="json")
    assert response.status_code == 200, response.data
    response = client_api.post("/api/v1/clients/", {"client_type": "INDIVIDUAL", "last_name": "New", "civility": "MR"}, format="json")
    assert response.status_code == 400
    response = client_api.post("/api/v1/clients/", {"client_type": "INDIVIDUAL", "last_name": "New", "civility": "CUSTOM"}, format="json")
    assert response.status_code == 201, response.data
    assert cbs_reference_value(client_configuration(client_a), "civility", "EXT-01") == "CUSTOM"
    assert cbs_reference_value(client_configuration(client_a), "civility", "UNMAPPED") is None


def test_reference_invalid_and_ambiguous_codes_rejected():
    with pytest.raises(ValidationError):
        validate_references({"civility": [{"code": "TOO_LONG_CODE", "label": "Too long", "active": True, "cbs_code": ""}]})
    with pytest.raises(ValidationError):
        validate_references({"civility": [{"code": "A", "label": "A", "active": True, "cbs_code": "1"}, {"code": "B", "label": "B", "active": True, "cbs_code": "1"}]})


def test_core_sections_cannot_be_hidden_and_required_informative_section_reshown(tenant_a):
    for key in ("fa-params", "fa-conclusion", "fa-income", "fa-balance"):
        with pytest.raises(ValidationError):
            validate_forms({"analysis_sections": [{"id": key, "visible": False}]})
    obj = published(tenant_a, {"forms": {"analysis_sections": [{"id": "fa-sector", "visible": False}]}, "analysis": {"required_fields": ["sector"]}})
    result = resolve_context(tenant_a.pk, {})
    assert result["forms"]["analysis_sections"][0]["visible"] is True
    assert obj.overrides["forms"]["analysis_sections"][0]["visible"] is False


def test_additional_analysis_fields_checked_at_submission(tenant_a, client_a, product_a):
    published(tenant_a, {"forms": {"analysis_fields": [definition("analysis_extra", required=True)]}})
    app = CreditApplication.all_tenants.create(tenant=tenant_a, client=client_a, product=product_a,
        reference="EXTRA", amount_requested="100000", duration_months=12)
    reference = SimpleNamespace(custom_fields={}, analysis_details={}, bank_statement_months=0)
    assert analysis_requirement_failures(app, reference)
    reference.custom_fields = {"analysis_extra": "Complete"}
    assert analysis_requirement_failures(app, reference) == []


def test_new_form_rules_not_injected_into_older_frozen_snapshot(tenant_a, client_a, product_a):
    app = CreditApplication.all_tenants.create(tenant=tenant_a, client=client_a, product=product_a,
        reference="OLD-FORM", amount_requested="100000", duration_months=12)
    freeze_configuration(app)
    for key in form_defaults():
        app.configuration_snapshot.pop(key, None)
        app.configuration_snapshot["origins"].pop(key, None)
    frozen = deepcopy(app.configuration_snapshot)
    app.status = "SUBMITTED"
    published(tenant_a, {"forms": {"client_fields": [definition(required=True)]}, "kyc": {"required_fields": ["phone"]}})
    result = application_configuration(app)
    assert result["forms"]["client_fields"] == [] and result["kyc"]["required_fields"] == []
    assert result["fingerprint"] == frozen["fingerprint"]


def test_unknown_fields_or_executable_schema_are_rejected():
    with pytest.raises(ValidationError):
        validate_overrides({"forms": {"client_fields": [{**definition(), "expression": "__import__('os')"}]}})
    with pytest.raises(ValidationError):
        validate_overrides({"kyc": {"required_fields": ["cbs_credit_limit"]}})


def test_required_whitespace_is_missing_but_false_and_zero_are_values(tenant_a, client_a):
    with pytest.raises(ValidationError):
        validate_custom_values([definition(required=True)], {"custom": "   "}, require=True)
    assert validate_custom_values([definition(kind="boolean", required=True)], {"custom": False}, require=True)["custom"] is False
    published(tenant_a, {"kyc": {"required_fields": ["phone"]}})
    client_a.phone = "   "
    assert kyc_failures(client_a)


def test_kyc_document_replacement_changes_evidence(tenant_a, client_a):
    published(tenant_a, {"kyc": {"required_documents": ["id_document_scan"]}})
    configuration = client_configuration(client_a)
    client_a.id_document_scan = "identity/old.pdf"
    old = kyc_evidence(client_a, configuration)
    client_a.id_document_scan = "identity/new.pdf"
    assert kyc_evidence(client_a, configuration) != old
