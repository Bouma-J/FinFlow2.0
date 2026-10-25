"""Décaissement crédit via Perfect POST …/crd/simple."""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import override_settings
from rest_framework.test import APIRequestFactory

from apps.accounts.models import User
from apps.catalog.defaults import ensure_catalog_defaults
from apps.common.tenancy import tenant_context
from apps.corebanking.callback_views import CreditDisbursementCallbackView
from apps.corebanking.disbursement import (
    build_credit_disbursement_payload,
    submit_credit_to_cbs,
)
from apps.corebanking.models import CoreBankingConnector, IntegrationLog
from apps.corebanking.services import CoreBankingError
from apps.credits.models import CreditApplication, Loan
from apps.credits.services import WorkflowError, disburse_application
from apps.tenants.models import Agency
from tests.setup_helpers import prepare_setup

pytestmark = pytest.mark.django_db


@pytest.fixture
def agency_a(tenant_a):
    with tenant_context(tenant_a.id):
        return Agency.objects.create(
            tenant=tenant_a,
            code="AG01",
            name="Agence 01",
            cbs_point_of_service_id="PS01",
        )


@pytest.fixture
def cbs_connector(tenant_a):
    ensure_catalog_defaults(tenant_a)
    with tenant_context(tenant_a.id):
        return CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="CBS Disburse Test",
            protocol=CoreBankingConnector.Protocol.REST,
            base_url="https://cbs.test.local/api",
            mapping_rules={
                "force_simulate": True,
                "disbursement": {
                    "mode": "LOCAL",
                    "callback_secret": "test-callback-secret",
                    "defaults": {
                        "idPointService": "PS01",
                        "idGestionnaire": "GEST01",
                        "idProduitRemb": "COMPTE-COURANT",
                    },
                },
                "simulate": {},
            },
            is_active=True,
        )


@pytest.fixture
def officer(tenant_a, agency_a):
    return User.objects.create(
        username="officer_cbs",
        tenant=tenant_a,
        agency=agency_a,
        cbs_id="GEST-OFFICER",
        employee_id="EMP-1",
    )


@pytest.fixture
def approved_app(tenant_a, product_a, client_a, agency_a, officer):
    with tenant_context(tenant_a.id):
        product_a.cbs_product_code = "CRED-CONSO"
        product_a.cbs_repayment_product_code = ""
        product_a.save(
            update_fields=["cbs_product_code", "cbs_repayment_product_code"]
        )
        client_a.cbs_client_id = "A0012345"
        client_a.save(update_fields=["cbs_client_id"])
        return CreditApplication.objects.create(
            tenant=tenant_a,
            reference="EXT-CRD-001",
            client=client_a,
            product=product_a,
            agency=agency_a,
            amount_requested=Decimal("500000"),
            amount_approved=Decimal("500000"),
            interest_rate=Decimal("7"),
            duration_months=12,
            periodicity="MONTHLY",
            repayment_mechanism="DEGRESSIVE",
            purpose_type="CONSUMPTION",
            currency="XOF",
            status=CreditApplication.Status.APPROVED,
            created_by=officer,
            submitted_by=officer,
        )


def test_build_payload_uses_catalog_and_user_cbs(approved_app, cbs_connector):
    with tenant_context(approved_app.tenant_id):
        with override_settings(PUBLIC_API_BASE_URL="https://finflow.test"):
            payload = build_credit_disbursement_payload(
                approved_app, connector=cbs_connector
            )
    assert payload["externalId"] == "EXT-CRD-001"
    assert payload["codeAdherent"] == "A0012345"
    assert payload["idPointService"] == "PS01"
    assert payload["idPeriodicite"] == "MENSUEL"
    assert payload["taux"] == 7.0
    assert payload["nombreEcheance"] == 12
    assert payload["idObjetFinancement"] == "CONSOMMATION"
    assert payload["idGestionnaire"] == "GEST-OFFICER"
    assert payload["idProduitCrd"] == "CRED-CONSO"
    assert payload["idProduitRemb"] == "COMPTE-COURANT"
    assert payload["montantDemande"] == 500000.0
    assert payload["codeDevise"] == "XOF"
    assert payload["callbackUrl"].endswith(
        f"/api/v1/cbs/callbacks/crd/{approved_app.pk}/"
    )


def test_build_payload_prefers_financing_object_cbs_id(
    approved_app, cbs_connector,
):
    from apps.catalog.models import FinancingObject

    with tenant_context(approved_app.tenant_id):
        FinancingObject.objects.create(
            code="CONSO",
            label="Crédit conso",
            cbs_code="30",
            purpose_type="CONSUMPTION",
            is_active=True,
        )
        payload = build_credit_disbursement_payload(
            approved_app, connector=cbs_connector
        )
    assert payload["idObjetFinancement"] == "30"



def test_submit_credit_local_success(approved_app, cbs_connector):
    with tenant_context(approved_app.tenant_id):
        result = submit_credit_to_cbs(approved_app, connector=cbs_connector)
    assert result["mode"] == "LOCAL"
    assert result["num_contrat"].startswith("CONTRAT-SIM-")
    assert result["num_demande"]
    assert IntegrationLog.all_tenants.filter(
        operation="SUBMIT_CREDIT", status=IntegrationLog.Status.SUCCESS
    ).exists()


