"""Provisionne les droits distincts de contrôle, d'autorisation et d'exécution."""

import uuid

from django.db import migrations


CREDIT_ADMIN_SPEC = (
    ("clients", "view_client"),
    ("credits", "view_creditapplication"),
    ("credits", "view_creditinstructionpolicy"),
    ("credits", "view_financialanalysis"),
    ("credits", "view_fieldvisit"),
    ("credits", "view_creditdocument"),
    ("credits", "view_analysisthreshold"),
    ("credits", "view_loan"),
    ("guarantees", "view_guarantee"),
    ("guarantees", "view_guaranteemovement"),
    ("guarantees", "view_guaranteereleaserequest"),
    ("guarantees", "view_dationrequest"),
    ("guarantees", "view_guaranteeformalizationrequest"),
    ("sureties", "view_surety"),
    ("sureties", "view_suretyengagement"),
    ("catalog", "view_creditproduct"),
    ("catalog", "view_productcategory"),
    ("catalog", "view_rejectreason"),
    ("catalog", "view_checklistitem"),
    ("catalog", "view_currency"),
    ("catalog", "view_loanperiodicity"),
    ("catalog", "view_repaymentmethod"),
    ("catalog", "view_financingobject"),
    ("catalog", "view_servicepoint"),
    ("catalog", "view_cbsmanager"),
    ("catalog", "view_financingsource"),
    ("catalog", "view_decisionmotif"),
    ("catalog", "view_cbsprofession"),
    ("documents", "view_document"),
    ("documents", "view_documentcategory"),
    ("contracts", "view_contracttemplate"),
    ("contracts", "view_generatedcontract"),
    ("workflow", "view_approvaltask"),
    ("workflow", "view_workflowinstance"),
    ("workflow", "view_workflowdefinition"),
    ("workflow", "view_approvalstep"),
    ("workflow", "view_approvalcondition"),
    ("collections", "view_repayment"),
    ("collections", "view_collectioncase"),
    ("collections", "view_collectionaction"),
    ("collections", "view_paymentpromise"),
    ("collections", "view_collectionstagehistory"),
    ("collections", "view_collectionescalationrule"),
    ("collections", "view_collectiontranche"),
    ("collections", "view_litigationfile"),
    ("collections", "view_litigationevent"),
    ("collections", "view_legalparty"),
    ("collections", "view_litigationseizure"),
    ("collections", "view_litigationcost"),
    ("collections", "view_loanrestructure"),
    ("collections", "view_writeoff"),
    ("collections", "view_collectiondialoguemessage"),
    ("corebanking", "view_corebankingconnector"),
    ("corebanking", "view_integrationlog"),
    ("tenants", "view_agency"),
    ("audit", "view_auditlog"),
    ("notifications", "view_notificationlog"),
    ("notifications", "view_tenantnotificationsettings"),
    ("reporting", "view_dashboard"),
    ("credits", "review_setup_creditapplication"),
    ("credits", "authorize_setup_creditapplication"),
    ("credits", "execute_setup_creditadmin"),
    ("credits", "disburse_creditapplication"),
    ("credits", "initiate_disburse_creditapplication"),
    ("credits", "change_creditapplication"),
    ("documents", "add_document"),
    ("documents", "change_document"),
    ("contracts", "add_generatedcontract"),
    ("contracts", "change_generatedcontract"),
)
NEW_PERMISSIONS = {
    "review_setup_creditapplication": "Peut contrôler le dossier avant mise en place",
    "authorize_setup_creditapplication": "Peut autoriser ou révoquer la mise en place",
    "execute_setup_creditadmin": "Peut transmettre au CBS au titre de l'administration crédit",
    "execute_setup_operations": "Peut transmettre au CBS au titre des opérations",
}


def provision_roles(apps, schema_editor):
    db = schema_editor.connection.alias
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    Group = apps.get_model("auth", "Group")
    TenantRole = apps.get_model("accounts", "TenantRole")
    Tenant = apps.get_model("tenants", "Tenant")
    Policy = apps.get_model("credits", "CreditInstructionPolicy")
    ct, _ = ContentType.objects.using(db).get_or_create(
        app_label="credits", model="creditapplication"
    )
    created = {}
    for codename, name in NEW_PERMISSIONS.items():
        created[codename], _ = Permission.objects.using(db).get_or_create(
            content_type=ct, codename=codename, defaults={"name": name}
        )
    # Préserve les habilitations de transmission existantes en mode opérations.
    for group in (
        Group.objects.using(db)
        .filter(
            permissions__content_type=ct,
            permissions__codename="disburse_creditapplication",
        )
        .exclude(tenant_role__name="Administrateur crédit")
        .distinct()
    ):
        group.permissions.add(created["execute_setup_operations"])
    for tenant in Tenant.objects.using(db).all():
        role = (
            TenantRole.objects.using(db)
            .filter(tenant=tenant, name="Administrateur crédit")
            .first()
        )
        if role is None:
            group = Group.objects.using(db).create(
                name=f"__ff_{tenant.pk}__{uuid.uuid4().hex[:12]}"
            )
            role = TenantRole.objects.using(db).create(
                tenant=tenant, name="Administrateur crédit", group=group
            )
        for app_label, codename in CREDIT_ADMIN_SPEC:
            permission = (
                Permission.objects.using(db)
                .filter(content_type__app_label=app_label, codename=codename)
                .first()
            )
            if permission:
                role.group.permissions.add(permission)
        for admin in TenantRole.objects.using(db).filter(
            tenant=tenant, name="Administrateur filiale"
        ):
            admin.group.permissions.add(*created.values())
    Policy.objects.using(db).all().update(require_final_review=True)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_delegation_agency_delegation_approval_required_and_more"),
        ("credits", "0034_alter_creditapplication_options_and_more"),
    ]
    operations = [migrations.RunPython(provision_roles, migrations.RunPython.noop)]
