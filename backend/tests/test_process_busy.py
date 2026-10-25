"""Verrou partagé dation / formalisation / main levée."""
from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.common.tenancy import tenant_context
from apps.credits.models import CreditApplication
from apps.guarantees.formalization_services import (
    formalization_compose_context,
    initiate_formalization_request,
)
from apps.guarantees.models import Guarantee
from apps.guarantees.process_services import (
    ProcessError,
    initiate_dation_request,
    initiate_release_request,
)

pytestmark = pytest.mark.django_db

CBS_DATION = {
    "total_outstanding": Decimal("100000"),
    "currency": "XAF",
    "breakdown": [],
    "raw": {},
    "log_id": "x",
}
CBS_SETTLED = {
    "settled": True,
    "outstanding": Decimal("0"),
    "currency": "XAF",
    "raw": {},
    "log_id": "x",
    "schedule": [],
}


@pytest.fixture
def agent(tenant_a):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.create_user(
        username="busy_agent",
        password="test-pass-123",
        email="busy@example.com",
        tenant=None,
        is_group_level=True,
        is_staff=True,
        is_superuser=True,
    )


def _app(tenant, client_obj, product):
    return CreditApplication.objects.create(
        tenant=tenant,
        client=client_obj,
        product=product,
        reference="CR-BUSY",
        amount_requested=Decimal("500000"),
        duration_months=12,
        risk_level=1,
    )


def _guarantee(tenant, client_obj, application=None):
    return Guarantee.objects.create(
        tenant=tenant,
        client=client_obj,
        application=application,
        guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
        current_value=Decimal("150000"),
        expertise_value=Decimal("150000"),
        status=Guarantee.Status.ACTIVE,
        reference="GAR-BUSY",
    )


@patch(
    "apps.guarantees.process_services.assert_client_outstanding_for_dation",
    return_value=CBS_DATION,
)
def test_open_dation_blocks_formalization_and_release(
    _cbs, tenant_a, client_a, product_a, agent
):
    with tenant_context(tenant_a.id):
        client_a.cbs_client_id = "CBS-BUSY"
        client_a.save(update_fields=["cbs_client_id"])
        app = _app(tenant_a, client_a, product_a)
        g = _guarantee(tenant_a, client_a, app)
        initiate_dation_request(
            client=client_a,
            user=agent,
            cbs_client_id="CBS-BUSY",
            guarantee_ids=[str(g.id)],
            as_draft=True,
        )
        with pytest.raises(ProcessError, match="dation"):
            initiate_formalization_request(guarantee=g, user=agent, as_draft=True)
        with patch(
            "apps.guarantees.process_services.assert_loan_settled",
            return_value=CBS_SETTLED,
        ):
            with pytest.raises(ProcessError, match="dation"):
                initiate_release_request(
                    guarantee=g,
                    user=agent,
                    cbs_loan_reference="LOAN-BUSY",
                    as_draft=True,
                )
        ctx = formalization_compose_context(application=app)
        row = ctx["guarantees"][0]
        assert row["process_busy"]["kind"] == "DATION"
        assert row["formalization_busy"] is True


def test_open_formalization_blocks_dation(tenant_a, client_a, product_a, agent):
    with tenant_context(tenant_a.id):
        client_a.cbs_client_id = "CBS-BUSY-F"
        client_a.save(update_fields=["cbs_client_id"])
        app = _app(tenant_a, client_a, product_a)
        g = _guarantee(tenant_a, client_a, app)
        initiate_formalization_request(guarantee=g, user=agent, as_draft=True)
        with patch(
            "apps.guarantees.process_services.assert_client_outstanding_for_dation",
            return_value=CBS_DATION,
        ):
            with pytest.raises(ProcessError, match="formalisation"):
                initiate_dation_request(
                    client=client_a,
                    user=agent,
                    cbs_client_id="CBS-BUSY-F",
                    guarantee_ids=[str(g.id)],
                    as_draft=True,
                )


@patch(
    "apps.guarantees.process_services.assert_loan_settled",
    return_value=CBS_SETTLED,
)
def test_open_release_blocks_formalization(
    _cbs, tenant_a, client_a, product_a, agent
):
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a)
        g = _guarantee(tenant_a, client_a, app)
        initiate_release_request(
            guarantee=g,
            user=agent,
            cbs_loan_reference="LOAN-BUSY-ML",
            as_draft=True,
        )
        with pytest.raises(ProcessError, match="main levée"):
            initiate_formalization_request(guarantee=g, user=agent, as_draft=True)


def test_patch_guarantee_blocked_when_busy(tenant_a, client_a, product_a, agent):
    from rest_framework.test import APIClient

    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a)
        g = _guarantee(tenant_a, client_a, app)
        g.document_type = "TITLE_DEED"
        g.document_number = "TIT-BUSY-1"
        g.save(update_fields=["document_type", "document_number", "updated_at"])
        initiate_formalization_request(guarantee=g, user=agent, as_draft=True)

    api = APIClient()
    api.force_authenticate(user=agent)
    api.credentials(HTTP_X_TENANT_ID=str(tenant_a.id))
    res = api.patch(
        f"/api/v1/guarantees/{g.id}/",
        {"description": "Tentative pendant formalisation"},
        format="json",
    )
    assert res.status_code == 400
    errors = res.json().get("errors", res.json())
    detail = errors.get("detail") or str(errors)
    assert "formalisation" in str(detail).lower()
