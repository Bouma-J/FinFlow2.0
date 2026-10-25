"""P3 — docs API gated, suppression fichier GED."""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import NoReverseMatch, reverse
from rest_framework.test import APIClient

import pytest

from apps.accounts.models import User
from apps.common.tenancy import tenant_context
from apps.documents.models import Document, DocumentCategory

pytestmark = pytest.mark.django_db


def test_api_docs_routes_absent_when_disabled():
    """ENABLE_API_DOCS=False (settings test) → pas de reverse swagger/schema."""
    with pytest.raises(NoReverseMatch):
        reverse("swagger-ui")
    with pytest.raises(NoReverseMatch):
        reverse("schema")
    api = APIClient()
    assert api.get("/api/docs/", HTTP_HOST="localhost").status_code == 404
    assert api.get("/api/schema/", HTTP_HOST="localhost").status_code == 404


@override_settings(ALLOWED_HOSTS=["*"])
def test_document_destroy_deletes_storage_file(tenant_a, tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.STORAGE_BACKEND = "local"
    user = User.objects.create_superuser(
        username="p3_ged",
        password="FinFlow2026!",
        email="p3@example.com",
        tenant=tenant_a,
    )
    with tenant_context(tenant_a.id):
        cat = DocumentCategory.objects.create(
            tenant=tenant_a, code="P3", label="P3"
        )
        doc = Document(
            tenant=tenant_a,
            category=cat,
            name="to-delete.pdf",
            uploaded_by=user,
        )
        doc.file.save(
            "to-delete.pdf",
            SimpleUploadedFile("to-delete.pdf", b"%PDF-1.4\nok"),
            save=True,
        )
        key = doc.file.name
        assert doc.file.storage.exists(key)
        doc_id = doc.id

    api = APIClient()
    api.force_authenticate(user)
    res = api.delete(
        f"/api/v1/documents/{doc_id}/",
        HTTP_X_TENANT_ID=str(tenant_a.id),
        HTTP_HOST="localhost",
    )
    assert res.status_code in (204, 200), res.content
    # Soft-delete : l'enregistrement reste (is_deleted) et le fichier est
    # conservé jusqu'à la purge de rétention.
    soft = Document.including_deleted.filter(pk=doc_id).first()
    assert soft is not None and soft.is_deleted is True
    assert not Document.all_tenants.filter(pk=doc_id).exists()
    from django.core.files.storage import default_storage

    assert default_storage.exists(key)
