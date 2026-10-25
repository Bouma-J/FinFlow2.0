from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import DataScope, User
from apps.clients.models import Client
from apps.common.tenancy import tenant_context
from apps.credits.models import CreditApplication, Loan

pytestmark = pytest.mark.django_db


def _auth(user, tenant):
    api = APIClient()
    api.force_authenticate(user)
    return api, {"HTTP_X_TENANT_ID": str(tenant.id), "HTTP_HOST": "localhost"}


def test_officers_endpoint_without_view_user(tenant_a):
    user = User.objects.create_user(
        username="officer_list",
        password="x",
        tenant=tenant_a,
        first_name="Awa",
        last_name="Diallo",
    )
    api, headers = _auth(user, tenant_a)
    res = api.get("/api/v1/users/officers/", **headers)
    assert res.status_code == 200, res.content
    names = [r["display_name"] for r in res.json()["results"]]
    assert any("Diallo" in n or "officer_list" in n for n in names)


def test_credit_and_loan_filter_by_gestionnaire(
    tenant_a, product_a, client_a
):
    manager = User.objects.create_user(
        username="mgr_a",
        password="x",
        tenant=tenant_a,
        is_staff=True,
        data_scope=DataScope.TENANT,
    )
    other = User.objects.create_user(
        username="mgr_b",
        password="x",
        tenant=tenant_a,
        is_staff=True,
        data_scope=DataScope.TENANT,
    )
    for user in (manager, other):
        for codename in ("view_creditapplication", "view_loan"):
            perm = Permission.objects.filter(codename=codename).first()
            if perm:
                user.user_permissions.add(perm)
    with tenant_context(tenant_a.id):
        mine = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="DOS-MGR",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("1000000"),
            duration_months=12,
            created_by=manager,
            submitted_by=manager,
        )
        CreditApplication.objects.create(
            tenant=tenant_a,
            reference="DOS-OTH",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("2000000"),
            duration_months=12,
            created_by=other,
        )
        Loan.objects.create(
            tenant=tenant_a,
            application=mine,
            principal=Decimal("1000000"),
            interest_rate=Decimal("12"),
            duration_months=12,
            disbursed_at=timezone.localdate(),
            first_due_date=timezone.localdate(),
            status=Loan.Status.ACTIVE,
        )

    api, headers = _auth(manager, tenant_a)
    credits = api.get(
        "/api/v1/credit-applications/",
        {"gestionnaire": str(manager.id)},
        **headers,
    )
    assert credits.status_code == 200, credits.content
    refs = [r["reference"] for r in credits.json()["results"]]
    assert "DOS-MGR" in refs
    assert "DOS-OTH" not in refs

    loans = api.get(
        "/api/v1/loans/",
        {"gestionnaire": str(manager.id)},
        **headers,
    )
    assert loans.status_code == 200, loans.content
    assert loans.json()["count"] >= 1
    for row in loans.json()["results"]:
        assert row["application"] == str(mine.id)


def test_dashboard_filters_agency_and_gestionnaire(
    tenant_a, product_a, client_a
):
    from apps.tenants.models import Agency

    manager = User.objects.create_user(
        username="dash_mgr",
        password="x",
        tenant=tenant_a,
        first_name="Awa",
        last_name="Kone",
        is_staff=True,
        data_scope=DataScope.TENANT,
    )
    other = User.objects.create_user(
        username="dash_oth",
        password="x",
        tenant=tenant_a,
        first_name="Ibrahim",
        last_name="Traore",
        is_staff=True,
        data_scope=DataScope.TENANT,
    )
    perm = Permission.objects.get(
        content_type__app_label="reporting",
        codename="view_dashboard",
    )
    manager.user_permissions.add(perm)

    with tenant_context(tenant_a.id):
        ag_centre = Agency.objects.create(
            tenant=tenant_a, code="AG-C", name="Agence Centre"
        )
        ag_nord = Agency.objects.create(
            tenant=tenant_a, code="AG-N", name="Agence Nord"
        )
        CreditApplication.objects.create(
            tenant=tenant_a,
            reference="DOS-DASH-MGR",
            client=client_a,
            product=product_a,
            agency=ag_centre,
            amount_requested=Decimal("1000000"),
            duration_months=12,
            created_by=manager,
            submitted_by=manager,
        )
        CreditApplication.objects.create(
            tenant=tenant_a,
            reference="DOS-DASH-OTH",
            client=client_a,
            product=product_a,
            agency=ag_nord,
            amount_requested=Decimal("2000000"),
            duration_months=12,
            created_by=other,
        )

    api, headers = _auth(manager, tenant_a)
    by_mgr = api.get(
        "/api/v1/reporting/dashboard/",
        {"live": "1", "gestionnaire": str(manager.id)},
        **headers,
    )
    assert by_mgr.status_code == 200, by_mgr.content
    body = by_mgr.json()
    assert body["credits"]["summary"]["total"] == 1
    refs = [r["reference"] for r in body["credits"]["recent"]]
    assert refs == ["DOS-DASH-MGR"]
    assert body["credits"]["recent"][0]["owner"] == "Awa Kone"
    assert body["filters_applied"]["gestionnaire"] == str(manager.id)

    by_ag = api.get(
        "/api/v1/reporting/dashboard/",
        {"live": "1", "agency": str(ag_nord.id)},
        **headers,
    )
    assert by_ag.status_code == 200, by_ag.content
    nord = by_ag.json()
    assert nord["credits"]["summary"]["total"] == 1
    assert nord["credits"]["recent"][0]["reference"] == "DOS-DASH-OTH"
    assert "AG-N" in nord["credits"]["recent"][0]["agency"]


