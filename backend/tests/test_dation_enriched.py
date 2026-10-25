"""Tests dation enrichie : biens, frais, calculs, clôture, GED."""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.common.tenancy import tenant_context
from apps.guarantees.models import DationRequest, Guarantee
from apps.guarantees.process_services import (
    complete_dation_request,
    ensure_dation_document_categories,
    initiate_dation_request,
    submit_dation_request,
)
from apps.workflow.models import ApprovalStep, WorkflowDefinition

User = get_user_model()

pytestmark = pytest.mark.django_db

CBS_OK = {
    "total_outstanding": Decimal("100000"),
    "currency": "XAF",
    "breakdown": [],
    "raw": {},
    "log_id": "x",
}


@pytest.fixture
def agent(tenant_a):
    return User.objects.create_user(
        username="dation_agent",
        password="test-pass-123",
        email="dation@example.com",
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
def dation_circuit(tenant_a):
    with tenant_context(tenant_a.id):
        role = Group.objects.create(name="Validateur Dation")
        definition = WorkflowDefinition.objects.create(
            tenant=tenant_a,
            code="CIRCUIT-DATION",
            name="Circuit dation",
            target_type=WorkflowDefinition.TargetType.DATION,
            version=1,
            is_active=True,
        )
        ApprovalStep.objects.create(
            tenant=tenant_a,
            definition=definition,
            name="Validation dation",
            order=1,
            required_group=role,
            sla_hours=24,
            step_kind=ApprovalStep.StepKind.DECISIONAL,
        )
        return definition


def _guarantee(tenant, client_obj, *, value="60000", ref="GAR-1"):
    g = Guarantee.objects.create(
        tenant=tenant,
        client=client_obj,
        guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
        description="Terrain test",
        expertise_value=Decimal(value),
        current_value=Decimal(value),
        status=Guarantee.Status.ACTIVE,
        reference=ref,
    )
    return g


@patch(
    "apps.guarantees.process_services.assert_client_outstanding_for_dation",
    return_value=CBS_OK,
)
def test_initiate_draft_with_fees_and_settlement(
    _cbs, tenant_a, client_a, agent, dation_circuit
):
    with tenant_context(tenant_a.id):
        client_a.cbs_client_id = "CBS-001"
        client_a.save(update_fields=["cbs_client_id"])
        g = _guarantee(tenant_a, client_a)
        req = initiate_dation_request(
            client=client_a,
            user=agent,
            cbs_client_id="CBS-001",
            guarantee_ids=[str(g.id)],
            additional_assets=[
                {
                    "description": "Véhicule occasion",
                    "value": "30000",
                    "asset_type": "VEHICLE",
                }
            ],
            fees=[
                {
                    "fee_type": "NOTARY",
                    "amount": "5000",
                    "payer": "CLIENT",
                    "label": "Acte",
                },
                {
                    "fee_type": "APPRAISAL",
                    "amount": "2000",
                    "payer": "INSTITUTION",
                },
            ],
            as_draft=True,
        )
        assert req.status == DationRequest.Status.DRAFT
        assert req.assets.count() == 2
        assert req.fees.count() == 2
        # 60000 + 30000 = 90000 biens ; créance 100000 + frais client 5000 = 105000
        assert req.assets_total_value() == Decimal("90000")
        assert req.fees_client_total == Decimal("5000")
        assert req.fees_institution_total == Decimal("2000")
        assert req.claim_to_cover == Decimal("105000")
        assert req.residual_balance == Decimal("15000")
        assert req.surplus_amount == Decimal("0")
        assert req.covers_claim() is False


@patch(
    "apps.guarantees.process_services.assert_client_outstanding_for_dation",
    return_value=CBS_OK,
)
def test_complete_realizes_source_guarantees(
    _cbs, tenant_a, client_a, agent, dation_circuit
):
    with tenant_context(tenant_a.id):
        client_a.cbs_client_id = "CBS-001"
        client_a.save(update_fields=["cbs_client_id"])
        g = _guarantee(tenant_a, client_a, value="120000")
        req = initiate_dation_request(
            client=client_a,
            user=agent,
            cbs_client_id="CBS-001",
            guarantee_ids=[str(g.id)],
            as_draft=True,
        )
        assert req.covers_claim() is True
        complete_dation_request(req)
        req.refresh_from_db()
        g.refresh_from_db()
        assert req.status == DationRequest.Status.COMPLETED
        assert req.resulting_guarantee_id is not None
        assert g.status == Guarantee.Status.REALIZED
        assert g.movements.filter(
            movement_type="REALIZATION"
        ).exists()
        assert req.resulting_guarantee.guarantee_type == Guarantee.GuaranteeType.DATION
        from apps.guarantees.serializers import GuaranteeSerializer

        src = GuaranteeSerializer(g).data
        assert src["completed_dation_id"] == str(req.id)
        assert src["open_dation_id"] is None
        created = GuaranteeSerializer(req.resulting_guarantee).data
        assert created["origin_dation_id"] == str(req.id)


@patch(
    "apps.guarantees.process_services.assert_client_outstanding_for_dation",
    return_value=CBS_OK,
)
def test_busy_guarantee_blocked(
    _cbs, tenant_a, client_a, agent, dation_circuit
):
    with tenant_context(tenant_a.id):
        client_a.cbs_client_id = "CBS-001"
        client_a.save(update_fields=["cbs_client_id"])
        g = _guarantee(tenant_a, client_a)
        initiate_dation_request(
            client=client_a,
            user=agent,
            cbs_client_id="CBS-001",
            guarantee_ids=[str(g.id)],
            as_draft=True,
        )
        from apps.guarantees.process_services import ProcessError

        with pytest.raises(ProcessError, match="déjà engagée"):
            initiate_dation_request(
                client=client_a,
                user=agent,
                cbs_client_id="CBS-001",
                guarantee_ids=[str(g.id)],
                as_draft=True,
            )


@patch(
    "apps.guarantees.process_services.assert_client_outstanding_for_dation",
    return_value=CBS_OK,
)
def test_submit_requires_full_coverage_when_flagged(
    _cbs, tenant_a, client_a, agent, dation_circuit
):
    with tenant_context(tenant_a.id):
        client_a.cbs_client_id = "CBS-001"
        client_a.save(update_fields=["cbs_client_id"])
        g = _guarantee(tenant_a, client_a, value="10000")
        req = initiate_dation_request(
            client=client_a,
            user=agent,
            cbs_client_id="CBS-001",
            guarantee_ids=[str(g.id)],
            as_draft=True,
            require_full_coverage=True,
        )
        from apps.guarantees.process_services import ProcessError

        with pytest.raises(ProcessError, match="Couverture insuffisante"):
            submit_dation_request(req, user=agent)


@patch(
    "apps.guarantees.process_services.assert_client_outstanding_for_dation",
    return_value=CBS_OK,
)
def test_api_documents_upload(
    _cbs, api, tenant_a, client_a, agent, dation_circuit
):
    with tenant_context(tenant_a.id):
        client_a.cbs_client_id = "CBS-001"
        client_a.save(update_fields=["cbs_client_id"])
        g = _guarantee(tenant_a, client_a)
        req = initiate_dation_request(
            client=client_a,
            user=agent,
            cbs_client_id="CBS-001",
            guarantee_ids=[str(g.id)],
            as_draft=True,
        )
        ensure_dation_document_categories(tenant_a)
        asset = req.assets.first()

    upload = SimpleUploadedFile(
        "photo.jpg",
        b"\xff\xd8\xff fakejpeg",
        content_type="image/jpeg",
    )
    r = api.post(
        f"/api/v1/dation-requests/{req.id}/documents/",
        {
            "file": upload,
            "name": "Photo terrain",
            "category": "DAT_PHOTO",
            "asset": str(asset.id),
        },
        format="multipart",
    )
    assert r.status_code == 201, r.content

    r = api.get(f"/api/v1/dation-requests/{req.id}/documents/")
    assert r.status_code == 200
    assert len(r.data) >= 1
    assert r.data[0]["name"] == "Photo terrain"


@patch(
    "apps.guarantees.process_services.assert_client_outstanding_for_dation",
    return_value=CBS_OK,
)
def test_api_add_fee_updates_settlement(
    _cbs, api, tenant_a, client_a, agent, dation_circuit
):
    with tenant_context(tenant_a.id):
        client_a.cbs_client_id = "CBS-001"
        client_a.save(update_fields=["cbs_client_id"])
        g = _guarantee(tenant_a, client_a, value="120000")
        req = initiate_dation_request(
            client=client_a,
            user=agent,
            cbs_client_id="CBS-001",
            guarantee_ids=[str(g.id)],
            as_draft=True,
        )

    r = api.post(
        f"/api/v1/dation-requests/{req.id}/add-fee/",
        {
            "fee_type": "REGISTRATION",
            "amount": "8000",
            "payer": "CLIENT",
            "label": "Enregistrement",
        },
        format="json",
    )
    assert r.status_code == 201, r.content
    assert Decimal(r.data["dation"]["fees_client_total"]) == Decimal("8000")
    assert Decimal(r.data["dation"]["claim_to_cover"]) == Decimal("108000")
