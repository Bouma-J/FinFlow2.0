"""Cohérence des packs RBAC avec les écrans (dashboard, formalisation, GED)."""

import pytest
from django.contrib.auth.models import Permission

from apps.accounts.services import (
    ANALYSTE_CREDIT_RISQUE_ROLE_NAME,
    ASSISTANT_AUDIT_ROLE_NAME,
    ASSISTANT_CONTROLE_INTERNE_ROLE_NAME,
    ASSISTANT_JURIDIQUE_ROLE_NAME,
    ASSISTANT_OPERATIONS_ROLE_NAME,
    CHARGE_AFFAIRE_ROLE_NAME,
    CHEF_AGENCE_ROLE_NAME,
    COMPTABLE_ROLE_NAME,
    CREDIT_COMMITTEE_FILIALE_ROLE_NAME,
    CREDIT_COMMITTEE_GROUP_ROLE_NAME,
    LECTEUR_ROLE_NAME,
    RESP_AUDIT_ROLE_NAME,
    RESP_CONTROLE_INTERNE_ROLE_NAME,
    ensure_default_role_packs,
    get_or_create_tenant_role,
)

pytestmark = pytest.mark.django_db


def _codes(group):
    return set(
        f"{p.content_type.app_label}.{p.codename}"
        for p in group.permissions.all()
    )


def test_consultation_and_finance_can_open_dashboard(tenant_a):
    ensure_default_role_packs(tenant_a)
    for name in (
        LECTEUR_ROLE_NAME,
        COMPTABLE_ROLE_NAME,
        ASSISTANT_CONTROLE_INTERNE_ROLE_NAME,
        RESP_AUDIT_ROLE_NAME,
        ASSISTANT_AUDIT_ROLE_NAME,
    ):
        group, _ = get_or_create_tenant_role(tenant_a, name)
        assert "reporting.view_dashboard" in _codes(group), name


def test_assistant_juridique_can_pilot_formalization_and_release(tenant_a):
    ensure_default_role_packs(tenant_a)
    group, _ = get_or_create_tenant_role(tenant_a, ASSISTANT_JURIDIQUE_ROLE_NAME)
    codes = _codes(group)
    assert "guarantees.initiate_guaranteeformalizationrequest" in codes
    assert "guarantees.initiate_guaranteereleaserequest" in codes
    assert "guarantees.view_guaranteeformalizationrequest" in codes


def test_audit_and_controle_can_open_ged(tenant_a):
    ensure_default_role_packs(tenant_a)
    for name in (
        ASSISTANT_AUDIT_ROLE_NAME,
        RESP_AUDIT_ROLE_NAME,
        ASSISTANT_CONTROLE_INTERNE_ROLE_NAME,
    ):
        group, _ = get_or_create_tenant_role(tenant_a, name)
        assert "documents.view_document" in _codes(group), name


def test_view_dashboard_perm_exists():
    assert Permission.objects.filter(
        content_type__app_label="reporting",
        codename="view_dashboard",
    ).exists()


def test_charge_affaire_and_chef_agence_consult_form_and_initiate_release(tenant_a):
    ensure_default_role_packs(tenant_a)
    for name in (CHARGE_AFFAIRE_ROLE_NAME, CHEF_AGENCE_ROLE_NAME):
        codes = _codes(get_or_create_tenant_role(tenant_a, name)[0])
        assert "guarantees.view_guaranteeformalizationrequest" in codes, name
        assert "guarantees.initiate_guaranteeformalizationrequest" not in codes, name
        assert "guarantees.initiate_guaranteereleaserequest" in codes, name


def test_chef_agence_decides_restructure_charge_affaire_proposes(tenant_a):
    ensure_default_role_packs(tenant_a)
    ca = _codes(get_or_create_tenant_role(tenant_a, CHARGE_AFFAIRE_ROLE_NAME)[0])
    chef = _codes(get_or_create_tenant_role(tenant_a, CHEF_AGENCE_ROLE_NAME)[0])
    assert "collections.add_loanrestructure" in ca
    assert "collections.change_loanrestructure" not in ca
    assert "collections.change_loanrestructure" in chef
    assert "collections.change_writeoff" in chef


def test_analyste_and_committee_can_view_collections(tenant_a):
    ensure_default_role_packs(tenant_a)
    for name in (
        ANALYSTE_CREDIT_RISQUE_ROLE_NAME,
        CREDIT_COMMITTEE_FILIALE_ROLE_NAME,
        CREDIT_COMMITTEE_GROUP_ROLE_NAME,
    ):
        codes = _codes(get_or_create_tenant_role(tenant_a, name)[0])
        assert "collections.view_collectioncase" in codes, name
        assert "documents.add_document" in codes, name


