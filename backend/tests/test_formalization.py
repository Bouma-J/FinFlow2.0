"""Tests formalisation de garantie : initiate, advance, complete — garantie reste ACTIVE."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from apps.common.tenancy import tenant_context
from apps.credits.models import CreditApplication
from apps.guarantees.formalization_services import (
    advance_legal_stage,
    complete_formalization_request,
    formalization_compose_context,
    initiate_formalization_request,
)
from apps.guarantees.models import (
    Guarantee,
    GuaranteeFormalizationRequest,
    GuaranteeMovement,
)
from apps.guarantees.process_services import ProcessError
from apps.workflow.models import ApprovalStep, WorkflowDefinition

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture
def agent(tenant_a):
    return User.objects.create_user(
        username="form_agent",
        password="test-pass-123",
        email="form@example.com",
        tenant=None,
        is_group_level=True,
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def form_circuit(tenant_a):
    with tenant_context(tenant_a.id):
        role = Group.objects.create(name="Validateur Formalisation")
        definition = WorkflowDefinition.objects.create(
            tenant=tenant_a,
            code="CIRCUIT-FORMALISATION",
            name="Circuit formalisation",
            target_type=WorkflowDefinition.TargetType.FORMALISATION,
            version=1,
            is_active=True,
        )
        ApprovalStep.objects.create(
            tenant=tenant_a,
            definition=definition,
            name="Validation formalisation",
            order=1,
            required_group=role,
            sla_hours=24,
            step_kind=ApprovalStep.StepKind.DECISIONAL,
        )
        return definition


def _app(tenant, client_obj, product, *, ref="CR-FORM-1"):
    return CreditApplication.objects.create(
        tenant=tenant,
        client=client_obj,
        product=product,
        reference=ref,
        amount_requested=Decimal("500000"),
        duration_months=12,
        risk_level=1,
    )


def _guarantee(tenant, client_obj, application, *, value="150000", ref="GAR-FORM-1"):
    return Guarantee.objects.create(
        tenant=tenant,
        client=client_obj,
        application=application,
        guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
        description="Bien à formaliser",
        expertise_value=Decimal(value),
        current_value=Decimal(value),
        status=Guarantee.Status.ACTIVE,
        reference=ref,
    )


def test_initiate_requires_application(tenant_a, client_a, agent, form_circuit):
    with tenant_context(tenant_a.id):
        g = Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
            current_value=Decimal("100000"),
            status=Guarantee.Status.ACTIVE,
            reference="GAR-ORPHAN",
        )
        with pytest.raises(ProcessError, match="dossier de crédit"):
            initiate_formalization_request(guarantee=g, user=agent, as_draft=True)


def test_compose_context_by_client_and_application(
    tenant_a, client_a, product_a, agent, form_circuit
):
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a)
        g = _guarantee(tenant_a, client_a, app)
        ctx = formalization_compose_context(client=client_a)
        assert ctx["client_id"] == str(client_a.pk)
        assert len(ctx["credits"]) == 1
        assert len(ctx["guarantees"]) == 1
        assert ctx["guarantees"][0]["id"] == str(g.pk)
        assert ctx["guarantees"][0]["formalization_busy"] is False

        ctx_app = formalization_compose_context(application=app)
        assert ctx_app["application_id"] == str(app.pk)
        assert len(ctx_app["guarantees"]) == 1


def test_initiate_formalization_keeps_guarantee_active(
    tenant_a, client_a, product_a, agent, form_circuit
):
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a)
        g = _guarantee(tenant_a, client_a, app)
        req = initiate_formalization_request(
            guarantee=g,
            user=agent,
            comment="Ouverture dossier",
            notary_name="Me Dupont",
            fees=[
                {
                    "fee_type": "NOTARY",
                    "amount": "25000",
                    "payer": "CLIENT",
                    "label": "Acte notarié",
                }
            ],
            as_draft=True,
        )
        g.refresh_from_db()
        assert req.status == GuaranteeFormalizationRequest.Status.DRAFT
        assert (
            req.legal_stage
            == GuaranteeFormalizationRequest.LegalStage.NOT_SENT
        )
        assert req.application_id == app.pk
        assert req.fees.count() == 1
        assert req.fees_client_total == Decimal("25000")
        assert g.status == Guarantee.Status.ACTIVE
        assert g.formalized_at is None


def test_advance_legal_stage(tenant_a, client_a, product_a, agent, form_circuit):
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a, ref="CR-FORM-2")
        g = _guarantee(tenant_a, client_a, app, ref="GAR-FORM-2")
        req = initiate_formalization_request(
            guarantee=g, user=agent, as_draft=True
        )
        updated = advance_legal_stage(
            req,
            GuaranteeFormalizationRequest.LegalStage.AT_NOTARY,
            user=agent,
            notary_name="Me Martin",
        )
        assert updated.status == GuaranteeFormalizationRequest.Status.IN_PROGRESS
        assert (
            updated.legal_stage
            == GuaranteeFormalizationRequest.LegalStage.AT_NOTARY
        )
        assert updated.notary_name == "Me Martin"
        assert updated.sent_to_notary_at is not None

        updated = advance_legal_stage(
            updated,
            GuaranteeFormalizationRequest.LegalStage.SIGNED,
            user=agent,
        )
        assert (
            updated.legal_stage
            == GuaranteeFormalizationRequest.LegalStage.SIGNED
        )
        g.refresh_from_db()
        assert g.status == Guarantee.Status.ACTIVE


def test_complete_formalization_stays_active(
    tenant_a, client_a, product_a, agent, form_circuit
):
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a, ref="CR-FORM-3")
        g = _guarantee(tenant_a, client_a, app, ref="GAR-FORM-3")
        req = initiate_formalization_request(
            guarantee=g,
            user=agent,
            notary_name="Me Leroy",
            as_draft=True,
        )
        advance_legal_stage(
            req,
            GuaranteeFormalizationRequest.LegalStage.REGISTERED,
            user=agent,
            registration_number="TF-99",
            registration_date="2024-01-15",
            registration_authority="Conservation",
        )
        req.refresh_from_db()
        req.status = GuaranteeFormalizationRequest.Status.APPROVED
        req.save(update_fields=["status", "updated_at"])
        complete_formalization_request(req, user=agent)
        req.refresh_from_db()
        g.refresh_from_db()
        assert req.status == GuaranteeFormalizationRequest.Status.COMPLETED
        assert req.legal_stage == GuaranteeFormalizationRequest.LegalStage.DONE
        assert g.status == Guarantee.Status.ACTIVE
        assert g.formalized_at is not None
        assert g.registration_number == "TF-99"
        assert GuaranteeMovement.objects.filter(
            guarantee=g,
            movement_type=GuaranteeMovement.MovementType.FORMALIZATION,
        ).exists()
