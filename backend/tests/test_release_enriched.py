"""Tests main levée enrichie : brouillon, demande client, acte, clôture."""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.common.tenancy import tenant_context
from apps.guarantees.models import Guarantee, GuaranteeReleaseRequest
from apps.guarantees.process_services import (
    ProcessError,
    complete_release_request,
    generate_release_acte,
    initiate_release_request,
    submit_release_request,
    upload_release_acte_signed,
)
from apps.workflow.models import ApprovalStep, WorkflowDefinition

User = get_user_model()
pytestmark = pytest.mark.django_db

CBS_SETTLED = {
    "settled": True,
    "outstanding": Decimal("0"),
    "currency": "XAF",
    "raw": {},
    "log_id": "x",
    "schedule": [],
}

_cbs_assert = patch(
    "apps.guarantees.process_services.assert_loan_settled",
    return_value=CBS_SETTLED,
)
_cbs_get = patch(
    "apps.guarantees.process_services.get_loan_status",
    return_value=CBS_SETTLED,
)


@pytest.fixture
def agent(tenant_a):
    return User.objects.create_user(
        username="ml_agent",
        password="test-pass-123",
        email="ml@example.com",
        tenant=None,
        is_group_level=True,
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def api(agent, tenant_a):
    client = APIClient()
    client.force_authenticate(user=agent)
    client.credentials(HTTP_X_TENANT_ID=str(tenant_a.id))
    return client


@pytest.fixture
def ml_circuit(tenant_a):
    with tenant_context(tenant_a.id):
        role = Group.objects.create(name="Validateur ML")
        definition = WorkflowDefinition.objects.create(
            tenant=tenant_a,
            code="CIRCUIT-ML",
            name="Circuit main levée",
            target_type=WorkflowDefinition.TargetType.MAIN_LEVEE,
            version=1,
            is_active=True,
        )
        ApprovalStep.objects.create(
            tenant=tenant_a,
            definition=definition,
            name="Validation ML",
            order=1,
            required_group=role,
            sla_hours=24,
            step_kind=ApprovalStep.StepKind.DECISIONAL,
        )
        return definition


def _guarantee(tenant, client_obj):
    return Guarantee.objects.create(
        tenant=tenant,
        client=client_obj,
        guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
        description="Hypothèque test",
        expertise_value=Decimal("500000"),
        current_value=Decimal("500000"),
        status=Guarantee.Status.ACTIVE,
        reference="GAR-ML-1",
    )


def _attach_demande(api, req_id):
    upload = SimpleUploadedFile(
        "demande.pdf", b"%PDF-1.4 demande", content_type="application/pdf"
    )
    r = api.post(
        f"/api/v1/guarantee-releases/{req_id}/documents/",
        {"file": upload, "name": "Demande client", "category": "ML_DEMANDE"},
        format="multipart",
    )
    assert r.status_code == 201, r.content


@_cbs_get
@_cbs_assert
def test_initiate_draft_and_busy(
    _assert, _get, tenant_a, client_a, agent, ml_circuit
):
    with tenant_context(tenant_a.id):
        g = _guarantee(tenant_a, client_a)
        req = initiate_release_request(
            guarantee=g,
            user=agent,
            cbs_loan_reference="LOAN-1",
            as_draft=True,
            fees=[{"fee_type": "NOTARY", "amount": "10000", "payer": "CLIENT"}],
        )
        assert req.status == GuaranteeReleaseRequest.Status.DRAFT
        assert req.fees.count() == 1
        with pytest.raises(ProcessError, match="déjà en cours"):
            initiate_release_request(
                guarantee=g,
                user=agent,
                cbs_loan_reference="LOAN-1",
                as_draft=True,
            )


@_cbs_get
@_cbs_assert
def test_submit_requires_demande_and_acte(
    _assert, _get, api, tenant_a, client_a, agent, ml_circuit
):
    with tenant_context(tenant_a.id):
        g = _guarantee(tenant_a, client_a)
        req = initiate_release_request(
            guarantee=g,
            user=agent,
            cbs_loan_reference="LOAN-1",
            as_draft=True,
        )
        with pytest.raises(ProcessError, match="demande"):
            submit_release_request(req, user=agent)

    _attach_demande(api, req.id)

    with tenant_context(tenant_a.id):
        req.refresh_from_db()
        with pytest.raises(ProcessError, match="acte"):
            submit_release_request(req, user=agent)
        generate_release_acte(req, user=agent)
        submit_release_request(req, user=agent)
        req.refresh_from_db()
        assert req.status == GuaranteeReleaseRequest.Status.IN_APPROVAL


@_cbs_get
@_cbs_assert
def test_complete_requires_signed_acte(
    _assert, _get, api, tenant_a, client_a, agent, ml_circuit
):
    with tenant_context(tenant_a.id):
        g = _guarantee(tenant_a, client_a)
        req = initiate_release_request(
            guarantee=g,
            user=agent,
            cbs_loan_reference="LOAN-1",
            as_draft=True,
        )
        generate_release_acte(req, user=agent)
        req.status = GuaranteeReleaseRequest.Status.APPROVED
        req.save(update_fields=["status"])
        with pytest.raises(ProcessError, match="signé"):
            complete_release_request(req)

        signed = SimpleUploadedFile(
            "acte-signe.pdf", b"%PDF-1.4 signe", content_type="application/pdf"
        )
        upload_release_acte_signed(req, signed, user=agent)
        req.refresh_from_db()
        g.refresh_from_db()
        assert req.status == GuaranteeReleaseRequest.Status.COMPLETED
        assert req.has_signed_acte()
        assert g.status == Guarantee.Status.RELEASED


@_cbs_get
@_cbs_assert
def test_api_generate_acte(_assert, _get, api, tenant_a, client_a, agent, ml_circuit):
    with tenant_context(tenant_a.id):
        g = _guarantee(tenant_a, client_a)
        req = initiate_release_request(
            guarantee=g,
            user=agent,
            cbs_loan_reference="LOAN-1",
            as_draft=True,
        )
    r = api.post(f"/api/v1/guarantee-releases/{req.id}/generate-acte/")
    assert r.status_code == 200, r.content
    assert r.data["has_generated_acte"] is True
    assert r.data["acte_status"] == "GENERATED"
