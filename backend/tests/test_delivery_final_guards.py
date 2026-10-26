from unittest.mock import Mock

import pytest

from apps.common.tenancy import tenant_context
from apps.corebanking.disbursement import submit_credit_to_cbs
from apps.corebanking.models import CoreBankingConnector
from apps.corebanking.services import CoreBankingError
from apps.credits.models import CreditApplication, Loan
from apps.credits.services import disburse_application
from apps.workflow.services import WorkflowError
from tests.setup_helpers import prepare_setup

pytestmark = pytest.mark.django_db


@pytest.fixture
def approved(tenant_a, client_a, product_a):
    return CreditApplication.all_tenants.create(tenant=tenant_a, client=client_a, product=product_a,
        status="APPROVED", amount_requested=100000, amount_approved=100000, duration_months=12, currency="XOF")


@pytest.mark.parametrize("response", [None, {}])
def test_no_positive_cbs_result_never_creates_local_loan(approved, monkeypatch, response):
    from tests.setup_helpers import configure_local_cbs
    configure_local_cbs(approved)
    actor = prepare_setup(approved)
    cbs = Mock(return_value=response)
    monkeypatch.setattr("apps.corebanking.disbursement.submit_credit_to_cbs", cbs)
    with tenant_context(approved.tenant_id), pytest.raises(WorkflowError, match="pas confirmé"):
        disburse_application(approved, user=actor)
    assert not Loan.all_tenants.filter(application=approved).exists()


def test_direct_skip_cbs_never_creates_local_loan(approved, monkeypatch):
    from tests.setup_helpers import configure_local_cbs
    configure_local_cbs(approved)
    actor = prepare_setup(approved)
    cbs = Mock()
    monkeypatch.setattr("apps.corebanking.disbursement.submit_credit_to_cbs", cbs)
    with tenant_context(approved.tenant_id), pytest.raises(WorkflowError, match="contournement"):
        disburse_application(approved, user=actor, skip_cbs=True)
    cbs.assert_not_called()
    assert not Loan.all_tenants.filter(application=approved).exists()


def test_monthly_effort_uses_preserved_frequency_after_referential_change(approved, monkeypatch):
    from apps.credits.models import FinancialAnalysis
    from decimal import Decimal
    approved.periodicity = "WEEKLY"
    approved.configuration_snapshot = {"simulation": {"conventions": {"engine": "CONFIGURED", "periods_per_year": {"WEEKLY": 52}}}}
    analysis = FinancialAnalysis(application=approved, new_installment=Decimal("120"))
    monkeypatch.setattr("apps.catalog.cbs_resolve.resolve_periodicity_periods_per_year", lambda *args, **kwargs: 100)
    assert analysis.monthly_new_installment == Decimal("520")


@pytest.mark.parametrize("protocol,url,rules", [
    ("REST", "", {}), ("REST", "https://cbs.invalid", {"disbursement": {"mode": "LOCAL"}}),
    ("REST", "https://cbs.invalid", {"force_simulate": True, "disbursement": {"mode": "CBS"}}),
    ("SOAP", "https://cbs.invalid", {"disbursement": {"mode": "CBS"}}),
])
def test_production_setup_rejects_simulation_before_any_network_call(approved, settings, monkeypatch, protocol, url, rules):
    settings.ALLOW_SIMULATED_CBS_SETUP = False
    connector = CoreBankingConnector(tenant=approved.tenant, name="Simulation interdite", protocol=protocol, base_url=url, mapping_rules=rules)
    cbs = Mock(side_effect=AssertionError("Aucun réseau réel en test"))
    monkeypatch.setattr("apps.corebanking.disbursement.send_operation", cbs)
    with pytest.raises(CoreBankingError, match="réelle exige"):
        submit_credit_to_cbs(approved, connector=connector)
    cbs.assert_not_called()
