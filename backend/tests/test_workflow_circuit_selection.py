"""Sélection de circuit crédit par montant, produit, ou les deux."""
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group

from apps.accounts.models import User
from apps.catalog.models import CreditProduct, ProductCategory
from apps.common.tenancy import tenant_context
from apps.credits.models import CreditApplication, FinancialAnalysis
from apps.credits.services import submit_application
from apps.workflow.models import ApprovalStep, WorkflowDefinition, WorkflowInstance
from apps.workflow.services import select_definition

pytestmark = pytest.mark.django_db


def _decisional_step(tenant, definition, role):
    return ApprovalStep.objects.create(
        tenant=tenant,
        definition=definition,
        name="Décision",
        order=1,
        required_group=role,
        step_kind=ApprovalStep.StepKind.DECISIONAL,
        sla_hours=24,
    )


def _ready_app(tenant, client, product, *, reference, amount, submitter):
    application = CreditApplication.objects.create(
        tenant=tenant,
        reference=reference,
        client=client,
        product=product,
        amount_requested=amount,
        duration_months=12,
        risk_level=1,
        submitted_by=submitter,
    )
    FinancialAnalysis.objects.create(
        tenant=tenant,
        application=application,
        is_reference=True,
        recommendation=FinancialAnalysis.Recommendation.FAVORABLE,
        salary_income=Decimal("300000"),
        client_type=getattr(client, "client_type", "") or "INDIVIDUAL",
    )
    return application


def test_select_by_amount_tranche(tenant_a, product_a):
    role = Group.objects.create(name="Val montant")
    with tenant_context(tenant_a.id):
        low = WorkflowDefinition.objects.create(
            tenant=tenant_a,
            code="WF-LOW",
            name="Petite tranche",
            version=1,
            is_active=True,
            min_amount=Decimal("0"),
            max_amount=Decimal("100000"),
        )
        high = WorkflowDefinition.objects.create(
            tenant=tenant_a,
            code="WF-HIGH",
            name="Grande tranche",
            version=1,
            is_active=True,
            min_amount=Decimal("100000.01"),
            max_amount=Decimal("1000000"),
        )
        _decisional_step(tenant_a, low, role)
        _decisional_step(tenant_a, high, role)

        chosen = select_definition(
            tenant_a.id,
            WorkflowDefinition.TargetType.CREDIT,
            Decimal("50000"),
            product=product_a,
        )
        assert chosen is not None
        assert chosen.id == low.id

        chosen = select_definition(
            tenant_a.id,
            WorkflowDefinition.TargetType.CREDIT,
            Decimal("250000"),
            product=product_a,
        )
        assert chosen is not None
        assert chosen.id == high.id


def test_select_by_product_and_specificity(tenant_a, product_a, client_a):
    role = Group.objects.create(name="Val produit")
    with tenant_context(tenant_a.id):
        cat_other, _ = ProductCategory.objects.get_or_create(
            tenant=tenant_a,
            code="OTHER-CAT",
            defaults={"label": "Autre famille"},
        )
        other_product = CreditProduct.objects.create(
            tenant=tenant_a,
            code="OTHER-PROD",
            label="Autre produit",
            category=cat_other,
            amount_min=Decimal("1000"),
            amount_max=Decimal("5000000"),
        )

        generic = WorkflowDefinition.objects.create(
            tenant=tenant_a,
            code="WF-GEN",
            name="Générique",
            version=1,
            is_active=True,
        )
        by_product = WorkflowDefinition.objects.create(
            tenant=tenant_a,
            code="WF-PROD",
            name="Produit ciblé",
            version=1,
            is_active=True,
            product=product_a,
        )
        by_amount = WorkflowDefinition.objects.create(
            tenant=tenant_a,
            code="WF-AMT",
            name="Montant seul",
            version=1,
            is_active=True,
            min_amount=Decimal("0"),
            max_amount=Decimal("2000000"),
        )
        both = WorkflowDefinition.objects.create(
            tenant=tenant_a,
            code="WF-BOTH",
            name="Produit + montant",
            version=1,
            is_active=True,
            product=product_a,
            min_amount=Decimal("0"),
            max_amount=Decimal("2000000"),
        )
        for d in (generic, by_product, by_amount, both):
            _decisional_step(tenant_a, d, role)

        # Les 4 matchent : le plus spécifique (montant + produit) gagne.
        chosen = select_definition(
            tenant_a.id,
            WorkflowDefinition.TargetType.CREDIT,
            Decimal("500000"),
            product=product_a,
        )
        assert chosen is not None
        assert chosen.id == both.id

        # Produit hors cible : tombe sur montant ou générique (montant plus spécifique).
        chosen = select_definition(
            tenant_a.id,
            WorkflowDefinition.TargetType.CREDIT,
            Decimal("500000"),
            product=other_product,
        )
        assert chosen is not None
        assert chosen.id == by_amount.id


def test_select_by_product_category(tenant_a, product_a):
    role = Group.objects.create(name="Val famille")
    with tenant_context(tenant_a.id):
        category = product_a.category
        by_cat = WorkflowDefinition.objects.create(
            tenant=tenant_a,
            code="WF-CAT",
            name="Famille",
            version=1,
            is_active=True,
            product_category=category,
        )
        _decisional_step(tenant_a, by_cat, role)

        chosen = select_definition(
            tenant_a.id,
            WorkflowDefinition.TargetType.CREDIT,
            Decimal("100000"),
            product=product_a,
        )
        assert chosen is not None
        assert chosen.id == by_cat.id


def test_submit_picks_matching_circuit(tenant_a, product_a, client_a):
    role = Group.objects.create(name="Val submit")
    submitter = User.objects.create(username="sub_sel", tenant=tenant_a)
    with tenant_context(tenant_a.id):
        low = WorkflowDefinition.objects.create(
            tenant=tenant_a,
            code="WF-SUB-LOW",
            name="Bas",
            version=1,
            is_active=True,
            min_amount=Decimal("0"),
            max_amount=Decimal("100000"),
        )
        high = WorkflowDefinition.objects.create(
            tenant=tenant_a,
            code="WF-SUB-HIGH",
            name="Haut",
            version=1,
            is_active=True,
            min_amount=Decimal("100000.01"),
            max_amount=None,
            product=product_a,
        )
        _decisional_step(tenant_a, low, role)
        _decisional_step(tenant_a, high, role)

        app = _ready_app(
            tenant_a,
            client_a,
            product_a,
            reference="SEL-1",
            amount=Decimal("750000"),
            submitter=submitter,
        )
        submit_application(app, submitter)
        instance = WorkflowInstance.objects.get(object_id=app.id)
        assert instance.definition_id == high.id
