"""Droits par tranche, dialogue consultatif, import / paramétrage admin."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.models import DataScope
from apps.accounts.services import (
    CHARGE_AFFAIRE_ROLE_NAME,
    CHEF_AGENCE_ROLE_NAME,
    FILIALE_ADMIN_ROLE_NAME,
    RESP_EXPLOITATION_ROLE_NAME,
    RESP_JURIDIQUE_ROLE_NAME,
    RESP_RECOUVREMENT_ROLE_NAME,
    ensure_default_role_packs,
    get_or_create_tenant_role,
)
from apps.collections.services import ensure_default_tranches, refresh_loan_overdue
from apps.common.tenancy import tenant_context
from apps.credits.models import CreditApplication, Installment, Loan
from apps.tenants.models import Agency

User = get_user_model()

pytestmark = pytest.mark.django_db


def _role_user(tenant, username, role_name, *, agency=None, data_scope=DataScope.TENANT):
    ensure_default_role_packs(tenant)
    group, _ = get_or_create_tenant_role(tenant, role_name)
    user = User.objects.create_user(
        username=username,
        password="test-pass-123",
        email=f"{username}@example.com",
        tenant=tenant,
        agency=agency,
        data_scope=data_scope,
    )
    user.groups.add(group)
    user = User.objects.get(pk=user.pk)
    return user


def _api(user, tenant):
    client = APIClient()
    client.force_authenticate(user=user)
    client.credentials(HTTP_X_TENANT_ID=str(tenant.id))
    return client


def _case(tenant, product, client_obj, *, days, ref, submitted_by=None, agency=None):
    app = CreditApplication.objects.create(
        tenant=tenant,
        client=client_obj,
        product=product,
        agency=agency,
        amount_requested=Decimal("20000"),
        duration_months=6,
        risk_level=1,
        reference=ref,
        status=CreditApplication.Status.APPROVED,
        submitted_by=submitted_by,
    )
    loan = Loan.objects.create(
        tenant=tenant,
        application=app,
        principal=Decimal("20000"),
        interest_rate=Decimal("12"),
        duration_months=6,
        disbursed_at=date.today() - timedelta(days=days + 10),
        first_due_date=date.today() - timedelta(days=days),
        status=Loan.Status.ACTIVE,
    )
    Installment.objects.create(
        tenant=tenant,
        loan=loan,
        number=1,
        due_date=date.today() - timedelta(days=days),
        principal_due=Decimal("20000"),
        interest_due=Decimal("0"),
        total_due=Decimal("20000"),
        status=Installment.Status.OVERDUE,
    )
    case = refresh_loan_overdue(
        loan,
        cbs_status={
            "settled": False,
            "days_overdue": days,
            "overdue_amount": Decimal("20000"),
        },
    )
    return case


def test_charge_affaire_mine_and_dashboard_ignore_others(
    tenant_a, product_a, client_a
):
    with tenant_context(tenant_a.id):
        ensure_default_tranches(tenant_a)
        ca = _role_user(tenant_a, "ca_mine", CHARGE_AFFAIRE_ROLE_NAME)
        other = _role_user(tenant_a, "ca_other_mine", CHARGE_AFFAIRE_ROLE_NAME)
        own_t1 = _case(
            tenant_a, product_a, client_a, days=15, ref="CA-MINE-T1", submitted_by=ca
        )
        own_t2 = _case(
            tenant_a, product_a, client_a, days=45, ref="CA-MINE-T2", submitted_by=ca
        )
        _case(
            tenant_a, product_a, client_a, days=12, ref="CA-MINE-OTH", submitted_by=other
        )
        own_t2.assigned_to = None
        own_t2.save(update_fields=["assigned_to"])

    api = _api(ca, tenant_a)
    mine = api.get("/api/v1/collection-cases/", {"mine": 1, "open": 1})
    assert mine.status_code == 200
    refs = {r["application_reference"] for r in mine.data["results"]}
    assert "CA-MINE-T1" in refs
    assert "CA-MINE-T2" in refs
    assert "CA-MINE-OTH" not in refs

    dash_mine = api.get("/api/v1/collection-cases/agent-dashboard/", {"scope": "mine"})
    assert dash_mine.status_code == 200
    assert dash_mine.data["assigned_open"] == 2
    dash_team = api.get("/api/v1/collection-cases/agent-dashboard/", {"scope": "team"})
    assert dash_team.data["assigned_open"] == 2
    assert own_t1.assigned_to_id == ca.id


def test_charge_affaire_operates_own_t1_only(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        ensure_default_tranches(tenant_a)
        ca = _role_user(tenant_a, "ca1", CHARGE_AFFAIRE_ROLE_NAME)
        other = _role_user(tenant_a, "ca2", CHARGE_AFFAIRE_ROLE_NAME)
        own_t1 = _case(
            tenant_a, product_a, client_a, days=15, ref="CA-OWN-T1", submitted_by=ca
        )
        other_t1 = _case(
            tenant_a, product_a, client_a, days=12, ref="CA-OTH-T1", submitted_by=other
        )
        own_t2 = _case(
            tenant_a, product_a, client_a, days=45, ref="CA-OWN-T2", submitted_by=ca
        )

    api = _api(ca, tenant_a)
    listed = api.get("/api/v1/collection-cases/")
    assert listed.status_code == 200
    refs = {r["application_reference"] for r in listed.data["results"]}
    assert "CA-OWN-T1" in refs
    assert "CA-OWN-T2" in refs
    assert "CA-OTH-T1" not in refs

    detail = api.get(f"/api/v1/collection-cases/{own_t1.id}/")
    assert detail.status_code == 200
    assert detail.data["can_operate"] is True

    ok = api.post(
        "/api/v1/collection-actions/",
        {
            "case": str(own_t1.id),
            "action_type": "CALL",
            "action_date": date.today().isoformat(),
            "result": "Joignable",
        },
        format="json",
    )
    assert ok.status_code == 201, ok.content
    action_id = ok.data["id"]
    assert str(ok.data["created_by"]) == str(ca.id)

    forbidden_other = api.get(f"/api/v1/collection-cases/{other_t1.id}/")
    assert forbidden_other.status_code == 404

    t2 = api.get(f"/api/v1/collection-cases/{own_t2.id}/")
    assert t2.status_code == 200
    assert t2.data["can_operate"] is False

    blocked = api.post(
        "/api/v1/collection-actions/",
        {
            "case": str(own_t2.id),
            "action_type": "CALL",
            "action_date": date.today().isoformat(),
        },
        format="json",
    )
    assert blocked.status_code == 403

    dialogue = api.post(
        f"/api/v1/collection-cases/{own_t2.id}/dialogue/",
        {"kind": "QUESTION", "body": "Merci de relancer le client."},
        format="json",
    )
    assert dialogue.status_code == 201, dialogue.content
    assert str(dialogue.data["created_by"]) == str(ca.id)

    patch_own = api.patch(
        f"/api/v1/collection-actions/{action_id}/",
        {"result": "Rappel demain"},
        format="json",
    )
    assert patch_own.status_code == 200

    # Recouvrement voit le dossier T1 mais ne peut pas éditer l'action du CA.
    reco = _role_user(tenant_a, "reco1", RESP_RECOUVREMENT_ROLE_NAME)
    reco_api = _api(reco, tenant_a)
    steal = reco_api.patch(
        f"/api/v1/collection-actions/{action_id}/",
        {"result": "piraté"},
        format="json",
    )
    assert steal.status_code == 403


def test_recouvrement_operates_t2_not_t1(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        ensure_default_tranches(tenant_a)
        reco = _role_user(tenant_a, "reco2", RESP_RECOUVREMENT_ROLE_NAME)
        ca = _role_user(tenant_a, "ca3", CHARGE_AFFAIRE_ROLE_NAME)
        t1 = _case(tenant_a, product_a, client_a, days=10, ref="RECO-T1", submitted_by=ca)
        t2 = _case(tenant_a, product_a, client_a, days=50, ref="RECO-T2", submitted_by=ca)

    api = _api(reco, tenant_a)
    d1 = api.get(f"/api/v1/collection-cases/{t1.id}/")
    d2 = api.get(f"/api/v1/collection-cases/{t2.id}/")
    assert d1.data["can_operate"] is False
    assert d2.data["can_operate"] is True

    assert api.post(
        "/api/v1/collection-actions/",
        {
            "case": str(t2.id),
            "action_type": "VISIT",
            "action_date": date.today().isoformat(),
        },
        format="json",
    ).status_code == 201
    assert api.post(
        "/api/v1/collection-actions/",
        {
            "case": str(t1.id),
            "action_type": "VISIT",
            "action_date": date.today().isoformat(),
        },
        format="json",
    ).status_code == 403

    talk = api.post(
        f"/api/v1/collection-cases/{t1.id}/dialogue/",
        {"kind": "RECOMMENDATION", "body": "Passer en visite."},
        format="json",
    )
    assert talk.status_code == 201


def test_dialogue_attached_to_action(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        ensure_default_tranches(tenant_a)
        ca = _role_user(tenant_a, "ca_dlg_act", CHARGE_AFFAIRE_ROLE_NAME)
        reco = _role_user(tenant_a, "reco_dlg_act", RESP_RECOUVREMENT_ROLE_NAME)
        t1 = _case(
            tenant_a, product_a, client_a, days=10, ref="DLG-ACT-1", submitted_by=ca
        )
        t2 = _case(
            tenant_a, product_a, client_a, days=50, ref="DLG-ACT-2", submitted_by=ca
        )

    ca_api = _api(ca, tenant_a)
    own_action = ca_api.post(
        "/api/v1/collection-actions/",
        {
            "case": str(t1.id),
            "action_type": "CALL",
            "action_date": date.today().isoformat(),
            "result": "NRP",
        },
        format="json",
    )
    assert own_action.status_code == 201, own_action.content
    action_id = own_action.data["id"]

    reco_api = _api(reco, tenant_a)
    other_action = reco_api.post(
        "/api/v1/collection-actions/",
        {
            "case": str(t2.id),
            "action_type": "VISIT",
            "action_date": date.today().isoformat(),
        },
        format="json",
    )
    assert other_action.status_code == 201, other_action.content

    case_msg = reco_api.post(
        f"/api/v1/collection-cases/{t1.id}/dialogue/",
        {"kind": "QUESTION", "body": "Où en est le dossier ?"},
        format="json",
    )
    assert case_msg.status_code == 201

    action_msg = reco_api.post(
        f"/api/v1/collection-cases/{t1.id}/dialogue/",
        {
            "kind": "RECOMMENDATION",
            "body": "Relancer demain matin.",
            "action": action_id,
        },
        format="json",
    )
    assert action_msg.status_code == 201, action_msg.content
    assert str(action_msg.data["action"]) == str(action_id)

    wrong = reco_api.post(
        f"/api/v1/collection-cases/{t1.id}/dialogue/",
        {
            "kind": "QUESTION",
            "body": "Mauvais rattachement",
            "action": other_action.data["id"],
        },
        format="json",
    )
    assert wrong.status_code == 400

    detail = reco_api.get(f"/api/v1/collection-cases/{t1.id}/")
    assert detail.status_code == 200
    bodies = [m["body"] for m in detail.data["dialogue"]]
    assert "Où en est le dossier ?" in bodies
    assert "Relancer demain matin." not in bodies
    action = next(a for a in detail.data["actions"] if a["id"] == action_id)
    assert [m["body"] for m in action["dialogue"]] == ["Relancer demain matin."]


def test_juridique_operates_t3(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        ensure_default_tranches(tenant_a)
        jur = _role_user(tenant_a, "jur1", RESP_JURIDIQUE_ROLE_NAME)
        t3 = _case(tenant_a, product_a, client_a, days=120, ref="JUR-T3")

    api = _api(jur, tenant_a)
    detail = api.get(f"/api/v1/collection-cases/{t3.id}/")
    assert detail.status_code == 200
    assert detail.data["can_operate"] is True
    assert api.post(
        "/api/v1/collection-actions/",
        {
            "case": str(t3.id),
            "action_type": "LEGAL",
            "action_date": date.today().isoformat(),
        },
        format="json",
    ).status_code == 201


def test_admin_operates_all_and_import_tranches(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        ensure_default_tranches(tenant_a)
        admin = _role_user(tenant_a, "filadm2", FILIALE_ADMIN_ROLE_NAME)
        admin.is_staff = True
        admin.save(update_fields=["is_staff"])
        reco = _role_user(tenant_a, "reco3", RESP_RECOUVREMENT_ROLE_NAME)
        t1 = _case(tenant_a, product_a, client_a, days=8, ref="ADM-T1")
        t3 = _case(tenant_a, product_a, client_a, days=130, ref="ADM-T3")

    admin_api = _api(admin, tenant_a)
    assert admin_api.get(f"/api/v1/collection-cases/{t1.id}/").data["can_operate"]
    assert admin_api.get(f"/api/v1/collection-cases/{t3.id}/").data["can_operate"]

    reco_api = _api(reco, tenant_a)
    denied = reco_api.post("/api/v1/collection-cases/import-cbs-portfolio/")
    assert denied.status_code == 403

    replace = reco_api.post(
        "/api/v1/collection-tranches/replace/",
        {"tranches": []},
        format="json",
    )
    assert replace.status_code == 403


def test_chef_agence_scope(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        ensure_default_tranches(tenant_a)
        ag_a = Agency.objects.create(tenant=tenant_a, code="AG1", name="Agence 1")
        ag_b = Agency.objects.create(tenant=tenant_a, code="AG2", name="Agence 2")
        chef = _role_user(
            tenant_a,
            "chef1",
            CHEF_AGENCE_ROLE_NAME,
            agency=ag_a,
            data_scope=DataScope.AGENCY,
        )
        chef.agencies.add(ag_a)
        mine = _case(
            tenant_a, product_a, client_a, days=14, ref="CHEF-A", agency=ag_a
        )
        other = _case(
            tenant_a, product_a, client_a, days=14, ref="CHEF-B", agency=ag_b
        )

    api = _api(chef, tenant_a)
    listed = api.get("/api/v1/collection-cases/")
    refs = {r["application_reference"] for r in listed.data["results"]}
    assert "CHEF-A" in refs
    assert "CHEF-B" not in refs
    assert api.get(f"/api/v1/collection-cases/{mine.id}/").data["can_operate"] is True


def test_charge_affaire_cannot_see_other_actions(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        ensure_default_tranches(tenant_a)
        ca = _role_user(tenant_a, "ca_hid", CHARGE_AFFAIRE_ROLE_NAME)
        other = _role_user(tenant_a, "ca_hid2", CHARGE_AFFAIRE_ROLE_NAME)
        foreign = _case(
            tenant_a, product_a, client_a, days=11, ref="HID-T1", submitted_by=other
        )
    other_api = _api(other, tenant_a)
    created = other_api.post(
        "/api/v1/collection-actions/",
        {
            "case": str(foreign.id),
            "action_type": "CALL",
            "action_date": date.today().isoformat(),
        },
        format="json",
    )
    assert created.status_code == 201
    hidden = _api(ca, tenant_a).get(
        "/api/v1/collection-actions/", {"case": str(foreign.id)}
    )
    assert hidden.status_code == 200
    assert hidden.data["count"] == 0


def test_exploitation_operates_t1_filiale(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        ensure_default_tranches(tenant_a)
        exp = _role_user(tenant_a, "exp1", RESP_EXPLOITATION_ROLE_NAME)
        t1 = _case(tenant_a, product_a, client_a, days=9, ref="EXP-T1")
        t2 = _case(tenant_a, product_a, client_a, days=40, ref="EXP-T2")

    api = _api(exp, tenant_a)
    assert api.get(f"/api/v1/collection-cases/{t1.id}/").data["can_operate"] is True
    assert api.get(f"/api/v1/collection-cases/{t2.id}/").data["can_operate"] is False


def test_collection_list_filters(tenant_a, product_a, client_a):
    with tenant_context(tenant_a.id):
        ensure_default_tranches(tenant_a)
        admin = _role_user(tenant_a, "filadm_f", FILIALE_ADMIN_ROLE_NAME)
        admin.is_staff = True
        admin.save(update_fields=["is_staff"])
        ag = Agency.objects.create(tenant=tenant_a, code="AGF", name="Agence F")
        ca = _role_user(tenant_a, "ca_filt", CHARGE_AFFAIRE_ROLE_NAME)
        t1 = _case(
            tenant_a,
            product_a,
            client_a,
            days=12,
            ref="FILT-T1",
            submitted_by=ca,
            agency=ag,
        )
        _case(tenant_a, product_a, client_a, days=55, ref="FILT-T2")

    api = _api(admin, tenant_a)
    by_agency = api.get("/api/v1/collection-cases/", {"agency": str(ag.id)})
    assert by_agency.status_code == 200
    refs = {r["application_reference"] for r in by_agency.data["results"]}
    assert "FILT-T1" in refs
    assert "FILT-T2" not in refs

    by_owner = api.get(
        "/api/v1/collection-cases/", {"owner_kind": "COLLECTION"}
    )
    assert by_owner.status_code == 200
    refs = {r["application_reference"] for r in by_owner.data["results"]}
    assert "FILT-T2" in refs
    assert "FILT-T1" not in refs

    by_mgr = api.get("/api/v1/collection-cases/", {"gestionnaire": str(ca.id)})
    refs = {r["application_reference"] for r in by_mgr.data["results"]}
    assert "FILT-T1" in refs
    assert "FILT-T2" not in refs
    assert t1.tranche_id


def test_recouvrement_can_call_surety(tenant_a, product_a, client_a):
    from apps.sureties.models import Surety, SuretyEngagement

    with tenant_context(tenant_a.id):
        reco = _role_user(tenant_a, "reco_call", RESP_RECOUVREMENT_ROLE_NAME)
        reco.data_scope = DataScope.TENANT
        reco.save(update_fields=["data_scope"])
        case = _case(
            tenant_a, product_a, client_a, days=45, ref="CALL-SURETY"
        )
        case.assigned_to = reco
        case.save(update_fields=["assigned_to"])
        surety = Surety.objects.create(
            tenant=tenant_a,
            surety_type=Surety.SuretyType.PHYSICAL,
            first_name="Mamadou",
            last_name="Ba",
            commitment_ceiling=Decimal("8000000"),
        )
        eng = SuretyEngagement.objects.create(
            tenant=tenant_a,
            surety=surety,
            application=case.loan.application,
            amount=Decimal("500000"),
            engagement_type=SuretyEngagement.EngagementType.SIMPLE,
        )

    assert reco.has_perm("sureties.change_suretyengagement")
    api = _api(reco, tenant_a)
    called = api.post(f"/api/v1/surety-engagements/{eng.id}/call/", {})
    assert called.status_code == 200, called.content
    assert called.data["status"] == SuretyEngagement.Status.CALLED
