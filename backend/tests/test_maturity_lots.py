"""SoD dur, formalisation bloquante, reporting dashboard perm, IDOR smoke."""
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.services import (
    CHARGE_AFFAIRE_ROLE_NAME,
    CREDIT_COMMITTEE_FILIALE_ROLE_NAME,
    ensure_default_role_packs,
    get_or_create_tenant_role,
    validate_sod_role_assignment,
)
from apps.common.tenancy import tenant_context
from apps.credits.models import CreditApplication, CreditInstructionPolicy
from apps.credits.services import WorkflowError, _assert_disbursement_prerequisites
from apps.guarantees.formalization_services import (
    missing_formalizations_for_disbursement,
)
from apps.guarantees.models import Guarantee
from apps.tenants.services import bootstrap_tenant

pytestmark = pytest.mark.django_db


def test_sod_blocks_charge_affaire_and_committee(tenant_a):
    bootstrap_tenant(tenant_a)
    ensure_default_role_packs(tenant_a)
    with tenant_context(tenant_a.id):
        ca, _ = get_or_create_tenant_role(tenant_a, CHARGE_AFFAIRE_ROLE_NAME)
        com, _ = get_or_create_tenant_role(tenant_a, CREDIT_COMMITTEE_FILIALE_ROLE_NAME)
        with pytest.raises(ValueError, match="Séparation des tâches"):
            validate_sod_role_assignment([ca, com])


def test_formalization_gate_blocks_disbursement(
    tenant_a, product_a, client_a,
):
    with tenant_context(tenant_a.id):
        policy, _ = CreditInstructionPolicy.all_tenants.get_or_create(
            tenant=tenant_a,
            defaults={"require_formalization_before_disbursement": True},
        )
        policy.require_formalization_before_disbursement = True
        policy.require_surety_signed_contracts = False
        policy.save()

        app = CreditApplication.objects.create(
            tenant=tenant_a,
            client=client_a,
            product=product_a,
            amount_requested=Decimal("1000000"),
            duration_months=12,
            risk_level=1,
            reference="REF-FORM-GATE",
            status=CreditApplication.Status.APPROVED,
        )
        Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            application=app,
            guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
            description="Hypothèque non formalisée",
            expertise_value=Decimal("2000000"),
            current_value=Decimal("2000000"),
            status=Guarantee.Status.ACTIVE,
            reference="GAR-FORM-1",
        )
        missing = missing_formalizations_for_disbursement(app)
        assert "GAR-FORM-1" in missing

        with pytest.raises(WorkflowError, match="formalisation"):
            from unittest.mock import patch

            with patch(
                "apps.workflow.services.has_pending_conditions",
                return_value=False,
            ), patch(
                "apps.contracts.services.missing_required_contracts",
                return_value=[],
            ), patch(
                "apps.contracts.services.missing_surety_signed_contracts",
                return_value=[],
            ):
                # Contrôle préalable à la revue : la formalisation doit être
                # terminée avant que l'administrateur puisse valider sa revue.
                _assert_disbursement_prerequisites(app, check_review=False)


def test_dashboard_requires_view_dashboard_perm(tenant_a):
    user = User.objects.create_user(
        username="dash_noperm",
        password="FinFlow2026!",
        tenant=tenant_a,
    )
    api = APIClient()
    api.force_authenticate(user)
    res = api.get(
        "/api/v1/reporting/dashboard/",
        HTTP_X_TENANT_ID=str(tenant_a.id),
    )
    assert res.status_code == 403

    perm = Permission.objects.get(
        content_type__app_label="reporting",
        codename="view_dashboard",
    )
    user.user_permissions.add(perm)
    user = User.objects.get(pk=user.pk)
    api.force_authenticate(user)
    res = api.get(
        "/api/v1/reporting/dashboard/",
        HTTP_X_TENANT_ID=str(tenant_a.id),
    )
    assert res.status_code == 200


def test_group_consolidation_requires_view_dashboard_perm():
    user = User.objects.create_user(
        username="grp_nodash",
        password="FinFlow2026!",
        tenant=None,
        is_group_level=True,
    )
    api = APIClient()
    api.force_authenticate(user)
    res = api.get("/api/v1/reporting/group-consolidation/")
    assert res.status_code == 403

    perm = Permission.objects.get(
        content_type__app_label="reporting",
        codename="view_dashboard",
    )
    user.user_permissions.add(perm)
    user = User.objects.get(pk=user.pk)
    api.force_authenticate(user)
    res = api.get("/api/v1/reporting/group-consolidation/")
    assert res.status_code == 200


def test_client_idor_cross_tenant(tenant_a, tenant_b, client_a):
    """Token filiale A ne lit pas un client de filiale B."""
    user_a = User.objects.create_user(
        username="idor_a",
        password="FinFlow2026!",
        tenant=tenant_a,
        is_staff=True,
    )
    # Give view_client
    perm = Permission.objects.get(
        content_type__app_label="clients",
        codename="view_client",
    )
    user_a.user_permissions.add(perm)

    with tenant_context(tenant_b.id):
        from apps.clients.models import Client

        other = Client.objects.create(
            tenant=tenant_b,
            client_type=Client.ClientType.INDIVIDUAL,
            first_name="Autre",
            last_name="Filiale",
            phone="0700000000",
        )

    api = APIClient()
    api.force_authenticate(user_a)
    res = api.get(
        f"/api/v1/clients/{other.id}/",
        HTTP_X_TENANT_ID=str(tenant_a.id),
    )
    assert res.status_code in (404, 403)
