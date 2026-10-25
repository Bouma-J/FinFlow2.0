from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import DataScope, User
from apps.clients.models import Client
from apps.common.tenancy import tenant_context
from apps.credits.models import CreditApplication, CreditDocument, FieldVisit, Loan
from apps.guarantees.formalization_services import (
    complete_formalization_request,
    initiate_formalization_request,
    submit_formalization_request,
)
from apps.guarantees.models import (
    DationRequest,
    DocumentType,
    Guarantee,
    GuaranteeFormalizationRequest,
)
from apps.corebanking.services import CoreBankingError
from apps.guarantees.process_services import (
    ProcessError,
    initiate_dation_request,
    submit_dation_request,
    update_dation_request,
)
from apps.guarantees.renewal_services import RenewalError, renew_guarantee
from apps.workflow.models import ApprovalStep, ApprovalTask, WorkflowDefinition, WorkflowInstance
from apps.workflow.services import WorkflowError, process_decision

pytestmark = pytest.mark.django_db


def _auth(user, tenant):
    api = APIClient()
    api.force_authenticate(user)
    return api, {"HTTP_X_TENANT_ID": str(tenant.id), "HTTP_HOST": "localhost"}


def _app(tenant, client, product, *, ref="DOS-AUD", user=None):
    return CreditApplication.objects.create(
        tenant=tenant,
        reference=ref,
        client=client,
        product=product,
        amount_requested=Decimal("1000000"),
        duration_months=12,
        created_by=user,
        submitted_by=user,
    )


def _guarantee(tenant, client, application, *, ref="GAR-AUD"):
    return Guarantee.objects.create(
        tenant=tenant,
        client=client,
        application=application,
        guarantee_type=Guarantee.GuaranteeType.MORTGAGE,
        document_type=DocumentType.LAND_TITLE,
        document_number="TF-AUDIT-1",
        description="Villa test",
        expertise_value=Decimal("5000000"),
        current_value=Decimal("5000000"),
        status=Guarantee.Status.ACTIVE,
        reference=ref,
    )


def test_formalization_approval_without_legal_stage_does_not_500(
    tenant_a, client_a, product_a
):
    role = Group.objects.create(name="Validateur Form Audit")
    validator = User.objects.create_user(
        username="form_val", password="x", tenant=tenant_a
    )
    validator.groups.add(role)
    agent = User.objects.create_user(
        username="form_init", password="x", tenant=tenant_a, is_staff=True
    )
    with tenant_context(tenant_a.id):
        definition = WorkflowDefinition.objects.create(
            tenant=tenant_a,
            code="CIRCUIT-FORM-AUD",
            name="Formalisation audit",
            target_type=WorkflowDefinition.TargetType.FORMALISATION,
            version=1,
            is_active=True,
        )
        ApprovalStep.objects.create(
            tenant=tenant_a,
            definition=definition,
            name="Val",
            order=1,
            required_group=role,
            sla_hours=24,
            step_kind=ApprovalStep.StepKind.DECISIONAL,
        )
        app = _app(tenant_a, client_a, product_a, ref="DOS-FORM-AUD", user=agent)
        g = _guarantee(tenant_a, client_a, app, ref="GAR-FORM-AUD")
        req = initiate_formalization_request(guarantee=g, user=agent, as_draft=True)
        submit_formalization_request(req, user=agent)
        task = ApprovalTask.objects.get(instance__object_id=req.id)
        process_decision(
            task,
            validator,
            ApprovalTask.Status.APPROVED,
            opinion=ApprovalTask.Opinion.FAVORABLE,
        )
        req.refresh_from_db()
        assert req.status == GuaranteeFormalizationRequest.Status.APPROVED
        assert req.legal_stage == GuaranteeFormalizationRequest.LegalStage.NOT_SENT
        assert req.completed_at is None


def test_complete_formalization_rejects_draft(
    tenant_a, client_a, product_a
):
    agent = User.objects.create_user(
        username="form_draft", password="x", tenant=tenant_a
    )
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a, ref="DOS-FORM-DR", user=agent)
        g = _guarantee(tenant_a, client_a, app, ref="GAR-FORM-DR")
        req = initiate_formalization_request(guarantee=g, user=agent, as_draft=True)
        with pytest.raises(ProcessError, match="approuvé"):
            complete_formalization_request(req, user=agent)


