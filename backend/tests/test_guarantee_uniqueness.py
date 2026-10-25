"""Unicité des hypothèques (titre) et gages véhicules (châssis)."""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import DataScope, User
from apps.common.tenancy import tenant_context
from apps.credits.models import CreditApplication
from apps.guarantees.models import DocumentType, Guarantee, PledgeCategory

pytestmark = pytest.mark.django_db


def _auth(user, tenant):
    api = APIClient()
    api.force_authenticate(user)
    return api, {"HTTP_X_TENANT_ID": str(tenant.id), "HTTP_HOST": "localhost"}


def _admin(tenant):
    return User.objects.create_user(
        username="gar_admin",
        password="x",
        tenant=tenant,
        is_staff=True,
        is_superuser=True,
        data_scope=DataScope.TENANT,
    )


def _app(tenant, client, product, ref="DOS-GAR-1"):
    return CreditApplication.objects.create(
        tenant=tenant,
        reference=ref,
        client=client,
        product=product,
        amount_requested=Decimal("1000000"),
        duration_months=12,
        status=CreditApplication.Status.DRAFT,
    )


def _mortgage_payload(client_id, application_id, *, number="TF-001"):
    return {
        "guarantee_type": "MORTGAGE",
        "client": str(client_id),
        "application": str(application_id),
        "document_type": DocumentType.LAND_TITLE,
        "document_number": number,
        "document_issue_date": "2018-04-12",
        "document_validity_date": "2030-04-12",
        "expertise_value": "25000000",
        "expertise_date": "2026-01-15",
        "expert_name": "Kouassi Expert",
        "expertise_firm": "Cabinet Horizon",
        "expertise_reference": "EXP-2026-14",
        "description": "Villa Cocody",
    }


def test_duplicate_land_title_is_blocked(tenant_a, client_a, product_a):
    admin = _admin(tenant_a)
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a)
        Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            application=app,
            guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
            document_type=DocumentType.LAND_TITLE,
            document_number="tf-001",
            status=Guarantee.Status.ACTIVE,
            reference="GAR-TF",
        )
    api, headers = _auth(admin, tenant_a)
    other_app_id = None
    with tenant_context(tenant_a.id):
        other = _app(tenant_a, client_a, product_a, ref="DOS-GAR-2")
        other_app_id = other.id
    res = api.post(
        "/api/v1/guarantees/",
        _mortgage_payload(client_a.id, other_app_id, number="TF-001"),
        format="json",
        **headers,
    )
    assert res.status_code == 400, res.content
    errors = res.json().get("errors", res.json())
    taken = errors.get("already_taken")
    assert taken
    payload = taken[0] if isinstance(taken, list) else taken
    assert payload["code"] == "GUARANTEE_ALREADY_TAKEN"
    assert "déjà pris" in payload["message"].lower()

    forced = api.post(
        "/api/v1/guarantees/",
        {
            **_mortgage_payload(client_a.id, other_app_id, number="TF-001"),
            "accept_existing": True,
        },
        format="json",
        **headers,
    )
    assert forced.status_code == 201, forced.content


def test_released_title_can_be_taken_again(tenant_a, client_a, product_a):
    admin = _admin(tenant_a)
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a)
        Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            application=app,
            guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
            document_type=DocumentType.LAND_TITLE,
            document_number="TF-REL",
            status=Guarantee.Status.RELEASED,
            reference="GAR-OLD",
        )
        next_app = _app(tenant_a, client_a, product_a, ref="DOS-GAR-3")
    api, headers = _auth(admin, tenant_a)
    res = api.post(
        "/api/v1/guarantees/",
        _mortgage_payload(client_a.id, next_app.id, number="TF-REL"),
        format="json",
        **headers,
    )
    assert res.status_code == 201, res.content


def test_duplicate_chassis_is_blocked(tenant_a, client_a, product_a):
    admin = _admin(tenant_a)
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a, ref="DOS-VEH-1")
        Guarantee.objects.create(
            tenant=tenant_a,
            client=client_a,
            application=app,
            guarantee_type=Guarantee.GuaranteeType.PLEDGE,
            pledge_category=PledgeCategory.VEHICLE,
            chassis_number="VF1-ABC 123",
            status=Guarantee.Status.ACTIVE,
            reference="GAR-VEH-1",
        )
        other = _app(tenant_a, client_a, product_a, ref="DOS-VEH-2")
    api, headers = _auth(admin, tenant_a)
    res = api.post(
        "/api/v1/guarantees/",
        {
            "guarantee_type": "PLEDGE",
            "pledge_category": "VEHICLE",
            "client": str(client_a.id),
            "application": str(other.id),
            "chassis_number": "VF1ABC123",
            "document_type": DocumentType.REGISTRATION_CARD,
            "document_number": "CG-99",
            "document_issue_date": "2022-06-01",
            "expertise_value": "8000000",
            "expertise_date": "2026-02-01",
            "expertise_firm": "Auto Expert",
        },
        format="json",
        **headers,
    )
    assert res.status_code == 400, res.content
    errors = res.json().get("errors", res.json())
    assert "already_taken" in errors

    forced = api.post(
        "/api/v1/guarantees/",
        {
            "guarantee_type": "PLEDGE",
            "pledge_category": "VEHICLE",
            "client": str(client_a.id),
            "application": str(other.id),
            "chassis_number": "VF1ABC123",
            "document_type": DocumentType.REGISTRATION_CARD,
            "document_number": "CG-99",
            "document_issue_date": "2022-06-01",
            "expertise_value": "8000000",
            "expertise_date": "2026-02-01",
            "expertise_firm": "Auto Expert",
            "accept_existing": True,
        },
        format="json",
        **headers,
    )
    assert forced.status_code == 201, forced.content


def test_mortgage_requires_title_on_create(tenant_a, client_a, product_a):
    admin = _admin(tenant_a)
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a, ref="DOS-REQ")
    api, headers = _auth(admin, tenant_a)
    res = api.post(
        "/api/v1/guarantees/",
        {
            "guarantee_type": "MORTGAGE",
            "client": str(client_a.id),
            "application": str(app.id),
            "description": "Sans titre",
        },
        format="json",
        **headers,
    )
    assert res.status_code == 400, res.content
    errors = res.json().get("errors", res.json())
    assert "document_type" in errors
    assert "document_number" in errors


def test_jewelry_pledge_skips_title_uniqueness(tenant_a, client_a, product_a):
    admin = _admin(tenant_a)
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a, ref="DOS-JOY")
    api, headers = _auth(admin, tenant_a)
    res = api.post(
        "/api/v1/guarantees/",
        {
            "guarantee_type": "PLEDGE",
            "pledge_category": "VALUABLE",
            "client": str(client_a.id),
            "application": str(app.id),
            "expertise_value": "500000",
            "description": "Collier",
        },
        format="json",
        **headers,
    )
    assert res.status_code == 201, res.content
