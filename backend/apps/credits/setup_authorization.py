"""Autorisation nominative préalable à toute transmission d'un crédit au CBS."""

import hashlib
import json

from django.db import transaction
from django.utils import timezone

from apps.workflow.services import WorkflowError

from .governance import evidence_fingerprint, fingerprint
from .instruction_policy import get_instruction_policy
from .models import CreditApplication


ELIGIBLE_STATUSES = {"APPROVED", "CONTRACT_GENERATED", "DISBURSEMENT_PENDING"}
EXECUTION_PERMISSIONS = {
    "CREDIT_ADMIN": "credits.execute_setup_creditadmin",
    "OPERATIONS": "credits.execute_setup_operations",
}


def policy_fingerprint(application):
    policy = get_instruction_policy(application.tenant_id, application=application)
    values = {
        field.name: getattr(policy, field.name)
        for field in policy._meta.fields
        if field.name not in {"id", "tenant", "created_at", "updated_at"}
    }
    values["policy_revision"] = (
        "configuration_conservee" if application.configuration_snapshot
        else policy.updated_at.isoformat() if not policy._state.adding else "defaults"
    )
    values["configuration"] = getattr(policy, "configuration_fingerprint", "")
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def review_is_current(application):
    from apps.catalog.cbs_mapping import cbs_mapping_snapshot, resolve_application_cbs

    review = application.setup_review or {}
    return bool(
        isinstance(review, dict)
        and review.get("status") == "VALIDATED"
        and review.get("reviewed_by")
        and review.get("reviewed_at")
        and review.get("fingerprint") == fingerprint(application)
        and review.get("evidence_fingerprint") == evidence_fingerprint(application)
        and review.get("policy_fingerprint") == policy_fingerprint(application)
        and (not resolve_application_cbs(application)["requires_real"]
             or review.get("cbs_mapping") == cbs_mapping_snapshot(application))
    )


def authorization_failures(application):
    from apps.catalog.cbs_mapping import cbs_mapping_snapshot, resolve_application_cbs

    current_mapping = resolve_application_cbs(application)
    if (current_mapping["requires_real"] or not current_mapping["connector_id"]) and current_mapping["errors"]:
        return [e["message"] for e in current_mapping["errors"]]

    authorization = application.setup_authorization or {}
    if (
        not isinstance(authorization, dict)
        or authorization.get("status") != "AUTHORIZED"
    ):
        return [
            "L'administrateur crédit doit autoriser la mise en place après son contrôle final."
        ]
    if (
        not authorization.get("authorized_by")
        or not authorization.get("authorized_at")
        or not review_is_current(application)
        or authorization.get("reviewed_at")
        != application.setup_review.get("reviewed_at")
        or authorization.get("fingerprint") != fingerprint(application)
        or authorization.get("evidence_fingerprint")
        != evidence_fingerprint(application)
        or authorization.get("policy_fingerprint") != policy_fingerprint(application)
        or (resolve_application_cbs(application)["requires_real"]
            and authorization.get("cbs_mapping") != cbs_mapping_snapshot(application))
    ):
        return [
            "Le dossier, les preuves ou la politique ont changé : un nouveau contrôle et une nouvelle autorisation sont nécessaires."
        ]
    return []


@transaction.atomic
def request_setup_complements(application, user, comment):
    from apps.audit.events import log_workflow_event

    application = CreditApplication.all_tenants.select_for_update().get(
        pk=application.pk
    )
    assert_actor(application, user, "credits.review_setup_creditapplication")
    if application.status not in ELIGIBLE_STATUSES or not comment.strip():
        raise WorkflowError(
            "Un dossier approuvé et un motif de complément sont requis."
        )
    invalidate_authorization(application, comment.strip(), user=user)
    application.setup_review = {
        **(application.setup_review or {}),
        "status": "TO_COMPLETE",
        "complement_request": {
            "requested_by": str(user.pk),
            "requested_by_display": str(user),
            "requested_at": timezone.now().isoformat(),
            "comment": comment.strip(),
        },
    }
    application.save(
        update_fields=["setup_review", "setup_authorization", "updated_at"]
    )
    log_workflow_event(
        application, "SETUP_COMPLEMENTS_REQUESTED", user=user, detail=comment.strip()
    )
    return application


def assert_actor(application, user, permission):
    from apps.accounts.capabilities import CREDIT_ADMIN, OPERATIONS, user_has_capability

    required_capability = {
        "credits.review_setup_creditapplication": CREDIT_ADMIN,
        "credits.authorize_setup_creditapplication": CREDIT_ADMIN,
        "credits.execute_setup_creditadmin": CREDIT_ADMIN,
        "credits.execute_setup_operations": OPERATIONS,
    }.get(permission)
    if (
        not user
        or not user.is_authenticated
        or not user.is_active
        or not user.has_perm(permission)
        or (required_capability and not user_has_capability(user, required_capability))
    ):
        raise WorkflowError("Droit insuffisant pour cette action de mise en place.")
    if not user.is_group_level and not user.is_superuser:
        from apps.common.access import apply_data_scope

        if (
            user.tenant_id != application.tenant_id
            or not apply_data_scope(
                CreditApplication.all_tenants.filter(pk=application.pk), user
            ).exists()
        ):
            raise WorkflowError("Ce dossier est hors de votre périmètre.")