def test_my_dossiers_group_user_stays_on_selected_tenant(
    tenant_a, tenant_b, product_a, client_a
):
    group_user = User.objects.create_user(
        username="grp_aud",
        password="x",
        is_group_level=True,
        is_staff=True,
        is_superuser=True,
    )
    perm = Permission.objects.filter(
        content_type__app_label="workflow", codename="view_approvaltask"
    ).first()
    if perm:
        group_user.user_permissions.add(perm)
    with tenant_context(tenant_b.id):
        other_client = Client.objects.create(
            tenant=tenant_b,
            reference="CLIB-AUD",
            client_type=Client.ClientType.INDIVIDUAL,
            first_name="Autre",
            last_name="Filiale",
            kyc_status=Client.KycStatus.VALIDATED,
        )
        from apps.catalog.models import CreditProduct, ProductCategory

        cat = ProductCategory.objects.create(
            tenant=tenant_b, code="CB", label="Cat B"
        )
        product_b = CreditProduct.objects.create(
            tenant=tenant_b,
            code="PB",
            label="Produit B",
            category=cat,
            amount_min=Decimal("1000"),
            amount_max=Decimal("10000000"),
            interest_rate=Decimal("10"),
        )
        app_b = _app(tenant_b, other_client, product_b, ref="DOS-B-LEAK")
        definition = WorkflowDefinition.objects.create(
            tenant=tenant_b, code="WF-B", version=1, is_active=True
        )
        ct = ContentType.objects.get_for_model(CreditApplication)
        WorkflowInstance.objects.create(
            tenant=tenant_b,
            definition=definition,
            content_type=ct,
            object_id=app_b.id,
            amount=app_b.amount_requested,
        )
        leak_id = str(app_b.id)

    api, headers = _auth(group_user, tenant_a)
    res = api.get("/api/v1/approval-tasks/my_dossiers/", **headers)
    assert res.status_code == 200, res.content
    ids = [row["id"] for row in res.json()["results"]]
    assert leak_id not in ids


def test_loan_list_respects_own_scope(tenant_a, product_a, client_a):
    owner = User.objects.create_user(
        username="loan_own",
        password="x",
        tenant=tenant_a,
        is_staff=True,
        data_scope=DataScope.OWN,
    )
    other = User.objects.create_user(
        username="loan_oth",
        password="x",
        tenant=tenant_a,
        is_staff=True,
        data_scope=DataScope.OWN,
    )
    perm = Permission.objects.filter(
        content_type__app_label="credits", codename="view_loan"
    ).first()
    if perm:
        owner.user_permissions.add(perm)
    with tenant_context(tenant_a.id):
        mine = _app(tenant_a, client_a, product_a, ref="DOS-OWN", user=owner)
        theirs = _app(tenant_a, client_a, product_a, ref="DOS-OTH", user=other)
        Loan.objects.create(
            tenant=tenant_a,
            application=mine,
            principal=Decimal("1000000"),
            interest_rate=Decimal("12"),
            duration_months=12,
            disbursed_at=timezone.localdate(),
            first_due_date=timezone.localdate(),
        )
        Loan.objects.create(
            tenant=tenant_a,
            application=theirs,
            principal=Decimal("2000000"),
            interest_rate=Decimal("12"),
            duration_months=12,
            disbursed_at=timezone.localdate(),
            first_due_date=timezone.localdate(),
        )
        mine_id = str(mine.id)

    api, headers = _auth(owner, tenant_a)
    res = api.get("/api/v1/loans/", **headers)
    assert res.status_code == 200, res.content
    apps = {row["application"] for row in res.json()["results"]}
    assert mine_id in apps
    assert str(theirs.id) not in apps


