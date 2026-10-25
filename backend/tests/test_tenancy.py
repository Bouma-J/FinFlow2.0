"""Tests d'isolation multi-tenants."""
import pytest

from apps.catalog.models import CreditProduct, ProductCategory
from apps.common.tenancy import tenant_context

pytestmark = pytest.mark.django_db


def test_isolation_between_tenants(tenant_a, tenant_b, product_a):
    # Depuis le contexte de la filiale A : on voit le produit de A
    with tenant_context(tenant_a.id):
        assert CreditProduct.objects.count() == 1

    # Depuis le contexte de la filiale B : on ne voit rien de A
    with tenant_context(tenant_b.id):
        assert CreditProduct.objects.count() == 0

    # Sans contexte : par sécurité, aucun résultat
    assert CreditProduct.objects.count() == 0

    # Le manager d'échappement voit tout
    assert CreditProduct.all_tenants.count() == 1


def test_tenant_auto_assigned_on_save(tenant_a):
    with tenant_context(tenant_a.id):
        cat = ProductCategory.objects.create(code="X", label="X")
        # tenant renseigné automatiquement depuis le contexte
        assert cat.tenant_id == tenant_a.id
