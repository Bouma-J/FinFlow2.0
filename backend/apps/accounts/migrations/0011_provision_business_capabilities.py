"""Attribution unique des fonctions des profils historiques, avant noms libres."""
from django.db import migrations


PACKS = {
    "Administrateur filiale": ("tenant_admin", ["tenant_admin"]),
    "Administrateur crédit": ("credit_admin", ["credit_admin"]),
    "Chargé d'affaire": ("relationship_manager", ["relationship_manager"]),
    "Chef d'agence": ("agency_manager", ["agency_manager"]),
    "Responsable exploitation": ("operations_manager", ["collection_manager", "collection_broad_view"]),
    "Responsable crédit et risque": ("credit_risk_manager", []),
    "Analyste crédit et risque": ("credit_analyst", ["credit_analyst"]),
    "Comité de crédit filiale": ("credit_committee", ["credit_committee"]),
    "Comité de crédit": ("credit_committee", ["credit_committee"]),
    "Comité de crédit groupe": ("group_credit_committee", ["credit_committee", "group_credit_committee"]),
    "Responsable retails": ("retail_manager", []),
    "Directeur Général": ("general_manager", ["credit_decision", "collection_broad_view"]),
    "Responsable Juridique": ("legal_manager", ["legal_officer", "collection_broad_view"]),
    "Assistant juridique": ("legal_assistant", ["legal_officer", "collection_broad_view"]),
    "Responsable des opérations": ("operations", ["operations"]),
    "Assistant des opérations": ("operations_assistant", ["operations"]),
    "Responsable contrôle interne": ("internal_control", ["internal_control"]),
    "Assistant Contrôle Interne": ("control_assistant", ["internal_control"]),
    "Assistant Audit": ("audit_assistant", ["audit"]),
    "Responsable Audit": ("audit", ["audit"]),
    "Assistant recouvrement": ("collection_assistant", ["collection_officer", "collection_broad_view"]),
    "Responsable recouvrement": ("collection_manager", ["collection_officer", "collection_broad_view"]),
    "Responsable administratif et financier": ("finance_manager", ["collection_broad_view"]),
    "Chef comptable": ("chief_accountant", []), "Comptable": ("accountant", []), "Lecteur": ("reader", []),
}
LABELS = {
    "tenant_admin": "Administration de la filiale", "credit_admin": "Administration crédit et contrôle final",
    "relationship_manager": "Gestion de la relation et du portefeuille personnel", "agency_manager": "Responsabilité d'agence",
    "credit_analyst": "Analyse crédit", "credit_committee": "Participation à un comité de crédit",
    "group_credit_committee": "Participation transverse au comité Groupe", "credit_decision": "Décision de crédit de direction",
    "operations": "Opérations de mise en place", "internal_control": "Contrôle permanent et visites de contrôle",
    "audit": "Audit indépendant", "collection_officer": "Recouvrement spécialisé", "legal_officer": "Recouvrement juridique",
    "collection_manager": "Supervision du recouvrement gestionnaire", "collection_broad_view": "Consultation du recouvrement de la filiale",
}


def provision(apps, schema_editor):
    db = schema_editor.connection.alias
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    TenantRole = apps.get_model("accounts", "TenantRole")
    Group = apps.get_model("auth", "Group")
    ct, _ = ContentType.objects.using(db).get_or_create(app_label="accounts", model="user")
    permissions = {}
    for code, label in LABELS.items():
        permissions[code], _ = Permission.objects.using(db).get_or_create(content_type=ct, codename=f"business_{code}", defaults={"name": label})
    for role in TenantRole.objects.using(db).filter(name__in=PACKS).order_by("name", "pk"):
        pack, codes = PACKS[role.name]
        # Les deux libellés historiques du comité peuvent coexister.
        # Les deux gardent leur fonction, un seul porte l'identité du pack.
        if not TenantRole.objects.using(db).filter(tenant_id=role.tenant_id, pack_code=pack).exists():
            role.pack_code = pack
            role.save(using=db, update_fields=["pack_code"])
        role.group.permissions.add(*(permissions[code] for code in codes))
    # Les rôles personnalisés/renommés déjà habilités à la mise en place
    # gardent leur fonction lors de la transition. Cette inférence n'est
    # exécutée qu'ici, jamais à l'enregistrement ni à l'exécution métier.
    for role in TenantRole.objects.using(db).exclude(name__in=PACKS):
        action_codes = set(role.group.permissions.filter(content_type__app_label="credits").values_list("codename", flat=True))
        codes = set()
        if action_codes & {"review_setup_creditapplication", "authorize_setup_creditapplication", "execute_setup_creditadmin"}:
            codes.add("credit_admin")
        if "execute_setup_operations" in action_codes:
            codes.add("operations")
        role.group.permissions.add(*(permissions[code] for code in codes))
    for group in Group.objects.using(db).filter(name="__ff_group__credit_committee"):
        group.permissions.add(permissions["credit_committee"], permissions["group_credit_committee"])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0010_business_capabilities")]
    operations = [migrations.RunPython(provision, migrations.RunPython.noop)]
