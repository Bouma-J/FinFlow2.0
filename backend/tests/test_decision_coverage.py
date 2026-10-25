"""Couverture décisionnelle des circuits d'approbation.

Un circuit dont une tranche de montant ne comporte aucune étape décisionnelle
approuve tout de même les dossiers concernés — sur les seuls avis consultatifs.
Le dossier avance, mais aucun décideur n'intervient formellement : c'est une
faille de gouvernance, pas un blocage. Ces tests verrouillent le diagnostic,
les garde-fous d'API, et le comportement réel du moteur.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.common.tenancy import tenant_context
from apps.credits.models import CreditApplication, FinancialAnalysis
from apps.credits.services import submit_application
from apps.workflow.models import (
    ApprovalStep,
    ApprovalTask,
    WorkflowDefinition,
    WorkflowInstance,
)
from apps.workflow.services import compute_decision_gaps, process_decision

pytestmark = pytest.mark.django_db

THRESHOLD = Decimal("10000000")


def _definition(tenant, *, code, is_active=True):
    return WorkflowDefinition.objects.create(
        tenant=tenant, code=code, name=code, version=1, is_active=is_active
    )


def _step(tenant, definition, *, name, order, group, kind, low=None, high=None,
          min_risk=None):
    return ApprovalStep.objects.create(
        tenant=tenant,
        definition=definition,
        name=name,
        order=order,
        required_group=group,
        sla_hours=24,
        step_kind=kind,
        min_amount=low,
        max_amount=high,
        min_risk_level=min_risk,
    )


def _seed_style_circuit(tenant, *, agency_kind, code="CIRCUIT-STD"):
    """Reproduit le circuit crédit du seed, la nature de l'étape agence variant."""
    from apps.accounts.services import create_tenant_role

    analyst = create_tenant_role(tenant, f"Analyste {code}").group
    manager = create_tenant_role(tenant, f"Agence {code}").group
    committee = create_tenant_role(tenant, f"Comité {code}").group
    definition = _definition(tenant, code=code)
    _step(
        tenant, definition, name="Analyse crédit", order=1, group=analyst,
        kind=ApprovalStep.StepKind.CONSULTATIVE,
    )
    _step(
        tenant, definition, name="Validation agence", order=2, group=manager,
        kind=agency_kind, high=THRESHOLD,
    )
    _step(
        tenant, definition, name="Comité de crédit", order=3, group=committee,
        kind=ApprovalStep.StepKind.DECISIONAL, low=THRESHOLD,
    )
    return definition, analyst, manager, committee


# --- Diagnostic ------------------------------------------------------------


def test_consultative_agency_step_leaves_low_amounts_without_decider(tenant_a):
    """C'était la configuration livrée par le seed : trou sur ]0 ; 10 M[."""
    with tenant_context(tenant_a.id):
        definition, *_ = _seed_style_circuit(
            tenant_a, agency_kind=ApprovalStep.StepKind.CONSULTATIVE
        )
        gaps = compute_decision_gaps(definition)

    assert gaps == [(Decimal("0"), Decimal("9999999.99"))]


def test_decisional_agency_step_covers_every_amount(tenant_a):
    with tenant_context(tenant_a.id):
        definition, *_ = _seed_style_circuit(
            tenant_a, agency_kind=ApprovalStep.StepKind.DECISIONAL
        )
        assert compute_decision_gaps(definition) == []


def test_definition_without_step_reports_no_gap(tenant_a):
    """Un circuit vide est en cours de création : rien à diagnostiquer."""
    with tenant_context(tenant_a.id):
        assert compute_decision_gaps(_definition(tenant_a, code="VIDE")) == []


def test_risk_conditioned_decider_does_not_count_as_coverage(tenant_a):
    """Un décideur soumis à un risque minimal ne couvre pas les dossiers sains."""
    group = Group.objects.create(name="Comité risque")
    with tenant_context(tenant_a.id):
        definition = _definition(tenant_a, code="RISQUE")
        _step(
            tenant_a, definition, name="Comité", order=1, group=group,
            kind=ApprovalStep.StepKind.DECISIONAL, min_risk=5,
        )
        assert compute_decision_gaps(definition) == [(Decimal("0"), None)]


