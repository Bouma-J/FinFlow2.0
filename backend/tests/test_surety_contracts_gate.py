"""Contrats de cautionnement signés — readiness + blocage décaissement."""
from decimal import Decimal

import pytest
from django.core.files.base import ContentFile

from apps.common.tenancy import tenant_context
from apps.contracts.models import GeneratedContract
from apps.contracts.services import missing_surety_signed_contracts
from apps.credits.instruction_policy import build_readiness
from apps.credits.models import CreditApplication, CreditInstructionPolicy
from apps.credits.services import _assert_disbursement_prerequisites
from apps.sureties.models import Surety, SuretyEngagement
from apps.workflow.services import WorkflowError

pytestmark = pytest.mark.django_db


def _app(tenant, client_obj, product, *, ref="CR-SURETY-GATE"):
    return CreditApplication.objects.create(
        tenant=tenant,
        client=client_obj,
        product=product,
        reference=ref,
        amount_requested=Decimal("500000"),
        duration_months=12,
        risk_level=1,
        status=CreditApplication.Status.APPROVED,
    )


def _engagement(tenant, app, *, amount="1000000"):
    surety = Surety.objects.create(
        tenant=tenant,
        surety_type=Surety.SuretyType.PHYSICAL,
        first_name="Awa",
        last_name="Diallo",
        commitment_ceiling=Decimal("10000000"),
    )
    return SuretyEngagement.objects.create(
        tenant=tenant,
        surety=surety,
        application=app,
        amount=Decimal(amount),
        engagement_type=SuretyEngagement.EngagementType.SOLIDAIRE,
        status=SuretyEngagement.Status.ACTIVE,
    )


def _contract(app, engagement, *, status=GeneratedContract.Status.GENERATED):
    gc = GeneratedContract(
        tenant_id=app.tenant_id,
        application=app,
        surety_engagement=engagement,
        template_name="Cautionnement",
        category="SURETY",
        status=status,
    )
    gc.file.save("caution.docx", ContentFile(b"PK fake docx"), save=False)
    if status == GeneratedContract.Status.SIGNED:
        gc.signed_file.save("caution-signee.pdf", ContentFile(b"%PDF signed"), save=False)
    gc.save()
    return gc


def test_missing_surety_when_no_contract(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a)
        _engagement(tenant_a, app)
        missing = missing_surety_signed_contracts(app)
        assert len(missing) == 1
        assert "non généré" in missing[0]


def test_missing_surety_when_unsigned(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a, ref="CR-SURETY-UNSIGNED")
        eng = _engagement(tenant_a, app)
        _contract(app, eng, status=GeneratedContract.Status.GENERATED)
        missing = missing_surety_signed_contracts(app)
        assert len(missing) == 1
        assert "non signé" in missing[0]


def test_no_missing_when_signed(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a, ref="CR-SURETY-SIGNED")
        eng = _engagement(tenant_a, app)
        _contract(app, eng, status=GeneratedContract.Status.SIGNED)
        assert missing_surety_signed_contracts(app) == []


def test_readiness_includes_surety_contracts_check(tenant_a, client_a, product_a):
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a, ref="CR-SURETY-READY")
        _engagement(tenant_a, app)
        result = build_readiness(app)
        check = next(c for c in result["checks"] if c["key"] == "surety_contracts")
        assert check["ok"] is False
        assert check["blocking"] is False
        assert "Avant mise en place" in check["message"]
        assert result["policy"]["require_surety_signed_contracts"] is True


def test_disbursement_blocked_without_signed_surety(
    tenant_a, client_a, product_a, monkeypatch
):
    with tenant_context(tenant_a.id):
        CreditInstructionPolicy.objects.create(
            tenant=tenant_a,
            require_surety_signed_contracts=True,
        )
        app = _app(tenant_a, client_a, product_a, ref="CR-SURETY-BLOCK")
        eng = _engagement(tenant_a, app)
        _contract(app, eng, status=GeneratedContract.Status.GENERATED)
        monkeypatch.setattr(
            "apps.contracts.services.missing_required_contracts",
            lambda _a: [],
        )
        monkeypatch.setattr(
            "apps.workflow.services.has_pending_conditions",
            lambda _a: False,
        )
        with pytest.raises(WorkflowError) as exc:
            _assert_disbursement_prerequisites(app, check_review=False)
        assert "cautionnement" in str(exc.value).lower()


