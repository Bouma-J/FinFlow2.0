"""Diagnostic en lecture seule des habilitations et des circuits persistés."""

import json

from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError

from apps.accounts.models import TenantRole, User
from apps.accounts.services import (
    DEFAULT_ROLE_PACKS,
    DEFAULT_PACK_CODES,
    validate_sod_role_assignment,
)
from apps.common.tenancy import tenant_context
from apps.credits.models import AnalysisThreshold, CreditInstructionPolicy
from apps.corebanking.disbursement import disbursement_mode
from apps.corebanking.models import CoreBankingConnector
from apps.tenants.models import Tenant
from apps.workflow.models import WorkflowDefinition
from apps.workflow.services import compute_decision_gaps, is_credit_committee_step
from apps.accounts.capabilities import GROUP_CREDIT_COMMITTEE, group_has_capability


class Command(BaseCommand):
    help = "Audite les comptes, rôles, paramètres crédit et circuits sans les modifier."

    def handle(self, *args, **options):
        report = {"tenants": [], "issues": []}

        def issue(code, **details):
            report["issues"].append({"code": code, **details})

        for user in User.objects.filter(is_active=True).prefetch_related(
            "groups__tenant_role", "agencies"
        ):
            groups = list(user.groups.all())
            try:
                validate_sod_role_assignment(groups)
            except ValueError as exc:
                issue("INCOMPATIBLE_ROLES", user=user.username, detail=str(exc))
            if bool(user.tenant_id) == bool(user.is_group_level):
                issue("INVALID_ACCOUNT_SCOPE", user=user.username)
            try:
                user.clean()
            except ValidationError as exc:
                issue(
                    "INVALID_ACCOUNT_CONFIGURATION", user=user.username, detail=str(exc)
                )
            for group in groups:
                role = getattr(group, "tenant_role", None)
                if role and role.tenant_id != user.tenant_id:
                    issue("FOREIGN_ROLE", user=user.username, role=role.name)
            if any(
                agency.tenant_id != user.tenant_id for agency in user.agencies.all()
            ):
                issue("FOREIGN_AGENCY", user=user.username)

        for tenant in Tenant.objects.filter(is_active=True):
            with tenant_context(tenant.pk):
                roles = list(
                    TenantRole.objects.filter(tenant=tenant)
                    .select_related("group")
                    .prefetch_related("group__permissions__content_type")
                )
                pack_codes = {role.pack_code for role in roles}
                for name in DEFAULT_ROLE_PACKS:
                    if DEFAULT_PACK_CODES.get(name) not in pack_codes:
                        issue("MISSING_ROLE", tenant=tenant.code, role=name)
                for role in roles:
                    actual = {
                        (p.content_type.app_label, p.codename)
                        for p in role.group.permissions.all()
                    }
                    standard_name = next((name for name, code in DEFAULT_PACK_CODES.items() if code == role.pack_code), "")
                    missing = set(DEFAULT_ROLE_PACKS.get(standard_name, ())) - actual
                    if missing:
                        issue(
                            "ROLE_DIFFERS_FROM_DEFAULT",
                            tenant=tenant.code,
                            role=role.name,
                            missing=[
                                f"{app}.{codename}" for app, codename in sorted(missing)
                            ],
                        )
                policy = CreditInstructionPolicy.for_tenant(tenant.pk)
                configuration = {
                    field.name: getattr(policy, field.name)
                    for field in policy._meta.fields
                    if field.name not in {"id", "tenant", "created_at", "updated_at"}
                }
                definitions = list(
                    WorkflowDefinition.objects.filter(is_active=True).prefetch_related(
                        "steps__required_group__tenant_role"
                    )
                )
                for definition in definitions:
                    steps = list(definition.steps.all())
                    if not steps:
                        issue(
                            "EMPTY_ACTIVE_WORKFLOW",
                            tenant=tenant.code,
                            circuit=definition.code,
                        )
                    if compute_decision_gaps(definition, steps):
                        issue(
                            "DECISION_GAP", tenant=tenant.code, circuit=definition.code
                        )
                    for step in steps:
                        role = getattr(step.required_group, "tenant_role", None)
                        transverse = role is None and group_has_capability(step.required_group, GROUP_CREDIT_COMMITTEE)
                        if not transverse and (not role or role.tenant_id != tenant.pk):
                            issue(
                                "INVALID_STEP_ROLE",
                                tenant=tenant.code,
                                circuit=definition.code,
                                step=step.name,
                            )
                        members = User.objects.filter(
                            is_active=True, groups=step.required_group
                        )
                        members = (
                            members.filter(is_group_level=True)
                            if transverse
                            else members.filter(tenant=tenant)
                        )
                        needed = (
                            step.committee_quorum
                            if is_credit_committee_step(step)
                            else 1
                        )
                        if members.distinct().count() < needed:
                            issue(
                                "INSUFFICIENT_STEP_MEMBERS",
                                tenant=tenant.code,
                                circuit=definition.code,
                                step=step.name,
                                required=needed,
                            )
                thresholds = AnalysisThreshold.for_tenant(tenant.pk)
                connectors = list(CoreBankingConnector.objects.filter(is_active=True))
                if len(connectors) != 1:
                    issue(
                        "ACTIVE_CBS_COUNT", tenant=tenant.code, active=len(connectors)
                    )
                report["tenants"].append(
                    {
                        "code": tenant.code,
                        "roles": len(roles),
                        "active_workflows": len(definitions),
                        "policy_persisted": not policy._state.adding,
                        "policy": configuration,
                        "analysis_thresholds": {
                            field.name: getattr(thresholds, field.name)
                            for field in thresholds._meta.fields
                            if field.name
                            not in {"id", "tenant", "created_at", "updated_at"}
                        },
                        "cbs": [
                            {
                                "name": connector.name,
                                "mode": disbursement_mode(connector),
                                "simulated": bool(
                                    (connector.mapping_rules or {}).get(
                                        "force_simulate"
                                    )
                                ),
                            }
                            for connector in connectors
                        ],
                    }
                )
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, default=str))