def test_gap_above_the_last_ceiling_is_reported(tenant_a):
    """Aucune étape au-delà du plafond : la tranche haute est signalée."""
    group = Group.objects.create(name="Agence plafond")
    with tenant_context(tenant_a.id):
        definition = _definition(tenant_a, code="PLAFOND")
        _step(
            tenant_a, definition, name="Agence", order=1, group=group,
            kind=ApprovalStep.StepKind.DECISIONAL, high=THRESHOLD,
        )
        assert compute_decision_gaps(definition) == [
            (Decimal("10000000.01"), None)
        ]


# --- Comportement réel du moteur -------------------------------------------


def test_credit_under_threshold_is_decided_by_the_agency_step(
    tenant_a, product_a, client_a
):
    """Après correction, un dossier sous le seuil passe par un vrai décideur.

    Ce test verrouille aussi le fait que le moteur mène bien le dossier
    jusqu'à APPROVED : l'absence d'étape décisionnelle ne bloquait pas
    l'approbation, elle la privait de décideur.
    """
    submitter = User.objects.create(username="cov_sub", tenant=tenant_a)

    with tenant_context(tenant_a.id):
        definition, analyst, manager, _ = _seed_style_circuit(
            tenant_a, agency_kind=ApprovalStep.StepKind.DECISIONAL
        )
        u_analyst = User.objects.create(username="cov_analyst", tenant=tenant_a)
        u_analyst.groups.add(analyst)
        u_manager = User.objects.create(username="cov_manager", tenant=tenant_a)
        u_manager.groups.add(manager)

        application = CreditApplication.objects.create(
            tenant=tenant_a, reference="COV-1", client=client_a,
            product=product_a, amount_requested=Decimal("1500000"),
            duration_months=12, risk_level=1, submitted_by=submitter,
        )
        FinancialAnalysis.objects.create(
            tenant=tenant_a, application=application, is_reference=True,
            recommendation=FinancialAnalysis.Recommendation.FAVORABLE,
            salary_income=Decimal("300000"), client_type="INDIVIDUAL",
        )
        submit_application(application, submitter)

        instance = WorkflowInstance.objects.get(object_id=application.id)
        actors = {"Analyse crédit": u_analyst, "Validation agence": u_manager}
        decided_kinds = []
        for _ in range(4):
            pending = list(
                ApprovalTask.objects.filter(
                    instance=instance, status=ApprovalTask.Status.PENDING
                )
            )
            if not pending:
                break
            for task in pending:
                decided_kinds.append(task.step.step_kind)
                process_decision(
                    task,
                    actors[task.step.name],
                    ApprovalTask.Status.APPROVED,
                    opinion=ApprovalTask.Opinion.FAVORABLE,
                )

        application.refresh_from_db()
        assert application.status == CreditApplication.Status.APPROVED
        assert ApprovalStep.StepKind.DECISIONAL in decided_kinds


# --- Garde-fous d'API ------------------------------------------------------


def _admin(tenant):
    return User.objects.create(
        username=f"cov_admin_{tenant.code}",
        tenant=tenant,
        is_superuser=True,
        is_staff=True,
    )