def test_add_movement_blocked_when_formalization_open(
    tenant_a, client_a, product_a
):
    admin = User.objects.create_superuser(
        username="mov_aud", password="x", email="m@x.com", tenant=tenant_a
    )
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a, ref="DOS-MOV", user=admin)
        g = _guarantee(tenant_a, client_a, app, ref="GAR-MOV")
        initiate_formalization_request(guarantee=g, user=admin, as_draft=True)
        gid = g.id
    api, headers = _auth(admin, tenant_a)
    res = api.post(
        f"/api/v1/guarantees/{gid}/add_movement/",
        {
            "movement_type": "RELEASE",
            "movement_date": str(timezone.localdate()),
        },
        format="json",
        **headers,
    )
    assert res.status_code == 400, res.content


def test_renew_active_mortgage_excludes_source(
    tenant_a, client_a, product_a
):
    admin = User.objects.create_superuser(
        username="ren_aud", password="x", email="r@x.com", tenant=tenant_a
    )
    with tenant_context(tenant_a.id):
        src_app = _app(tenant_a, client_a, product_a, ref="DOS-REN-1", user=admin)
        dst_app = _app(tenant_a, client_a, product_a, ref="DOS-REN-2", user=admin)
        source = _guarantee(tenant_a, client_a, src_app, ref="GAR-REN")
        clone = renew_guarantee(source=source, application=dst_app, user=admin)
        assert clone.pk != source.pk
        assert clone.renewed_from_id == source.pk
        assert clone.document_number == source.document_number
        assert clone.status == Guarantee.Status.ACTIVE


def test_renew_blocked_when_other_active_same_title(
    tenant_a, client_a, product_a
):
    admin = User.objects.create_superuser(
        username="ren_oth", password="x", email="ro@x.com", tenant=tenant_a
    )
    with tenant_context(tenant_a.id):
        src_app = _app(tenant_a, client_a, product_a, ref="DOS-REN-A", user=admin)
        other_app = _app(tenant_a, client_a, product_a, ref="DOS-REN-B", user=admin)
        dst_app = _app(tenant_a, client_a, product_a, ref="DOS-REN-C", user=admin)
        source = _guarantee(tenant_a, client_a, src_app, ref="GAR-REN-S")
        _guarantee(tenant_a, client_a, other_app, ref="GAR-REN-X")
        with pytest.raises(RenewalError, match="déjà pris"):
            renew_guarantee(source=source, application=dst_app, user=admin)


CBS_OK = {
    "total_outstanding": Decimal("100000"),
    "currency": "XAF",
    "breakdown": [],
    "raw": {},
    "log_id": "x",
}


@patch(
    "apps.guarantees.process_services.assert_client_outstanding_for_dation",
    return_value=CBS_OK,
)
def test_dation_approval_processerror_keeps_approved(
    _cbs, tenant_a, client_a, product_a
):
    role = Group.objects.create(name="Validateur Dation Audit")
    validator = User.objects.create_user(
        username="dat_val", password="x", tenant=tenant_a
    )
    validator.groups.add(role)
    agent = User.objects.create_user(
        username="dat_init", password="x", tenant=tenant_a, is_staff=True
    )
    with tenant_context(tenant_a.id):
        definition = WorkflowDefinition.objects.create(
            tenant=tenant_a,
            code="CIRCUIT-DAT-AUD",
            name="Dation audit",
            target_type=WorkflowDefinition.TargetType.DATION,
            version=1,
            is_active=True,
        )
        ApprovalStep.objects.create(
            tenant=tenant_a,
            definition=definition,
            name="Val",
            order=1,
            required_group=role,
            sla_hours=24,
            step_kind=ApprovalStep.StepKind.DECISIONAL,
        )
        app = _app(tenant_a, client_a, product_a, ref="DOS-DAT-AUD", user=agent)
        client_a.cbs_client_id = "CBS-AUD"
        client_a.save(update_fields=["cbs_client_id"])
        req = initiate_dation_request(
            client=client_a,
            user=agent,
            application=app,
            cbs_client_id="CBS-AUD",
            additional_assets=[{"description": "Terrain audit", "value": "50000"}],
            as_draft=True,
        )
        submit_dation_request(req, user=agent)
        task = ApprovalTask.objects.get(instance__object_id=req.id)
        with patch(
            "apps.guarantees.process_services.complete_dation_request",
            side_effect=ProcessError("refus clôture"),
        ):
            process_decision(
                task,
                validator,
                ApprovalTask.Status.APPROVED,
                opinion=ApprovalTask.Opinion.FAVORABLE,
            )
        req.refresh_from_db()
        assert req.status == DationRequest.Status.APPROVED
        assert req.completed_at is None


