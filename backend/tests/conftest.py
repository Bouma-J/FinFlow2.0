from decimal import Decimal

import pytest

from apps.catalog.models import CreditProduct, ProductCategory
from apps.clients.models import Client
from apps.common.tenancy import tenant_context
from apps.tenants.models import Tenant


@pytest.fixture
def tenant_a(db):
    return Tenant.objects.create(code="A", name="Filiale A", country="CI", currency="XOF")


@pytest.fixture
def tenant_b(db):
    return Tenant.objects.create(code="B", name="Filiale B", country="SN", currency="XOF")


@pytest.fixture
def product_a(tenant_a):
    with tenant_context(tenant_a.id):
        cat = ProductCategory.objects.create(tenant=tenant_a, code="C1", label="Cat 1")
        return CreditProduct.objects.create(
            tenant=tenant_a, code="P1", label="Produit 1", category=cat,
            amount_min=Decimal("1000"), amount_max=Decimal("10000000"),
            interest_rate=Decimal("10"),
        )


@pytest.fixture
def client_a(tenant_a):
    with tenant_context(tenant_a.id):
        return Client.objects.create(
            tenant=tenant_a, reference="CLIA",
            client_type=Client.ClientType.INDIVIDUAL,
            first_name="Test", last_name="Client",
            kyc_status=Client.KycStatus.VALIDATED,
        )