def test_portfolio_lists_filter_by_client(tenant_a, product_a, client_a):
    from datetime import date, timedelta

    from apps.collections.services import refresh_loan_overdue
    from apps.guarantees.models import Guarantee, GuaranteeFormalizationRequest, GuaranteeReleaseRequest
    from apps.sureties.models import Surety, SuretyEngagement

    admin = User.objects.create_user(
        username="port_admin",
        password="x",
        tenant=tenant_a,
        is_staff=True,
        is_superuser=True,
        data_scope=DataScope.TENANT,
    )
    with tenant_context(tenant_a.id):
        other = Client.objects.create(
            tenant=tenant_a,
            reference="CLIB",
            client_type=Client.ClientType.INDIVIDUAL,
            first_name="Autre",
            last_name="Client",
            kyc_status=Client.KycStatus.VALIDATED,
        )
        mine = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="DOS-CLI-A",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("1000000"),
            duration_months=12,
            status=CreditApplication.Status.APPROVED,
        )
        CreditApplication.objects.create(
            tenant=tenant_a,
            reference="DOS-CLI-B",
            client=other,
            product=product_a,
            amount_requested=Decimal("2000000"),
            duration_months=12,
        )
        loan = Loan.objects.create(
            tenant=tenant_a,
            application=mine,
            principal=Decimal("1000000"),
            interest_rate=Decimal("12"),
            duration_months=12,
            disbursed_at=date.today() - timedelta(days=40),
            first_due_date=date.today() - timedelta(days=30),
            status=Loan.Status.ACTIVE,
        )
        case = refresh_loan_overdue(
            loan,
            cbs_status={
                "settled": False,
                "days_overdue": 30,
                "overdue_amount": Decimal("1000000"),
            },
        )
        surety = Surety.objects.create(
            tenant=tenant_a,
            surety_type=Surety.SuretyType.PHYSICAL,
            first_name="Jean",
            last_name="Caution",
        )
        engagement = SuretyEngagement.objects.create(
            tenant=tenant_a,
            surety=surety,
            application=mine,
            amount=Decimal("200000"),
        )
        guarantee = Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            application=mine,
            guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
            description="Terrain",
            current_value=Decimal("400000"),
            status=Guarantee.Status.ACTIVE,
            reference="GAR-PORT",
        )
        release = GuaranteeReleaseRequest.objects.create(
            tenant=tenant_a,
            guarantee=guarantee,
            application=mine,
        )
        formalization = GuaranteeFormalizationRequest.objects.create(
            tenant=tenant_a,
            guarantee=guarantee,
            application=mine,
        )

    api, headers = _auth(admin, tenant_a)

    credits = api.get(
        "/api/v1/credit-applications/",
        {"client": str(client_a.id)},
        **headers,
    )
    assert credits.status_code == 200, credits.content
    refs = [r["reference"] for r in credits.json()["results"]]
    assert "DOS-CLI-A" in refs
    assert "DOS-CLI-B" not in refs
    row = next(r for r in credits.json()["results"] if r["reference"] == "DOS-CLI-A")
    assert row["collection_case_id"] == str(case.id)
    assert row["collection_stage_display"]

    cases = api.get(
        "/api/v1/collection-cases/",
        {"client": str(client_a.id)},
        **headers,
    )
    assert cases.status_code == 200, cases.content
    assert str(case.id) in [r["id"] for r in cases.json()["results"]]

    other_cases = api.get(
        "/api/v1/collection-cases/",
        {"client": str(other.id)},
        **headers,
    )
    assert other_cases.status_code == 200
    assert other_cases.json()["count"] == 0

    engagements = api.get(
        "/api/v1/surety-engagements/",
        {"client": str(client_a.id)},
        **headers,
    )
    assert engagements.status_code == 200, engagements.content
    assert str(engagement.id) in [r["id"] for r in engagements.json()["results"]]

    releases = api.get(
        "/api/v1/guarantee-releases/",
        {"client": str(client_a.id)},
        **headers,
    )
    assert releases.status_code == 200, releases.content
    assert str(release.id) in [r["id"] for r in releases.json()["results"]]

    forms = api.get(
        "/api/v1/guarantee-formalizations/",
        {"client": str(client_a.id)},
        **headers,
    )
    assert forms.status_code == 200, forms.content
    assert str(formalization.id) in [r["id"] for r in forms.json()["results"]]


def test_my_dossiers_is_paginated(tenant_a):
    user = User.objects.create_user(
        username="val_user",
        password="x",
        tenant=tenant_a,
        is_staff=True,
        is_superuser=True,
    )
    api, headers = _auth(user, tenant_a)
    res = api.get("/api/v1/approval-tasks/my_dossiers/", **headers)
    assert res.status_code == 200, res.content
    body = res.json()
    assert "count" in body
    assert "results" in body
    assert "actionable_count" in body