@patch(
    "apps.guarantees.process_services.assert_client_outstanding_for_dation",
    return_value=CBS_OK,
)
def test_dation_approval_cbs_error_rolls_back_circuit(
    _cbs_ok, tenant_a, client_a, product_a
):
    role = Group.objects.create(name="Validateur Dation CBS")
    validator = User.objects.create_user(
        username="dat_cbs", password="x", tenant=tenant_a
    )
    validator.groups.add(role)
    agent = User.objects.create_user(
        username="dat_cbs_init", password="x", tenant=tenant_a, is_staff=True
    )
    with tenant_context(tenant_a.id):
        definition = WorkflowDefinition.objects.create(
            tenant=tenant_a,
            code="CIRCUIT-DAT-CBS",
            name="Dation CBS",
            target_type=WorkflowDefinition.TargetType.DATION,
            version=1,
            is_active=True,
        )
        ApprovalStep.objects.create(
            tenant=tenant_a,
            definition=definition,
            name="Val",
            order=1,
            required_group=role,
            sla_hours=24,
            step_kind=ApprovalStep.StepKind.DECISIONAL,
        )
        app = _app(tenant_a, client_a, product_a, ref="DOS-DAT-CBS", user=agent)
        client_a.cbs_client_id = "CBS-FAIL"
        client_a.save(update_fields=["cbs_client_id"])
        req = initiate_dation_request(
            client=client_a,
            user=agent,
            application=app,
            cbs_client_id="CBS-FAIL",
            additional_assets=[{"description": "Terrain CBS", "value": "50000"}],
            as_draft=True,
        )
        submit_dation_request(req, user=agent)
        task = ApprovalTask.objects.get(instance__object_id=req.id)
        with patch(
            "apps.guarantees.process_services.assert_client_outstanding_for_dation",
            side_effect=CoreBankingError("CBS indisponible"),
        ):
            with pytest.raises(WorkflowError, match="Contrôle CBS impossible"):
                process_decision(
                    task,
                    validator,
                    ApprovalTask.Status.APPROVED,
                    opinion=ApprovalTask.Opinion.FAVORABLE,
                )
        req.refresh_from_db()
        task.refresh_from_db()
        instance = WorkflowInstance.objects.get(object_id=req.id)
        assert req.status == DationRequest.Status.IN_APPROVAL
        assert req.completed_at is None
        assert task.status == ApprovalTask.Status.PENDING
        assert instance.status == WorkflowInstance.Status.IN_PROGRESS


@patch(
    "apps.guarantees.process_services.assert_client_outstanding_for_dation",
    return_value=CBS_OK,
)
def test_dation_retry_cbs_processerror_is_400(
    _cbs, tenant_a, client_a, product_a
):
    admin = User.objects.create_superuser(
        username="dat_retry", password="x", email="dr@x.com", tenant=tenant_a
    )
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a, ref="DOS-DAT-RT", user=admin)
        client_a.cbs_client_id = "CBS-RT"
        client_a.save(update_fields=["cbs_client_id"])
        req = initiate_dation_request(
            client=client_a,
            user=admin,
            application=app,
            cbs_client_id="CBS-RT",
            additional_assets=[{"description": "Terrain relance", "value": "50000"}],
            as_draft=True,
        )
        req.status = DationRequest.Status.BLOCKED
        req.save(update_fields=["status", "updated_at"])
        rid = req.id
    api, headers = _auth(admin, tenant_a)
    with patch(
        "apps.guarantees.views.complete_dation_request",
        side_effect=ProcessError("refus relance"),
    ):
        res = api.post(
            f"/api/v1/dation-requests/{rid}/retry_cbs/",
            format="json",
            **headers,
        )
    assert res.status_code == 400, res.content


