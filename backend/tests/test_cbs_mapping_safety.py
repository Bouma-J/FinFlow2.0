"""Régression du lot 1 : références exactes et transmission protégée, sans réseau."""
import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.cbs_mapping import cbs_mapping_snapshot, resolve_application_cbs
from apps.catalog.models import CbsProductReference, FinancingObject, RepaymentMethod
from apps.common.tenancy import tenant_context
from apps.corebanking.disbursement import build_credit_disbursement_payload, submit_credit_to_cbs
from apps.corebanking.models import CoreBankingConnector, IntegrationLog
from apps.corebanking.services import CoreBankingError, RestAdapter, send_operation
from apps.credits.models import CreditApplication
from apps.credits.setup_authorization import authorization_failures
from apps.tenants.models import Agency
from tests.setup_helpers import configure_verified_cbs, prepare_setup

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Aucun accès réseau autorisé dans ces tests")
    monkeypatch.setattr("requests.sessions.Session.request", forbidden)


@pytest.fixture
def mapped(tenant_a, product_a, client_a):
    from apps.catalog.defaults import ensure_catalog_defaults
    ensure_catalog_defaults(tenant_a)
    with tenant_context(tenant_a.pk):
        conn = CoreBankingConnector.objects.create(tenant=tenant_a, name="CBS test", protocol="REST",
            base_url="https://cbs.invalid", mapping_rules={"disbursement": {"mode": "CBS"}}, is_active=True)
        agency = Agency.objects.create(tenant=tenant_a, code="A", name="Agence test", cbs_point_of_service_id="PS1")
        officer = User.objects.create(username="officer-mapping", tenant=tenant_a, agency=agency, cbs_id="G1")
        client_a.cbs_client_id = "A-TEST"
        client_a.save(update_fields=["cbs_client_id"])
        app = CreditApplication.objects.create(tenant=tenant_a, client=client_a, product=product_a, agency=agency,
            reference="SAFETY", amount_requested=100000, amount_approved=100000, duration_months=12,
            interest_rate=10, currency="XOF", periodicity="MONTHLY", repayment_mechanism="DEGRESSIVE",
            purpose_type="CONSUMPTION", status="APPROVED", decision_date=timezone.now().date(),
            created_by=officer, submitted_by=officer)
        configure_verified_cbs(app, conn, officer)
    return app, conn


def test_exact_mapping_is_shared_by_display_and_payload(mapped):
    app, conn = mapped
    resolved = resolve_application_cbs(app)
    assert resolved["ready_for_cbs"]
    payload = build_credit_disbursement_payload(app, connector=conn)
    assert all(payload.get(key) == value for key, value in resolved["values"].items() if value)
    assert payload["idProduitCrd"] == "101"
    assert payload["idProduitRemb"] == "202"
    assert payload["idObjetFinancement"] == "45"


def test_successful_user_example_has_distinct_credit_product_and_object(mapped):
    app, conn = mapped
    FinancingObject.all_tenants.filter(pk=app.financing_object_id).update(cbs_code="30")
    CbsProductReference.all_tenants.filter(pk=app.product.cbs_credit_product_id).update(cbs_code="1")
    RepaymentMethod.all_tenants.filter(tenant_id=app.tenant_id, code=app.repayment_mechanism).update(cbs_code="1")
    payload = build_credit_disbursement_payload(app, connector=conn)
    assert payload["idProduitCrd"] == "1"
    assert payload["idProduitRemb"] == "1"
    assert payload["idObjetFinancement"] == "30"
    assert all(isinstance(payload[key], str) for key in ("idProduitCrd", "idProduitRemb", "idObjetFinancement"))


@pytest.mark.parametrize("code,account,identity,expected", [
    ("AG-TEST", "ACCOUNT-TEST", "UAT-LOCAL", "codeAdherent"),
    ("", "ACCOUNT-TEST", "UAT-LOCAL", "numManuel"),
    ("", "", "IDENTITY-TEST", "numPieceIdentite"),
])
def test_real_payload_uses_one_primary_identifier(mapped, code, account, identity, expected):
    app, conn = mapped
    app.client.cbs_client_id = code
    app.client.cbs_account_number = account
    app.client.national_id = identity
    app.client.save(update_fields=["cbs_client_id", "cbs_account_number", "national_id"])
    payload = build_credit_disbursement_payload(app, connector=conn)
    assert [k for k in ("codeAdherent", "numManuel", "numPieceIdentite") if k in payload] == [expected]


