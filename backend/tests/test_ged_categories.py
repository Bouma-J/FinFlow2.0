"""Seed catégories GED au bootstrap filiale."""
import pytest

from apps.common.tenancy import tenant_context
from apps.documents.category_seed import (
    ensure_all_process_document_categories,
    ensure_core_document_categories,
)
from apps.documents.models import DocumentCategory

pytestmark = pytest.mark.django_db


def test_ensure_core_document_categories(tenant_a):
    with tenant_context(tenant_a.id):
        created = ensure_core_document_categories(tenant_a)
        assert created > 0
        assert DocumentCategory.objects.filter(code="CNI").exists()
        assert DocumentCategory.objects.filter(code="CREDIT_PIECE").exists()
        # Idempotent
        assert ensure_core_document_categories(tenant_a) == 0


def test_ensure_all_process_document_categories(tenant_a):
    with tenant_context(tenant_a.id):
        ensure_all_process_document_categories(tenant_a)
        codes = set(
            DocumentCategory.objects.values_list("code", flat=True)
        )
        assert "ML_DEMANDE" in codes
        assert "DAT_ACTE" in codes
        assert "FORM_ACTE_SIGNE" in codes
        assert "LIT_JUDGMENT" in codes
        assert "CNI" in codes