def test_comptable_can_view_guarantees(tenant_a):
    ensure_default_role_packs(tenant_a)
    codes = _codes(get_or_create_tenant_role(tenant_a, COMPTABLE_ROLE_NAME)[0])
    assert "guarantees.view_guarantee" in codes
    assert "guarantees.add_guarantee" not in codes


_WRITE_BLOCKED = (
    "credits.add_creditapplication",
    "credits.change_creditapplication",
    "guarantees.add_guarantee",
    "guarantees.initiate_dationrequest",
    "collections.add_repayment",
)


def test_audit_consults_all_business_ops_read_only(tenant_a):
    ensure_default_role_packs(tenant_a)
    for name in (RESP_AUDIT_ROLE_NAME, ASSISTANT_AUDIT_ROLE_NAME):
        codes = _codes(get_or_create_tenant_role(tenant_a, name)[0])
        assert "credits.view_creditapplication" in codes, name
        assert "collections.view_collectioncase" in codes, name
        assert "guarantees.view_dationrequest" in codes, name
        assert "guarantees.view_guaranteereleaserequest" in codes, name
        assert "guarantees.view_guaranteeformalizationrequest" in codes, name
        assert "reporting.view_dashboard" in codes, name
        assert "credits.add_fieldvisit" not in codes, name
        for blocked in _WRITE_BLOCKED:
            assert blocked not in codes, f"{name} {blocked}"


def test_controle_permanent_reads_all_and_can_add_field_visit(tenant_a):
    ensure_default_role_packs(tenant_a)
    for name in (
        RESP_CONTROLE_INTERNE_ROLE_NAME,
        ASSISTANT_CONTROLE_INTERNE_ROLE_NAME,
    ):
        codes = _codes(get_or_create_tenant_role(tenant_a, name)[0])
        assert "credits.view_creditapplication" in codes, name
        assert "collections.view_collectioncase" in codes, name
        assert "guarantees.view_guarantee" in codes, name
        assert "credits.add_fieldvisit" in codes, name
        assert "credits.add_financialanalysis" not in codes, name
        for blocked in _WRITE_BLOCKED:
            assert blocked not in codes, f"{name} {blocked}"


def test_assistant_operations_consults_dation_and_release_only(tenant_a):
    ensure_default_role_packs(tenant_a)
    codes = _codes(get_or_create_tenant_role(tenant_a, ASSISTANT_OPERATIONS_ROLE_NAME)[0])
    assert "guarantees.view_dationrequest" in codes
    assert "guarantees.view_guaranteereleaserequest" in codes
    assert "guarantees.initiate_dationrequest" not in codes
    assert "guarantees.initiate_guaranteereleaserequest" not in codes


def test_controle_can_add_visit_without_owning_the_dossier(
    tenant_a, product_a, client_a,
):
    from decimal import Decimal

    from django.contrib.auth import get_user_model

    from apps.common.tenancy import tenant_context
    from apps.credits.access import can_add_field_visit, can_contribute
    from apps.credits.models import CreditApplication

    ensure_default_role_packs(tenant_a)
    User = get_user_model()
    owner = User.objects.create_user(
        username="ca_owner",
        password="x",
        tenant=tenant_a,
    )
    group, _ = get_or_create_tenant_role(tenant_a, RESP_CONTROLE_INTERNE_ROLE_NAME)
    ctrl = User.objects.create_user(
        username="ctrl_visit",
        password="x",
        tenant=tenant_a,
    )
    ctrl.groups.add(group)

    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            reference="DOS-CTRL-1",
            client=client_a,
            product=product_a,
            amount_requested=Decimal("1000000"),
            duration_months=12,
            status=CreditApplication.Status.IN_APPROVAL,
            created_by=owner,
        )

    assert not can_contribute(app, ctrl)
    assert can_add_field_visit(app, ctrl)


def test_ensure_role_pack_keeps_manual_permissions(tenant_a):
    extra = Permission.objects.get(
        content_type__app_label="credits",
        codename="add_creditapplication",
    )
    ensure_default_role_packs(tenant_a)
    group, _ = get_or_create_tenant_role(tenant_a, LECTEUR_ROLE_NAME)
    assert extra not in group.permissions.all()
    group.permissions.add(extra)
    ensure_default_role_packs(tenant_a)
    group, _ = get_or_create_tenant_role(tenant_a, LECTEUR_ROLE_NAME)
    assert extra in group.permissions.all()
    assert "reporting.view_dashboard" in _codes(group)
