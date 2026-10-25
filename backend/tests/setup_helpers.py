"""Préparer une mise en place avec les acteurs et contrôles métier réels."""
from apps.accounts.models import User
from apps.accounts.services import (
    CREDIT_ADMIN_ROLE_NAME, RESP_OPERATIONS_ROLE_NAME,
    ensure_default_role_packs, get_or_create_tenant_role,
)
from apps.common.tenancy import tenant_context
from apps.credits.instruction_policy import get_instruction_policy
from apps.credits.setup_authorization import authorize_setup
from rest_framework.test import APIClient


def configure_local_cbs(application):
    """Scénario local explicite, sans réseau, pour isoler les tests métier."""
    from apps.catalog.defaults import ensure_catalog_defaults
    from apps.corebanking.models import CoreBankingConnector
    ensure_catalog_defaults(application.tenant)
    with tenant_context(application.tenant_id):
        connector = CoreBankingConnector.objects.create(
            tenant=application.tenant, name="CBS local du test", protocol="REST",
            base_url="https://cbs.invalid", is_active=True,
            mapping_rules={"force_simulate": True, "disbursement": {"mode": "LOCAL", "defaults": {
                "idPointService": "PS-TEST", "idGestionnaire": "GEST-TEST", "idProduitRemb": "REMB-TEST",
            }}},
        )
        application.client.cbs_client_id = "ADHERENT-TEST"
        application.client.save(update_fields=["cbs_client_id"])
        return connector


def configure_verified_cbs(application, connector, verifier):
    """Références fictives isolées en base de test ; HTTP reste à mocker."""
    from apps.catalog.models import CbsManager, CbsProductReference, FinancingObject, RepaymentMethod, ServicePoint
    from django.utils import timezone
    with tenant_context(application.tenant_id):
        for model, code in ((ServicePoint, application.agency.cbs_point_of_service_id), (CbsManager, verifier.cbs_id)):
            model.objects.get_or_create(tenant=application.tenant, code=code,
                defaults={"label": "Référence du test", "cbs_code": code})
        obj = FinancingObject.objects.create(tenant=application.tenant, code="OBJ-TEST", label="Objet du test",
            cbs_code="45", purpose_type=application.purpose_type)
        application.financing_object = obj
        application.save(update_fields=["financing_object"])
        application.product.cbs_credit_product = CbsProductReference.objects.create(
            tenant=application.tenant, connector=connector, kind="CREDIT", cbs_code="101", label="Crédit du test",
            currency=application.currency, source_reference="Fixture isolée du test, sans appel CBS",
            verification_status="VERIFIED", verified_at=timezone.now(), verified_by=verifier)
        application.product.save(update_fields=["cbs_credit_product"])
        RepaymentMethod.objects.filter(code=application.repayment_mechanism).update(cbs_code="202")


def prepare_setup(application, *, executor=None):
    """Revue API puis autorisation nominative, sans contourner les prérequis."""
    with tenant_context(application.tenant_id):
        ensure_default_role_packs(application.tenant)
        reviewer = User.objects.create_user(
            username=f"review-{application.pk.hex}", tenant=application.tenant,
            agency=application.agency, data_scope="TENANT",
        )
        reviewer.groups.add(get_or_create_tenant_role(application.tenant, CREDIT_ADMIN_ROLE_NAME)[0])
        api = APIClient()
        api.force_authenticate(reviewer)
        response = api.post(
            f"/api/v1/credit-applications/{application.pk}/setup-review/",
            {"comment": "Vérifications documentées pour la recette.",
             "checks": {key: True for key in ("kyc", "contribution", "collateral", "terms", "insurance")}},
            format="json",
        )
        assert response.status_code == 200, response.content
        application.refresh_from_db()
        authorize_setup(application, reviewer, "Autorisation nominative après contrôle final de recette.")
        application.refresh_from_db()
        if executor is None:
            executor = User.objects.create_user(
                username=f"execute-{application.pk.hex}", tenant=application.tenant,
                agency=application.agency, data_scope="TENANT",
            )
        policy = get_instruction_policy(application.tenant_id, application=application)
        role = CREDIT_ADMIN_ROLE_NAME if policy.setup_execution_role == "CREDIT_ADMIN" else RESP_OPERATIONS_ROLE_NAME
        executor.groups.add(get_or_create_tenant_role(application.tenant, role)[0])
        for key in ("_perm_cache", "_group_perm_cache", "_user_perm_cache"):
            executor.__dict__.pop(key, None)
        return executor