def test_disbursement_allowed_when_policy_off(
    tenant_a, client_a, product_a, monkeypatch
):
    with tenant_context(tenant_a.id):
        CreditInstructionPolicy.objects.create(
            tenant=tenant_a,
            require_surety_signed_contracts=False,
            require_surety_contracts=False,
        )
        app = _app(tenant_a, client_a, product_a, ref="CR-SURETY-OFF")
        _engagement(tenant_a, app)
        monkeypatch.setattr(
            "apps.contracts.services.missing_required_contracts",
            lambda _a: [],
        )
        monkeypatch.setattr(
            "apps.workflow.services.has_pending_conditions",
            lambda _a: False,
        )
        _assert_disbursement_prerequisites(app, check_review=False)


def test_policy_endpoint_exposes_surety_flag(tenant_a):
    from rest_framework.test import APIClient

    from apps.accounts.models import User

    admin = User.objects.create_user(
        username="surety_pol_admin",
        password="FinFlow2026!",
        is_staff=True,
        is_group_level=True,
    )
    client = APIClient()
    client.force_authenticate(admin)
    res = client.get(
        "/api/v1/credit-instruction-policy/current/",
        HTTP_X_TENANT_ID=str(tenant_a.id),
    )
    assert res.status_code == 200
    assert res.json()["require_surety_signed_contracts"] is True


def test_assert_surety_generation_requires_engagement(tenant_a):
    from apps.contracts.models import ContractCategory, ContractTemplate
    from apps.contracts.services import assert_surety_generation
    from rest_framework.exceptions import ValidationError

    with tenant_context(tenant_a.id):
        template = ContractTemplate(
            tenant=tenant_a,
            name="Cautionnement",
            category=ContractCategory.SURETY,
        )
        template.file.save("caution.docx", ContentFile(b"PK fake docx"), save=False)
        template.save()
        with pytest.raises(ValidationError) as exc:
            assert_surety_generation(template, None)
        assert "surety_engagement" in exc.value.detail


def test_generate_surety_without_engagement_is_400(
    tenant_a, client_a, product_a,
):
    from apps.accounts.models import User
    from apps.contracts.models import ContractCategory, ContractTemplate
    from rest_framework.test import APIClient

    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a, ref="CR-SURETY-GEN")
        template = ContractTemplate(
            tenant=tenant_a,
            name="Cautionnement dossier",
            category=ContractCategory.SURETY,
        )
        template.file.save("caution.docx", ContentFile(b"PK fake docx"), save=False)
        template.save()

    admin = User.objects.create_user(
        username="surety_gen_admin",
        password="FinFlow2026!",
        is_staff=True,
        is_superuser=True,
        is_group_level=True,
    )
    api = APIClient()
    api.force_authenticate(admin)
    api.credentials(HTTP_X_TENANT_ID=str(tenant_a.id))
    res = api.post(
        "/api/v1/generated-contracts/generate/",
        {"application": str(app.id), "template": str(template.id)},
        format="json",
    )
    assert res.status_code == 400
    errors = res.json().get("errors", res.json())
    assert "surety_engagement" in errors


def test_required_templates_exclude_surety(tenant_a, client_a, product_a):
    from apps.contracts.models import ContractCategory, ContractTemplate
    from apps.contracts.services import required_templates_for

    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a, ref="CR-SURETY-REQ")
        template = ContractTemplate(
            tenant=tenant_a,
            name="Caution obligatoire",
            category=ContractCategory.SURETY,
            is_required=True,
            is_active=True,
        )
        template.file.save("caution.docx", ContentFile(b"PK fake docx"), save=False)
        template.save()
        assert required_templates_for(app) == []