@patch(
    "apps.guarantees.process_services.assert_client_outstanding_for_dation",
    return_value=CBS_OK,
)
def test_update_dation_rejects_other_client_application(
    _cbs, tenant_a, client_a, product_a
):
    admin = User.objects.create_superuser(
        username="dat_swap", password="x", email="ds@x.com", tenant=tenant_a
    )
    with tenant_context(tenant_a.id):
        other = Client.objects.create(
            tenant=tenant_a,
            reference="CLI-SWAP",
            client_type=Client.ClientType.INDIVIDUAL,
            first_name="Autre",
            last_name="Client",
            kyc_status=Client.KycStatus.VALIDATED,
        )
        app_ok = _app(tenant_a, client_a, product_a, ref="DOS-DAT-OK", user=admin)
        app_other = _app(tenant_a, other, product_a, ref="DOS-DAT-OTH", user=admin)
        client_a.cbs_client_id = "CBS-SW"
        client_a.save(update_fields=["cbs_client_id"])
        req = initiate_dation_request(
            client=client_a,
            user=admin,
            application=app_ok,
            cbs_client_id="CBS-SW",
            additional_assets=[{"description": "Terrain swap", "value": "50000"}],
            as_draft=True,
        )
        with pytest.raises(ProcessError, match="n'appartient pas"):
            update_dation_request(req, user=admin, application=app_other)


def test_credit_document_and_visit_cannot_reassign_application(
    tenant_a, client_a, product_a
):
    admin = User.objects.create_superuser(
        username="doc_swap", password="x", email="dx@x.com", tenant=tenant_a
    )
    with tenant_context(tenant_a.id):
        app_a = _app(tenant_a, client_a, product_a, ref="DOS-DOC-A", user=admin)
        app_b = _app(tenant_a, client_a, product_a, ref="DOS-DOC-B", user=admin)
        doc = CreditDocument.objects.create(
            tenant=tenant_a,
            application=app_a,
            file=SimpleUploadedFile("piece.pdf", b"%PDF-1.4", content_type="application/pdf"),
            label="Pièce",
        )
        visit = FieldVisit.objects.create(
            tenant=tenant_a,
            application=app_a,
            visit_date=timezone.localdate(),
            visited_by=admin,
            report="OK",
        )
        doc_id, visit_id = doc.id, visit.id
        app_b_id = app_b.id
    api, headers = _auth(admin, tenant_a)
    res = api.patch(
        f"/api/v1/credit-documents/{doc_id}/",
        {"application": str(app_b_id)},
        format="json",
        **headers,
    )
    assert res.status_code == 400, res.content
    res = api.patch(
        f"/api/v1/field-visits/{visit_id}/",
        {"application": str(app_b_id)},
        format="json",
        **headers,
    )
    assert res.status_code == 400, res.content


def test_direct_realization_movement_blocked(tenant_a, client_a, product_a):
    admin = User.objects.create_superuser(
        username="mov_direct", password="x", email="md@x.com", tenant=tenant_a
    )
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a, ref="DOS-MOV-D", user=admin)
        g = _guarantee(tenant_a, client_a, app, ref="GAR-MOV-D")
        gid = g.id
    api, headers = _auth(admin, tenant_a)
    res = api.post(
        "/api/v1/guarantee-movements/",
        {
            "guarantee": str(gid),
            "movement_type": "REALIZATION",
            "movement_date": str(timezone.localdate()),
        },
        format="json",
        **headers,
    )
    assert res.status_code == 400, res.content