@pytest.mark.parametrize("field,value", [
    ("is_active", False), ("verification_status", "PENDING"), ("verified_at", None),
    ("verified_by", None), ("source_reference", ""), ("currency", "EUR"),
    ("kind", "REPAYMENT"), ("cbs_code", "CRED-CONSO"), ("cbs_code", ""),
])
def test_invalid_credit_product_never_falls_back_to_financing_object(mapped, field, value):
    app, conn = mapped
    ref = app.product.cbs_credit_product
    setattr(ref, field, value)
    ref.save(update_fields=[field])
    resolved = resolve_application_cbs(app)
    assert resolved["product_cbs_code"] == ""
    assert not resolved["ready_for_cbs"]
    with pytest.raises(CoreBankingError, match="product.cbs_product_code"):
        build_credit_disbursement_payload(app, connector=conn)


def test_new_external_reference_is_stable_and_globally_distinct(mapped):
    app, conn = mapped
    first = build_credit_disbursement_payload(app, connector=conn)["externalId"]
    assert first == str(app.pk)
    app.reference = "REFERENCE-METIER-MODIFIEE"
    assert build_credit_disbursement_payload(app, connector=conn)["externalId"] == first


def test_existing_attempt_keeps_its_external_reference(mapped):
    app, conn = mapped
    IntegrationLog.all_tenants.create(tenant_id=app.tenant_id, connector=conn, operation="SUBMIT_CREDIT",
        idempotency_key=f"disburse:{app.pk}", status="RETRY", request_payload={"externalId": "OLD-CBS-REFERENCE"})
    assert build_credit_disbursement_payload(app, connector=conn)["externalId"] == "OLD-CBS-REFERENCE"


@pytest.mark.parametrize("model,field,value", [
    (FinancingObject, "is_active", False), (FinancingObject, "cbs_code", ""),
    (RepaymentMethod, "is_active", False), (RepaymentMethod, "cbs_code", ""),
])
def test_invalid_catalog_reference_blocks_payload(mapped, model, field, value):
    app, conn = mapped
    query = model.all_tenants.filter(tenant_id=app.tenant_id)
    query = query.filter(pk=app.financing_object_id) if model is FinancingObject else query.filter(code=app.repayment_mechanism)
    query.update(**{field: value})
    assert not resolve_application_cbs(app)["ready_for_cbs"]
    with pytest.raises(CoreBankingError):
        build_credit_disbursement_payload(app, connector=conn)


def test_foreign_tenant_and_foreign_connector_are_rejected(mapped, tenant_b):
    app, conn = mapped
    FinancingObject.all_tenants.filter(pk=app.financing_object_id).update(tenant=tenant_b)
    assert not resolve_application_cbs(app)["ready_for_cbs"]
    FinancingObject.all_tenants.filter(pk=app.financing_object_id).update(tenant=app.tenant)
    conn.tenant = tenant_b
    with pytest.raises(CoreBankingError):
        build_credit_disbursement_payload(app, connector=conn)


def test_obsolete_product_codes_do_not_override_selected_catalogs(mapped):
    app, conn = mapped
    app.product.cbs_product_code = "CRED-CONSO"
    app.product.cbs_repayment_product_code = "LEGACY-OVERRIDE"
    app.product.save(update_fields=["cbs_product_code", "cbs_repayment_product_code"])
    payload = build_credit_disbursement_payload(app, connector=conn)
    assert payload["idProduitCrd"] == "101"
    assert payload["idProduitRemb"] == "202"


