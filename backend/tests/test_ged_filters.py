from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client
from apps.common.tenancy import tenant_context
from apps.credits.models import CreditApplication
from apps.documents.models import Document, DocumentCategory

pytestmark = pytest.mark.django_db


def _auth(user, tenant):
    api = APIClient()
    api.force_authenticate(user)
    return api, {"HTTP_X_TENANT_ID": str(tenant.id), "HTTP_HOST": "localhost"}


def _viewer(tenant, username="ged_viewer"):
    user = User.objects.create_user(
        username=username,
        password="x",
        tenant=tenant,
        is_staff=True,
    )
    perm = Permission.objects.filter(
        content_type__app_label="documents", codename="view_document"
    ).first()
    if perm:
        user.user_permissions.add(perm)
    return user


def _pdf(name="piece.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4", content_type="application/pdf")


def _doc(tenant, category, name, related=None, **kwargs):
    ct = None
    oid = None
    if related is not None:
        ct = ContentType.objects.get_for_model(related)
        oid = related.id
    return Document.objects.create(
        tenant=tenant,
        category=category,
        name=name,
        file=_pdf(name),
        content_type=ct,
        object_id=oid,
        **kwargs,
    )


def test_ged_filters_related_kind_client_expiry(
    tenant_a, product_a, client_a
):
    user = _viewer(tenant_a)
    today = timezone.now().date()
    with tenant_context(tenant_a.id):
        other_client = Client.objects.create(
            tenant=tenant_a,
            reference="CLIB",
            client_type=Client.ClientType.INDIVIDUAL,
            first_name="Autre",
            last_name="Client",
            kyc_status=Client.KycStatus.VALIDATED,
        )
        cat = DocumentCategory.objects.create(
            tenant=tenant_a, code="GEDF", label="Filtre"
        )
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="DOS-GED",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("1000000"),
            duration_months=12,
            created_by=user,
        )
        on_client = _doc(
            tenant_a, cat, "kyc-client.pdf", related=client_a, uploaded_by=user
        )
        on_app = _doc(
            tenant_a,
            cat,
            "piece-dossier.pdf",
            related=app,
            uploaded_by=user,
            expiry_date=today + timedelta(days=10),
        )
        expired = _doc(
            tenant_a,
            cat,
            "cni-expiree.pdf",
            related=client_a,
            uploaded_by=user,
            expiry_date=today - timedelta(days=2),
        )
        other = _doc(
            tenant_a,
            cat,
            "autre-client.pdf",
            related=other_client,
            uploaded_by=user,
        )
        _doc(tenant_a, cat, "sans-lien.pdf", uploaded_by=user)

    api, headers = _auth(user, tenant_a)

    by_credit = api.get(
        "/api/v1/documents/?related_kind=CREDIT", **headers
    )
    assert by_credit.status_code == 200, by_credit.content
    names = {row["name"] for row in by_credit.json()["results"]}
    assert names == {"piece-dossier.pdf"}
    row = by_credit.json()["results"][0]
    assert row["related_kind"] == "CREDIT"
    assert row["related_path"] == f"/dossiers/{app.id}"

    by_client_kind = api.get(
        "/api/v1/documents/?related_kind=CLIENT", **headers
    )
    assert by_client_kind.status_code == 200
    assert {r["name"] for r in by_client_kind.json()["results"]} == {
        "kyc-client.pdf",
        "cni-expiree.pdf",
        "autre-client.pdf",
    }

    by_other = api.get("/api/v1/documents/?related_kind=OTHER", **headers)
    assert {r["name"] for r in by_other.json()["results"]} == {"sans-lien.pdf"}

    scoped = api.get(f"/api/v1/documents/?client={client_a.id}", **headers)
    assert scoped.status_code == 200, scoped.content
    scoped_names = {r["name"] for r in scoped.json()["results"]}
    assert scoped_names == {
        "kyc-client.pdf",
        "piece-dossier.pdf",
        "cni-expiree.pdf",
    }
    assert "autre-client.pdf" not in scoped_names

    expiring = api.get("/api/v1/documents/?expiry=expiring", **headers)
    assert {r["name"] for r in expiring.json()["results"]} == {
        "piece-dossier.pdf"
    }

    expired_res = api.get("/api/v1/documents/?expiry=expired", **headers)
    assert {r["name"] for r in expired_res.json()["results"]} == {
        "cni-expiree.pdf"
    }

    by_uploader = api.get(
        f"/api/v1/documents/?uploaded_by={user.id}", **headers
    )
    assert by_uploader.status_code == 200
    assert by_uploader.json()["count"] >= 5

    # Formalisation / recouvrement n'ont pas de client_id direct.
    safe = api.get(
        f"/api/v1/documents/?client={client_a.id}&related_kind=FORMALIZATION",
        **headers,
    )
    assert safe.status_code == 200, safe.content
    assert safe.json()["results"] == []

    assert on_client.id and on_app.id and expired.id and other.id


def test_ged_dation_asset_is_dation_kind_and_client_scoped(
    tenant_a, product_a, client_a
):
    from apps.guarantees.models import DationAsset, DationRequest

    user = _viewer(tenant_a, username="ged_dation")
    with tenant_context(tenant_a.id):
        cat = DocumentCategory.objects.create(
            tenant=tenant_a, code="GEDDAT", label="Dation GED"
        )
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="DOS-GED-DAT",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("1000000"),
            duration_months=12,
            created_by=user,
        )
        dation = DationRequest.objects.create(
            tenant=tenant_a,
            client=client_a,
            application=app,
            reference="DAT-GED",
        )
        asset = DationAsset.objects.create(
            tenant=tenant_a,
            dation=dation,
            source=DationAsset.Source.ADDITIONAL,
            description="Terrain test GED",
        )
        _doc(tenant_a, cat, "acte-dation.pdf", related=dation, uploaded_by=user)
        _doc(tenant_a, cat, "photo-bien.pdf", related=asset, uploaded_by=user)
        _doc(tenant_a, cat, "hors-dation.pdf", uploaded_by=user)

    api, headers = _auth(user, tenant_a)
    by_dation = api.get("/api/v1/documents/?related_kind=DATION", **headers)
    assert by_dation.status_code == 200, by_dation.content
    names = {row["name"] for row in by_dation.json()["results"]}
    assert names == {"acte-dation.pdf", "photo-bien.pdf"}
    asset_row = next(
        row for row in by_dation.json()["results"] if row["name"] == "photo-bien.pdf"
    )
    assert asset_row["related_kind"] == "DATION"
    assert asset_row["related_path"] == f"/dations/{dation.id}"

    scoped = api.get(f"/api/v1/documents/?client={client_a.id}", **headers)
    scoped_names = {r["name"] for r in scoped.json()["results"]}
    assert "photo-bien.pdf" in scoped_names
    assert "acte-dation.pdf" in scoped_names

    by_other = api.get("/api/v1/documents/?related_kind=OTHER", **headers)
    assert "photo-bien.pdf" not in {r["name"] for r in by_other.json()["results"]}