def test_assign_rejects_other_tenant_agent(
    tenant_a, tenant_b, client_a, product_a
):
    from apps.collections.models import CollectionCase
    from apps.collections.services import refresh_loan_overdue
    from apps.credits.models import Installment

    admin = User.objects.create_superuser(
        username="asg_adm", password="x", email="aa@x.com", tenant=tenant_a
    )
    foreign = User.objects.create_user(
        username="asg_other",
        password="x",
        tenant=tenant_b,
        is_group_level=True,
    )
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a, ref="DOS-ASG", user=admin)
        loan = Loan.objects.create(
            tenant=tenant_a,
            application=app,
            principal=Decimal("10000"),
            interest_rate=Decimal("12"),
            duration_months=6,
            disbursed_at=timezone.localdate(),
            first_due_date=timezone.localdate(),
            status=Loan.Status.ACTIVE,
        )
        Installment.objects.create(
            tenant=tenant_a,
            loan=loan,
            number=1,
            due_date=timezone.localdate(),
            principal_due=Decimal("10000"),
            interest_due=Decimal("0"),
            total_due=Decimal("10000"),
            status=Installment.Status.OVERDUE,
        )
        case = refresh_loan_overdue(
            loan,
            cbs_status={
                "settled": False,
                "days_overdue": 20,
                "overdue_amount": Decimal("10000"),
            },
        )
        cid = case.id
    api, headers = _auth(admin, tenant_a)
    res = api.post(
        f"/api/v1/collection-cases/{cid}/assign/",
        {"assigned_to": str(foreign.id)},
        format="json",
        **headers,
    )
    assert res.status_code == 400, res.content
    assert CollectionCase.all_tenants.get(pk=cid).assigned_to_id != foreign.id


def test_repayment_requires_collection_case(tenant_a, client_a, product_a):
    admin = User.objects.create_superuser(
        username="rep_nocase", password="x", email="rn@x.com", tenant=tenant_a
    )
    with tenant_context(tenant_a.id):
        app = _app(tenant_a, client_a, product_a, ref="DOS-REP-NC", user=admin)
        loan = Loan.objects.create(
            tenant=tenant_a,
            application=app,
            principal=Decimal("10000"),
            interest_rate=Decimal("12"),
            duration_months=6,
            disbursed_at=timezone.localdate(),
            first_due_date=timezone.localdate(),
            status=Loan.Status.ACTIVE,
        )
        lid = loan.id
    api, headers = _auth(admin, tenant_a)
    res = api.post(
        "/api/v1/repayments/",
        {
            "loan": str(lid),
            "amount": "1000",
            "payment_date": str(timezone.localdate()),
        },
        format="json",
        **headers,
    )
    assert res.status_code == 400, res.content
    assert "CBS" in res.json()["errors"]["detail"]


def test_litigation_rejects_foreign_client_guarantee(
    tenant_a, client_a, product_a
):
    admin = User.objects.create_superuser(
        username="lit_gar", password="x", email="lg@x.com", tenant=tenant_a
    )
    with tenant_context(tenant_a.id):
        other = Client.objects.create(
            tenant=tenant_a,
            reference="CLIB",
            client_type=Client.ClientType.INDIVIDUAL,
            first_name="Autre",
            last_name="Client",
            kyc_status=Client.KycStatus.VALIDATED,
        )
        app = _app(tenant_a, client_a, product_a, ref="DOS-LIT-G", user=admin)
        other_app = _app(tenant_a, other, product_a, ref="DOS-LIT-X", user=admin)
        foreign_g = _guarantee(tenant_a, other, other_app, ref="GAR-LIT-X")
        loan = Loan.objects.create(
            tenant=tenant_a,
            application=app,
            principal=Decimal("10000"),
            interest_rate=Decimal("12"),
            duration_months=6,
            disbursed_at=timezone.localdate(),
            first_due_date=timezone.localdate(),
            status=Loan.Status.ACTIVE,
        )
        from apps.collections.models import CollectionCase
        from apps.collections.services import refresh_loan_overdue
        from apps.credits.models import Installment

        Installment.objects.create(
            tenant=tenant_a,
            loan=loan,
            number=1,
            due_date=timezone.localdate(),
            principal_due=Decimal("10000"),
            interest_due=Decimal("0"),
            total_due=Decimal("10000"),
            status=Installment.Status.OVERDUE,
        )
        case = refresh_loan_overdue(
            loan,
            cbs_status={
                "settled": False,
                "days_overdue": 20,
                "overdue_amount": Decimal("10000"),
            },
        )
        cid, gid = case.id, foreign_g.id
    api, headers = _auth(admin, tenant_a)
    res = api.post(
        "/api/v1/litigations/",
        {
            "case": str(cid),
            "title": "Procédure test",
            "related_guarantee_ids": [str(gid)],
        },
        format="json",
        **headers,
    )
    assert res.status_code == 400, res.content
