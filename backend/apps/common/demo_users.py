"""Acteurs de recette distincts pour exercer la séparation des tâches."""

from apps.accounts.models import DataScope, User
from apps.accounts.services import (
    ANALYSTE_CREDIT_RISQUE_ROLE_NAME,
    ASSISTANT_OPERATIONS_ROLE_NAME,
    CHARGE_AFFAIRE_ROLE_NAME,
    CREDIT_ADMIN_ROLE_NAME,
    CHEF_AGENCE_ROLE_NAME,
    CREDIT_COMMITTEE_FILIALE_ROLE_NAME,
    CREDIT_COMMITTEE_GROUP_ROLE_NAME,
    LECTEUR_ROLE_NAME,
    RESP_JURIDIQUE_ROLE_NAME,
    RESP_OPERATIONS_ROLE_NAME,
    get_or_create_tenant_role,
)


def ensure_demo_business_users(tenant, agency):
    specs = (
        ("fil01_admin_credit", CREDIT_ADMIN_ROLE_NAME, DataScope.TENANT),
        ("fil01_charge", CHARGE_AFFAIRE_ROLE_NAME, DataScope.OWN),
        ("fil01_analyste", ANALYSTE_CREDIT_RISQUE_ROLE_NAME, DataScope.TENANT),
        ("fil01_chef", CHEF_AGENCE_ROLE_NAME, DataScope.AGENCY),
        ("fil01_comite", CREDIT_COMMITTEE_FILIALE_ROLE_NAME, DataScope.TENANT),
        ("fil01_comite_groupe", CREDIT_COMMITTEE_GROUP_ROLE_NAME, DataScope.TENANT),
        ("fil01_operations", RESP_OPERATIONS_ROLE_NAME, DataScope.TENANT),
        ("fil01_assistant_ops", ASSISTANT_OPERATIONS_ROLE_NAME, DataScope.TENANT),
        ("fil01_juridique", RESP_JURIDIQUE_ROLE_NAME, DataScope.TENANT),
        ("fil01_lecteur", LECTEUR_ROLE_NAME, DataScope.TENANT),
    )
    created_names = []
    for username, role_name, scope in specs:
        role, _ = get_or_create_tenant_role(tenant, role_name)
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "tenant": tenant,
                "agency": agency,
                "data_scope": scope,
                "first_name": role_name,
                "last_name": "Démo",
                "must_change_password": False,
            },
        )
        if created:
            user.set_password("FinFlow2026!")
            user.save(update_fields=["password"])
            user.groups.add(role)
            created_names.append(username)
    # Le compte d'administration démo historique cumulait analyse et décision.
    # Les profils ci-dessus assurent désormais chaque étape séparément.
    admin = User.objects.filter(username="fil01_admin", tenant=tenant).first()
    if admin:
        admin.groups.remove(
            *[
                get_or_create_tenant_role(tenant, name)[0]
                for name in (
                    ANALYSTE_CREDIT_RISQUE_ROLE_NAME,
                    CHEF_AGENCE_ROLE_NAME,
                    CREDIT_COMMITTEE_FILIALE_ROLE_NAME,
                    CREDIT_COMMITTEE_GROUP_ROLE_NAME,
                )
            ]
        )
    return created_names