def test_submit_credit_local_idempotent(approved_app, cbs_connector):
    with tenant_context(approved_app.tenant_id):
        first = submit_credit_to_cbs(approved_app, connector=cbs_connector)
        second = submit_credit_to_cbs(approved_app, connector=cbs_connector)
    assert first["log_id"] == second["log_id"]
    assert (
        IntegrationLog.all_tenants.filter(operation="SUBMIT_CREDIT").count()
        == 1
    )


def test_submit_credit_simulated_failure(approved_app, cbs_connector):
    cbs_connector.mapping_rules = {
        **cbs_connector.mapping_rules,
        "simulate": {"credit_submit_fail": True},
    }
    cbs_connector.save(update_fields=["mapping_rules"])
    with tenant_context(approved_app.tenant_id):
        with pytest.raises(CoreBankingError, match="Limite de crédit"):
            submit_credit_to_cbs(approved_app, connector=cbs_connector)


def test_disburse_application_pushes_cbs_then_creates_loan(
    approved_app, cbs_connector,
):
    with tenant_context(approved_app.tenant_id):
        with patch(
            "apps.contracts.services.missing_required_contracts",
            return_value=[],
        ), patch(
            "apps.workflow.services.has_pending_conditions",
            return_value=False,
        ):
            executor = prepare_setup(approved_app)
            loan = disburse_application(approved_app, user=executor)

    assert loan.cbs_contract_number.startswith("CONTRAT-SIM-")
    assert loan.cbs_external_id == "EXT-CRD-001"
    assert loan.cbs_disbursement_status == "SUBMITTED"
    assert loan.core_banking_reference == loan.cbs_contract_number
    approved_app.refresh_from_db()
    assert approved_app.status == CreditApplication.Status.DISBURSED
    assert approved_app.cbs_demande_number == loan.cbs_demande_number
    assert approved_app.cbs_demande_ref == loan.cbs_demande_ref
    assert approved_app.cbs_contract_number == loan.cbs_contract_number
    assert approved_app.cbs_operation_date is not None


def test_disburse_blocks_on_cbs_error(approved_app, cbs_connector):
    cbs_connector.mapping_rules = {
        **cbs_connector.mapping_rules,
        "simulate": {"credit_submit_fail": True},
    }
    cbs_connector.save(update_fields=["mapping_rules"])
    with tenant_context(approved_app.tenant_id):
        with patch(
            "apps.contracts.services.missing_required_contracts",
            return_value=[],
        ), patch(
            "apps.workflow.services.has_pending_conditions",
            return_value=False,
        ):
            executor = prepare_setup(approved_app)
            with pytest.raises(WorkflowError, match="Limite de crédit"):
                disburse_application(approved_app, user=executor)
    assert not Loan.all_tenants.filter(application=approved_app).exists()


def test_cbs_callback_updates_loan(approved_app, cbs_connector):
    with tenant_context(approved_app.tenant_id):
        with patch(
            "apps.contracts.services.missing_required_contracts",
            return_value=[],
        ), patch(
            "apps.workflow.services.has_pending_conditions",
            return_value=False,
        ):
            executor = prepare_setup(approved_app)
            loan = disburse_application(approved_app, user=executor)

    factory = APIRequestFactory()
    request = factory.post(
        f"/api/v1/cbs/callbacks/crd/{approved_app.pk}/",
        {
            "responseCode": 200,
            "numDemande": "DEM-FINAL",
            "refDemande": "REF-FINAL",
            "numContrat": "CONTRAT-FINAL",
            "context": "DEBLOQUE",
        },
        format="json",
        HTTP_X_CBS_CALLBACK_SECRET="test-callback-secret",
    )
    response = CreditDisbursementCallbackView.as_view()(
        request, application_id=approved_app.pk
    )
    assert response.status_code == 200
    loan.refresh_from_db()
    assert loan.cbs_contract_number == "CONTRAT-FINAL"
    assert loan.cbs_demande_number == "DEM-FINAL"
    assert loan.cbs_disbursement_status == "DEBLOQUE"
    approved_app.refresh_from_db()
    assert approved_app.cbs_contract_number == "CONTRAT-FINAL"
    assert approved_app.cbs_demande_number == "DEM-FINAL"
    assert approved_app.cbs_demande_ref == "REF-FINAL"


def test_cbs_callback_rejects_missing_secret(approved_app, cbs_connector):
    factory = APIRequestFactory()
    request = factory.post(
        f"/api/v1/cbs/callbacks/crd/{approved_app.pk}/",
        {"context": "HACK", "numContrat": "X"},
        format="json",
    )
    response = CreditDisbursementCallbackView.as_view()(
        request, application_id=approved_app.pk
    )
    assert response.status_code == 400
    assert "secret" in response.data["detail"].lower()


def test_cbs_callback_rejects_when_secret_not_configured(approved_app, cbs_connector):
    cbs_connector.mapping_rules = {
        **cbs_connector.mapping_rules,
        "disbursement": {
            **cbs_connector.mapping_rules.get("disbursement", {}),
            "callback_secret": "",
        },
    }
    cbs_connector.save(update_fields=["mapping_rules"])
    factory = APIRequestFactory()
    request = factory.post(
        f"/api/v1/cbs/callbacks/crd/{approved_app.pk}/",
        {"context": "HACK"},
        format="json",
        HTTP_X_CBS_CALLBACK_SECRET="anything",
    )
    response = CreditDisbursementCallbackView.as_view()(
        request, application_id=approved_app.pk
    )
    assert response.status_code == 400
    assert "callback_secret" in response.data["detail"].lower()