def test_manual_credit_product_id_configures_real_mapping(mapped):
    from apps.catalog.serializers import CreditProductSerializer
    app, conn = mapped
    with tenant_context(app.tenant_id):
        serializer = CreditProductSerializer(app.product, data={"cbs_product_code": "OVERRIDE"}, partial=True)
        assert serializer.is_valid(), serializer.errors
        serializer.save()
    assert build_credit_disbursement_payload(app, connector=conn)["idProduitCrd"] == "OVERRIDE"


def test_mechanism_identifier_is_configurable_and_used(mapped):
    from apps.catalog.serializers import RepaymentMethodSerializer
    app, conn = mapped
    mechanism = RepaymentMethod.all_tenants.get(tenant_id=app.tenant_id, code=app.repayment_mechanism)
    with tenant_context(app.tenant_id):
        serializer = RepaymentMethodSerializer(mechanism, data={"cbs_code": "DEGRESSIVE"}, partial=True)
        assert serializer.is_valid(), serializer.errors
        serializer.save()
    assert build_credit_disbursement_payload(app, connector=conn)["idProduitRemb"] == "DEGRESSIVE"


def test_exact_object_wins_and_ambiguous_legacy_object_is_blocked(mapped):
    app, conn = mapped
    with tenant_context(app.tenant_id):
        other = FinancingObject.objects.create(tenant=app.tenant, code="OTHER", label="Autre objet",
            cbs_code="46", purpose_type="CONSUMPTION")
    assert build_credit_disbursement_payload(app, connector=conn)["idObjetFinancement"] == "45"
    app.financing_object = other
    payload = build_credit_disbursement_payload(app, connector=conn)
    assert payload["idObjetFinancement"] == "46"
    assert payload["idProduitCrd"] == "101"
    app.financing_object = None
    with pytest.raises(CoreBankingError, match="financing_object"):
        build_credit_disbursement_payload(app, connector=conn)


def test_generic_submission_is_blocked_without_journal(mapped):
    app, conn = mapped
    with tenant_context(app.tenant_id), pytest.raises(CoreBankingError, match="rejeu générique"):
        send_operation(conn, "SUBMIT_CREDIT", {})
    assert not IntegrationLog.all_tenants.filter(operation="SUBMIT_CREDIT").exists()


def test_mapping_change_invalidates_authorization(mapped):
    app, conn = mapped
    with tenant_context(app.tenant_id):
        prepare_setup(app)
        assert authorization_failures(app) == []
        before = cbs_mapping_snapshot(app)
        RepaymentMethod.objects.filter(code=app.repayment_mechanism).update(cbs_code="303")
        assert cbs_mapping_snapshot(app) != before
        assert authorization_failures(app)
        with pytest.raises(CoreBankingError, match="autorisation à jour"):
            submit_credit_to_cbs(app, connector=conn)
    assert not IntegrationLog.all_tenants.filter(operation="SUBMIT_CREDIT").exists()


@pytest.mark.parametrize("tamper", ["payload", "idempotency"])
def test_sender_rejects_tampered_authorized_request(mapped, tamper):
    app, conn = mapped
    with tenant_context(app.tenant_id):
        prepare_setup(app)
        payload = build_credit_disbursement_payload(app, connector=conn)
        key = f"disburse:{app.pk}"
        if tamper == "payload":
            payload["idProduitCrd"] = "999"
        else:
            key = "arbitrary"
        with pytest.raises(CoreBankingError, match="ne correspond pas"):
            send_operation(conn, "SUBMIT_CREDIT", payload, idempotency_key=key, authorized_application=app)


def test_cbs_failure_keeps_attempt_journal(mapped, monkeypatch):
    app, conn = mapped
    with tenant_context(app.tenant_id):
        prepare_setup(app)
        def reject(*args, **kwargs):
            raise CoreBankingError("Refus CBS fictif du test")
        monkeypatch.setattr(RestAdapter, "send", reject)
        with pytest.raises(CoreBankingError, match="Refus CBS fictif"):
            submit_credit_to_cbs(app, connector=conn)
        log = IntegrationLog.objects.get(operation="SUBMIT_CREDIT")
        assert log.status == "RETRY"
        assert log.attempts == 1
        assert log.request_payload["idProduitCrd"] == "101"
        assert "Refus CBS fictif" in log.error_message