def _api(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


def test_api_exposes_decision_gaps(tenant_a):
    with tenant_context(tenant_a.id):
        holed, *_ = _seed_style_circuit(
            tenant_a, agency_kind=ApprovalStep.StepKind.CONSULTATIVE, code="TROUE"
        )
        _seed_style_circuit(
            tenant_a, agency_kind=ApprovalStep.StepKind.DECISIONAL, code="SAIN"
        )

    res = _api(_admin(tenant_a)).get(
        "/api/v1/workflow-definitions/", HTTP_X_TENANT_ID=str(tenant_a.id)
    )
    assert res.status_code == 200
    payload = res.json()
    by_code = {d["code"]: d for d in payload.get("results", payload)}

    assert by_code["SAIN"]["decision_gaps"] is None
    gaps = by_code["TROUE"]["decision_gaps"]
    assert gaps is not None
    assert "9 999 999.99" in gaps["label"]
    assert str(holed.code) == "TROUE"


def test_api_refuses_to_activate_a_holed_circuit(tenant_a):
    with tenant_context(tenant_a.id):
        definition, *_ = _seed_style_circuit(
            tenant_a, agency_kind=ApprovalStep.StepKind.CONSULTATIVE, code="ACT"
        )
        definition.is_active = False
        definition.save(update_fields=["is_active"])

    res = _api(_admin(tenant_a)).patch(
        f"/api/v1/workflow-definitions/{definition.id}/",
        {"is_active": True},
        format="json",
        HTTP_X_TENANT_ID=str(tenant_a.id),
    )

    assert res.status_code == 400
    assert "décisionnelle" in str(res.json())
    definition.refresh_from_db()
    assert definition.is_active is False


def test_api_refuses_a_step_edit_that_opens_a_gap(tenant_a):
    """Un circuit actif et sain ne peut pas être dégradé en circuit troué."""
    with tenant_context(tenant_a.id):
        definition, _, manager, _ = _seed_style_circuit(
            tenant_a, agency_kind=ApprovalStep.StepKind.DECISIONAL, code="DEGRAD"
        )
        agency_step = ApprovalStep.objects.get(
            definition=definition, name="Validation agence"
        )

    res = _api(_admin(tenant_a)).patch(
        f"/api/v1/workflow-steps/{agency_step.id}/",
        {"step_kind": "CONSULTATIVE"},
        format="json",
        HTTP_X_TENANT_ID=str(tenant_a.id),
    )

    assert res.status_code == 400
    agency_step.refresh_from_db()
    assert agency_step.step_kind == ApprovalStep.StepKind.DECISIONAL


def test_api_allows_building_a_circuit_step_by_step(tenant_a):
    """La construction progressive reste possible : pas de faux blocage."""
    from apps.accounts.services import create_tenant_role

    group = create_tenant_role(tenant_a, "Analyste construction").group
    with tenant_context(tenant_a.id):
        definition = _definition(tenant_a, code="CONSTR")

    api = _api(_admin(tenant_a))
    base = {
        "definition": str(definition.id),
        "required_group": group.id,
        "sla_hours": 48,
    }

    first = api.post(
        "/api/v1/workflow-steps/",
        {**base, "name": "Analyse", "order": 1, "step_kind": "CONSULTATIVE"},
        format="json",
        HTTP_X_TENANT_ID=str(tenant_a.id),
    )
    assert first.status_code == 201, first.json()

    second = api.post(
        "/api/v1/workflow-steps/",
        {**base, "name": "Décision", "order": 2, "step_kind": "DECISIONAL"},
        format="json",
        HTTP_X_TENANT_ID=str(tenant_a.id),
    )
    assert second.status_code == 201, second.json()

    with tenant_context(tenant_a.id):
        assert compute_decision_gaps(definition) == []


# --- Commande d'audit du parc ----------------------------------------------


def test_audit_command_flags_a_holed_circuit(tenant_a, capsys):
    with tenant_context(tenant_a.id):
        _seed_style_circuit(
            tenant_a, agency_kind=ApprovalStep.StepKind.CONSULTATIVE, code="AUDIT-KO"
        )

    with pytest.raises(SystemExit) as exit_info:
        call_command("audit_decision_coverage")

    assert exit_info.value.code == 1
    out = capsys.readouterr().out
    assert "AUDIT-KO" in out
    assert "9 999 999.99" in out


def test_audit_command_passes_on_a_healthy_circuit(tenant_a, capsys):
    with tenant_context(tenant_a.id):
        _seed_style_circuit(
            tenant_a, agency_kind=ApprovalStep.StepKind.DECISIONAL, code="AUDIT-OK"
        )

    call_command("audit_decision_coverage")

    assert "décisionnelle" in capsys.readouterr().out
