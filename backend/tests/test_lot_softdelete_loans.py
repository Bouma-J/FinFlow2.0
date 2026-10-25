"""Smoke — soft-delete GED, liste prêts, métriques Celery."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.common.tenancy import tenant_context
from apps.credits.models import CreditApplication, Loan
from apps.documents.models import Document, DocumentCategory

pytestmark = pytest.mark.django_db
User = get_user_model()


def _staff_with_perms(tenant, *, username, codenames):
    user = User.objects.create_user(
        username=username,
        password="FinFlow2026!",
        tenant=tenant,
        is_staff=True,
    )
    for app_label, codename in codenames:
        perm = Permission.objects.filter(
            content_type__app_label=app_label, codename=codename
        ).first()
        if perm:
            user.user_permissions.add(perm)
    return user


def test_document_soft_delete_and_restore(tenant_a):
    user = _staff_with_perms(
        tenant_a,
        username="ged_sd",
        codenames=[
            ("documents", "view_document"),
            ("documents", "add_document"),
            ("documents", "delete_document"),
            ("documents", "change_document"),
        ],
    )
    with tenant_context(tenant_a.id):
        cat = DocumentCategory.objects.create(
            tenant=tenant_a, code="SD", label="SoftDel"
        )
        doc = Document.objects.create(
            tenant=tenant_a,
            category=cat,
            name="piece.pdf",
            file=SimpleUploadedFile("piece.pdf", b"%PDF-1.4", content_type="application/pdf"),
            uploaded_by=user,
            size_bytes=8,
        )
        doc_id = doc.id

    api = APIClient()
    api.force_authenticate(user)
    headers = {"HTTP_X_TENANT_ID": str(tenant_a.id), "HTTP_HOST": "localhost"}

    del_resp = api.delete(f"/api/v1/documents/{doc_id}/", **headers)
    assert del_resp.status_code in (204, 200), del_resp.content

    with tenant_context(tenant_a.id):
        assert not Document.objects.filter(pk=doc_id).exists()
        soft = Document.including_deleted.get(pk=doc_id)
        assert soft.is_deleted is True
        assert soft.deleted_at is not None

    rest = api.post(f"/api/v1/documents/{doc_id}/restore/", {}, format="json", **headers)
    assert rest.status_code == 200, rest.content
    with tenant_context(tenant_a.id):
        alive = Document.objects.get(pk=doc_id)
        assert alive.is_deleted is False
        assert alive.deleted_at is None


def test_loans_list_lightweight(tenant_a, client_a, product_a):
    user = _staff_with_perms(
        tenant_a,
        username="loan_list",
        codenames=[("credits", "view_loan"), ("credits", "view_creditapplication")],
    )
    user.data_scope = "TENANT"
    user.save(update_fields=["data_scope"])
    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="LN-LIST-1",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("500000"),
            duration_months=12,
            status=CreditApplication.Status.DISBURSED,
        )
        Loan.objects.create(
            tenant=tenant_a,
            application=app,
            principal=Decimal("500000"),
            interest_rate=Decimal("12.0"),
            duration_months=12,
            disbursed_at=timezone.localdate(),
            first_due_date=timezone.localdate(),
            status=Loan.Status.ACTIVE,
        )

    api = APIClient()
    api.force_authenticate(user)
    res = api.get(
        "/api/v1/loans/",
        HTTP_X_TENANT_ID=str(tenant_a.id),
        HTTP_HOST="localhost",
    )
    assert res.status_code == 200, res.content
    body = res.json()
    results = body.get("results", body if isinstance(body, list) else [])
    assert len(results) >= 1
    row = results[0]
    assert "application_reference" in row
    assert "installments" not in row


def test_metrics_includes_celery_and_soft_delete(tenant_a):
    user = User.objects.create_user(
        username="metrics_ops",
        password="x",
        is_staff=True,
        is_group_level=True,
        tenant=tenant_a,
    )
    api = APIClient()
    api.force_authenticate(user)
    res = api.get("/api/v1/metrics/", HTTP_HOST="localhost")
    assert res.status_code == 200, res.content
    data = res.json()
    assert "celery" in data
    assert "documents_soft_deleted" in data
    assert isinstance(data["celery"], dict)