def assert_setup_authorization(application, *, user):
    failures = authorization_failures(application)
    if failures:
        raise WorkflowError(" ".join(failures))
    policy = get_instruction_policy(application.tenant_id, application=application)
    permission = EXECUTION_PERMISSIONS.get(policy.setup_execution_role)
    if permission is None:
        raise WorkflowError(
            "Le responsable de la transmission au CBS n'est pas configuré."
        )
    assert_actor(application, user, "credits.disburse_creditapplication")
    assert_actor(application, user, permission)
    if policy.require_setup_authorizer_separation and str(
        user.pk
    ) == application.setup_authorization.get("authorized_by"):
        raise WorkflowError(
            "L'auteur de l'autorisation ne peut pas transmettre lui-même le dossier au CBS."
        )


def invalidate_authorization(application, reason, *, user=None):
    if application.setup_authorization:
        application.setup_authorization = {
            **application.setup_authorization,
            "status": "REVOKED",
            "revoked_at": timezone.now().isoformat(),
            "revoked_by": str(user.pk) if user else None,
            "revocation_reason": reason,
        }


@transaction.atomic
def authorize_setup(application, user, comment):
    from .services import _assert_disbursement_prerequisites
    from apps.audit.events import log_workflow_event

    application = CreditApplication.all_tenants.select_for_update().get(
        pk=application.pk
    )
    assert_actor(application, user, "credits.authorize_setup_creditapplication")
    if application.status not in ELIGIBLE_STATUSES:
        raise WorkflowError(
            "Seul un crédit approuvé et non encore mis en place peut être autorisé."
        )
    if not comment.strip():
        raise WorkflowError("Précisez le motif et les références de l'autorisation.")
    _assert_disbursement_prerequisites(application)
    from apps.catalog.cbs_mapping import cbs_mapping_snapshot
    policy = get_instruction_policy(application.tenant_id, application=application)
    application.setup_authorization = {
        "status": "AUTHORIZED",
        "authorized_by": str(user.pk),
        "authorized_by_display": str(user),
        "authorized_at": timezone.now().isoformat(),
        "comment": comment.strip(),
        "reviewed_by": application.setup_review["reviewed_by"],
        "reviewed_at": application.setup_review["reviewed_at"],
        "execution_role": policy.setup_execution_role,
        "require_authorizer_separation": policy.require_setup_authorizer_separation,
        "fingerprint": fingerprint(application),
        "evidence_fingerprint": evidence_fingerprint(application),
        "policy_fingerprint": policy_fingerprint(application),
        "cbs_mapping": cbs_mapping_snapshot(application),
    }
    # L'autorisation constitue la demande nominative adressée au service exécutant.
    if application.status != "DISBURSEMENT_PENDING":
        application.disbursement_previous_status = application.status
        application.status = "DISBURSEMENT_PENDING"
        application.disbursement_requested_by = user
        application.disbursement_requested_at = timezone.now()
    application.save(
        update_fields=[
            "setup_authorization",
            "status",
            "disbursement_previous_status",
            "disbursement_requested_by",
            "disbursement_requested_at",
            "updated_at",
        ]
    )
    log_workflow_event(
        application,
        "SETUP_AUTHORIZED",
        user=user,
        detail=f"{comment.strip()} — Transmission : {policy.get_setup_execution_role_display()}.",
    )
    return application


@transaction.atomic
def revoke_setup(application, user, reason):
    from apps.audit.events import log_workflow_event

    application = CreditApplication.all_tenants.select_for_update().get(
        pk=application.pk
    )
    assert_actor(application, user, "credits.authorize_setup_creditapplication")
    if application.status not in ELIGIBLE_STATUSES:
        raise WorkflowError(
            "Une mise en place déjà réalisée ne peut pas être révoquée ici."
        )
    if not reason.strip():
        raise WorkflowError("Un motif de révocation est obligatoire.")
    invalidate_authorization(application, reason.strip(), user=user)
    application.save(update_fields=["setup_authorization", "updated_at"])
    log_workflow_event(
        application, "SETUP_AUTHORIZATION_REVOKED", user=user, detail=reason.strip()
    )
    return application


def setup_state(application, user):
    policy = get_instruction_policy(application.tenant_id, application=application)
    failures = authorization_failures(application)
    try:
        assert_setup_authorization(application, user=user)
        can_transmit = application.status in ELIGIBLE_STATUSES
        if (
            policy.require_setup_request
            and application.status != "DISBURSEMENT_PENDING"
        ):
            can_transmit = False
        if policy.require_setup_four_eyes and (
            not application.disbursement_requested_by_id
            or application.disbursement_requested_by_id == user.pk
        ):
            can_transmit = False
    except WorkflowError:
        can_transmit = False
    return {
        "authorization": application.setup_authorization,
        "authorization_valid": not failures,
        "authorization_failures": failures,
        "review_current": review_is_current(application),
        "execution_role": policy.setup_execution_role,
        "execution_role_display": policy.get_setup_execution_role_display(),
        "can_transmit": can_transmit,
    }
