"""Hub après-vente — agrégation ML / dation / formalisation / recouvrement."""
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from django.contrib.auth.models import Permission
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.collections.models import CollectionCase
from apps.common.tenancy import tenant_context
from apps.credits.models import CreditApplication, Loan
from apps.guarantees.models import Guarantee, GuaranteeReleaseRequest
from apps.reporting.services import build_after_sales_hub

pytestmark = pytest.mark.django_db


def test_build_after_sales_hub_counts(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        g = Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
            description="Hub test",
            expertise_value=Decimal("1000000"),
            current_value=Decimal("1000000"),
            status=Guarantee.Status.ACTIVE,
            reference="GAR-HUB-1",
        )
        GuaranteeReleaseRequest.objects.create(
            tenant=tenant_a,
            guarantee=g,
            reference="ML-HUB-1",
            status=GuaranteeReleaseRequest.Status.IN_APPROVAL,
        )
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            client=client_a,
            product=product_a,
            amount_requested=Decimal("5000"),
            duration_months=6,
            risk_level=1,
            reference="REF-HUB-COL",
            status=CreditApplication.Status.APPROVED,
        )
        loan = Loan.objects.create(
            tenant=tenant_a,
            application=app,
            principal=Decimal("5000"),
            interest_rate=Decimal("12"),
            duration_months=6,
            disbursed_at=date.today() - timedelta(days=40),
            first_due_date=date.today() - timedelta(days=30),
            status=Loan.Status.ACTIVE,
        )
        CollectionCase.objects.create(
            tenant=tenant_a,
            loan=loan,
            days_overdue=30,
            overdue_amount=Decimal("5000"),
            stage=CollectionCase.Stage.AMICABLE,
            next_action_date=date.today(),
            next_action_type="CALL",
        )

        data = build_after_sales_hub(tenant_id=tenant_a.id)
        assert data["modules"]["main_levee"]["open"] >= 1
        assert data["modules"]["main_levee"]["in_approval"] >= 1
        assert data["modules"]["collection"]["open"] >= 1
        assert data["modules"]["collection"]["followups_due"] >= 1
        assert any(r["kind"] == "MAIN_LEVEE" for r in data["recent"])


def test_build_after_sales_hub_filters_by_user_perms(tenant_a, product_a, client_a):
    """Un utilisateur sans droits collections ne voit pas le module recouvrement."""
    with tenant_context(tenant_a.id):
        g = Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
            description="Hub RBAC",
            expertise_value=Decimal("1000000"),
            current_value=Decimal("1000000"),
            status=Guarantee.Status.ACTIVE,
            reference="GAR-HUB-RBAC",
        )
        GuaranteeReleaseRequest.objects.create(
            tenant=tenant_a,
            guarantee=g,
            reference="ML-HUB-RBAC",
            status=GuaranteeReleaseRequest.Status.DRAFT,
        )
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            client=client_a,
            product=product_a,
            amount_requested=Decimal("5000"),
            duration_months=6,
            risk_level=1,
            reference="REF-HUB-RBAC",
            status=CreditApplication.Status.APPROVED,
        )
        loan = Loan.objects.create(
            tenant=tenant_a,
            application=app,
            principal=Decimal("5000"),
            interest_rate=Decimal("12"),
            duration_months=6,
            disbursed_at=date.today() - timedelta(days=40),
            first_due_date=date.today() - timedelta(days=30),
            status=Loan.Status.ACTIVE,
        )
        CollectionCase.objects.create(
            tenant=tenant_a,
            loan=loan,
            days_overdue=10,
            overdue_amount=Decimal("1000"),
            stage=CollectionCase.Stage.AMICABLE,
        )

    user = MagicMock()
    user.is_superuser = False
    user.has_perm = lambda code: code in (
        "guarantees.view_guaranteereleaserequest",
    )

    data = build_after_sales_hub(tenant_id=tenant_a.id, user=user)
    assert "main_levee" in data["modules"]
    assert "collection" not in data["modules"]
    assert all(r["kind"] == "MAIN_LEVEE" for r in data["recent"])


def test_after_sales_hub_api(tenant_a):
    admin = User.objects.create_user(
        username="hub_admin",
        password="FinFlow2026!",
        is_staff=True,
        is_group_level=True,
        is_superuser=True,
    )
    api = APIClient()
    api.force_authenticate(admin)
    res = api.get(
        "/api/v1/reporting/after-sales-hub/",
        {"tenant": str(tenant_a.id)},
        HTTP_X_TENANT_ID=str(tenant_a.id),
    )
    assert res.status_code == 200
    body = res.json()
    assert "modules" in body
    assert "recent" in body
    assert "main_levee" in body["modules"]


def test_after_sales_hub_api_forbidden_without_perms(tenant_a):
    user = User.objects.create_user(
        username="hub_noperm",
        password="FinFlow2026!",
        tenant=tenant_a,
    )
    api = APIClient()
    api.force_authenticate(user)
    res = api.get(
        "/api/v1/reporting/after-sales-hub/",
        HTTP_X_TENANT_ID=str(tenant_a.id),
    )
    assert res.status_code == 403


def test_notification_settings_require_view_perm(tenant_a):
    user = User.objects.create_user(
        username="notif_noperm",
        password="FinFlow2026!",
        tenant=tenant_a,
    )
    api = APIClient()
    api.force_authenticate(user)
    res = api.get(
        "/api/v1/notification-settings/current/",
        HTTP_X_TENANT_ID=str(tenant_a.id),
    )
    assert res.status_code == 403

    perm = Permission.objects.get(
        content_type__app_label="notifications",
        codename="view_tenantnotificationsettings",
    )
    user.user_permissions.add(perm)
    user = User.objects.get(pk=user.pk)
    api.force_authenticate(user)
    res = api.get(
        "/api/v1/notification-settings/current/",
        HTTP_X_TENANT_ID=str(tenant_a.id),
    )
    assert res.status_code == 200
    res = api.patch(
        "/api/v1/notification-settings/current/",
        {"enabled": False},
        format="json",
        HTTP_X_TENANT_ID=str(tenant_a.id),
    )
    assert res.status_code == 403
