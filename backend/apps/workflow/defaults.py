"""Circuits workflow par défaut (main levée, dation, formalisation)."""
from __future__ import annotations


def ensure_process_workflows(tenant) -> dict:
    """
    Crée les circuits MAIN_LEVEE / DATION / FORMALISATION manquants (idempotent).

    Étape unique de validation assignée au Chef d'agence.
    """
    from apps.accounts.services import (
        CHEF_AGENCE_ROLE_NAME,
        get_or_create_tenant_role,
    )
    from apps.common.tenancy import tenant_context
    from apps.workflow.models import ApprovalStep, WorkflowDefinition

    created = {"main_levee": 0, "dation": 0, "formalisation": 0}

    with tenant_context(tenant.id):
        group, _ = get_or_create_tenant_role(tenant, CHEF_AGENCE_ROLE_NAME)

        specs = (
            (
                "CIRCUIT-MAIN-LEVEE",
                "Circuit main levée",
                WorkflowDefinition.TargetType.MAIN_LEVEE,
                "Validation main levée",
                "main_levee",
            ),
            (
                "CIRCUIT-DATION",
                "Circuit dation en paiement",
                WorkflowDefinition.TargetType.DATION,
                "Validation dation",
                "dation",
            ),
            (
                "CIRCUIT-FORMALISATION",
                "Circuit formalisation de garantie",
                WorkflowDefinition.TargetType.FORMALISATION,
                "Validation formalisation",
                "formalisation",
            ),
        )
        for code, name, target, step_name, key in specs:
            definition, was_created = WorkflowDefinition.objects.get_or_create(
                tenant=tenant,
                code=code,
                version=1,
                defaults={
                    "name": name,
                    "target_type": target,
                    "is_active": True,
                },
            )
            if was_created:
                created[key] = 1
                ApprovalStep.objects.create(
                    tenant=tenant,
                    definition=definition,
                    name=step_name,
                    order=1,
                    required_group=group,
                    sla_hours=48,
                    step_kind=ApprovalStep.StepKind.DECISIONAL,
                )
            else:
                changed = False
                if definition.target_type != target:
                    definition.target_type = target
                    changed = True
                if not definition.is_active:
                    definition.is_active = True
                    changed = True
                if changed:
                    definition.save(
                        update_fields=["target_type", "is_active", "updated_at"]
                    )
                if not definition.steps.filter(order=1).exists():
                    ApprovalStep.objects.create(
                        tenant=tenant,
                        definition=definition,
                        name=step_name,
                        order=1,
                        required_group=group,
                        sla_hours=48,
                        step_kind=ApprovalStep.StepKind.DECISIONAL,
                    )

    return created
