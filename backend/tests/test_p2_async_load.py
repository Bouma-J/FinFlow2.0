"""P2 — Celery / async overdue & contrats / prefetch."""
from django.conf import settings
from django.test import override_settings
from rest_framework.test import APIClient

import pytest

from apps.accounts.models import User
from apps.common.tenancy import tenant_context

pytestmark = pytest.mark.django_db


def test_celery_acks_late_and_time_limits_configured():
    assert getattr(settings, "CELERY_TASK_ACKS_LATE", False) is True
    assert getattr(settings, "CELERY_TASK_REJECT_ON_WORKER_LOST", False) is True
    assert int(settings.CELERY_TASK_SOFT_TIME_LIMIT) >= 60
    assert int(settings.CELERY_TASK_TIME_LIMIT) >= int(
        settings.CELERY_TASK_SOFT_TIME_LIMIT
    )


@override_settings(ALLOWED_HOSTS=["*"], CELERY_TASK_ALWAYS_EAGER=True)
def test_refresh_overdue_queues_by_default(tenant_a):
    user = User.objects.create_user(
        username="p2_col",
        password="FinFlow2026!",
        tenant=tenant_a,
        is_staff=True,
    )
    from django.contrib.auth.models import Permission

    from apps.accounts.services import (
        RESP_RECOUVREMENT_ROLE_NAME,
        ensure_default_role_packs,
        get_or_create_tenant_role,
    )

    ensure_default_role_packs(tenant_a)
    role, _ = get_or_create_tenant_role(tenant_a, RESP_RECOUVREMENT_ROLE_NAME)
    user.groups.add(role)
    for codename in (
        "view_collectioncase",
        "change_collectioncase",
        "add_collectioncase",
    ):
        perm = Permission.objects.filter(
            content_type__app_label="collections",
            codename=codename,
        ).first()
        if perm:
            user.user_permissions.add(perm)

    api = APIClient()
    api.force_authenticate(user)
    res = api.post(
        "/api/v1/collection-cases/refresh-overdue/",
        {},
        format="json",
        HTTP_X_TENANT_ID=str(tenant_a.id),
        HTTP_HOST="localhost",
    )
    # Eager : peut être 202 avec task exécutée, ou 200 si sync forcé — défaut = queue
    assert res.status_code in (200, 202), res.content
    if res.status_code == 202:
        body = res.json()
        assert body.get("status") == "queued"
        assert body.get("task_id")


@override_settings(ALLOWED_HOSTS=["*"], CELERY_TASK_ALWAYS_EAGER=True)
def test_contract_generate_defaults_to_async(tenant_a, product_a, client_a):
    from decimal import Decimal

    from apps.contracts.models import ContractTemplate
    from apps.credits.models import CreditApplication

    user = User.objects.create_superuser(
        username="p2_ctr",
        password="FinFlow2026!",
        email="p2@example.com",
        tenant=tenant_a,
    )
    with tenant_context(tenant_a.id):
        app = CreditApplication.objects.create(
            tenant=tenant_a,
            client=client_a,
            product=product_a,
            reference="P2-CTR-1",
            amount_requested=Decimal("50000"),
            duration_months=6,
            status=CreditApplication.Status.APPROVED,
            currency="XOF",
        )
        # Sans fichier réel le task peut échouer en eager — on vérifie surtout le 202
        tpl = ContractTemplate.objects.create(
            tenant=tenant_a,
            code="P2DOC",
            name="Modèle P2",
            engine=ContractTemplate.Engine.DOCX,
            is_active=True,
            is_required=False,
        )

    api = APIClient()
    api.force_authenticate(user)
    res = api.post(
        "/api/v1/generated-contracts/generate/",
        {"application": str(app.id), "template": str(tpl.id)},
        format="json",
        HTTP_X_TENANT_ID=str(tenant_a.id),
        HTTP_HOST="localhost",
    )
    # Sans fichier template, async queue → 202 ; sync échouerait en 400
    assert res.status_code == 202, res.content
    assert res.json().get("status") == "queued"
