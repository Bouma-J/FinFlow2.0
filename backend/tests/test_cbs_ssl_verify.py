"""Unit test verify_ssl on RestAdapter."""
from apps.corebanking.models import CoreBankingConnector
from apps.corebanking.services import RestAdapter


def test_ssl_verify_defaults_true(tenant_a):
    c = CoreBankingConnector(
        tenant=tenant_a,
        name="t",
        protocol=CoreBankingConnector.Protocol.REST,
        base_url="https://example.com",
        mapping_rules={},
    )
    assert RestAdapter(c)._ssl_verify() is True


def test_ssl_verify_can_be_disabled(tenant_a):
    c = CoreBankingConnector(
        tenant=tenant_a,
        name="t",
        protocol=CoreBankingConnector.Protocol.REST,
        base_url="https://example.com",
        mapping_rules={"verify_ssl": False},
    )
    assert RestAdapter(c)._ssl_verify() is False
