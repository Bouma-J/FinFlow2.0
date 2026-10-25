"""Fonctions métier explicites ; les noms de rôles restent des libellés libres.

Une capacité complète les permissions d'action et ne remplace jamais les
contrôles de filiale, d'agence, de dossier ou de séparation des acteurs.
"""
from django.db.models import Q

TENANT_ADMIN = "tenant_admin"
CREDIT_ADMIN = "credit_admin"
RELATIONSHIP_MANAGER = "relationship_manager"
AGENCY_MANAGER = "agency_manager"
CREDIT_ANALYST = "credit_analyst"
CREDIT_COMMITTEE = "credit_committee"
GROUP_CREDIT_COMMITTEE = "group_credit_committee"
CREDIT_DECISION = "credit_decision"
OPERATIONS = "operations"
INTERNAL_CONTROL = "internal_control"
AUDIT = "audit"
COLLECTION_OFFICER = "collection_officer"
LEGAL_OFFICER = "legal_officer"
COLLECTION_MANAGER = "collection_manager"
COLLECTION_BROAD_VIEW = "collection_broad_view"

CAPABILITIES = {
    TENANT_ADMIN: "Administration de la filiale",
    CREDIT_ADMIN: "Administration crédit et contrôle final",
    RELATIONSHIP_MANAGER: "Gestion de la relation et du portefeuille personnel",
    AGENCY_MANAGER: "Responsabilité d'agence",
    CREDIT_ANALYST: "Analyse crédit",
    CREDIT_COMMITTEE: "Participation à un comité de crédit",
    GROUP_CREDIT_COMMITTEE: "Participation transverse au comité Groupe",
    CREDIT_DECISION: "Décision de crédit de direction",
    OPERATIONS: "Opérations de mise en place",
    INTERNAL_CONTROL: "Contrôle permanent et visites de contrôle",
    AUDIT: "Audit indépendant",
    COLLECTION_OFFICER: "Recouvrement spécialisé",
    LEGAL_OFFICER: "Recouvrement juridique",
    COLLECTION_MANAGER: "Supervision du recouvrement gestionnaire",
    COLLECTION_BROAD_VIEW: "Consultation du recouvrement de la filiale",
}

CAPABILITY_PERMISSIONS = tuple(
    (f"business_{code}", label) for code, label in CAPABILITIES.items()
)

# Une combinaison incohérente reste interdite après renommage ou répartition
# des capacités entre plusieurs rôles personnalisés.
INCOMPATIBLE_CAPABILITIES = (
    frozenset({RELATIONSHIP_MANAGER, CREDIT_COMMITTEE}),
    frozenset({CREDIT_ANALYST, CREDIT_COMMITTEE}),
    frozenset({RELATIONSHIP_MANAGER, CREDIT_DECISION}),
    frozenset({CREDIT_ANALYST, CREDIT_DECISION}),
    frozenset({OPERATIONS, AUDIT}),
    frozenset({OPERATIONS, INTERNAL_CONTROL}),
    frozenset({COLLECTION_OFFICER, AUDIT}),
)


def group_capabilities(group):
    if group is None:
        return set()
    return {
        code.removeprefix("business_")
        for code in group.permissions.filter(
            content_type__app_label="accounts", content_type__model="user", codename__startswith="business_"
        ).values_list("codename", flat=True)
        if code.removeprefix("business_") in CAPABILITIES
    }


def group_has_capability(group, code):
    return code in CAPABILITIES and code in group_capabilities(group)


def user_capabilities(user):
    if not user or not getattr(user, "is_authenticated", False) or not user.is_active:
        return set()
    if user.is_superuser:
        return set(CAPABILITIES)
    groups = user.groups.all()
    if user.is_group_level:
        groups = groups.filter(tenant_role__isnull=True)
    elif user.tenant_id:
        groups = groups.filter(tenant_role__tenant_id=user.tenant_id)
    else:
        return set()
    codes = set(groups.values_list("permissions__codename", flat=True).filter(
        permissions__content_type__app_label="accounts",
        permissions__content_type__model="user",
        permissions__codename__startswith="business_",
    ))
    return {code.removeprefix("business_") for code in codes if code and code.removeprefix("business_") in CAPABILITIES}


def user_has_capability(user, code):
    return code in CAPABILITIES and code in user_capabilities(user)


def users_with_capability(queryset, *codes):
    """Présélection SQL, puis contrôle exact via user_capabilities à l'usage."""
    names = [f"business_{code}" for code in codes if code in CAPABILITIES]
    return queryset.filter(
        Q(groups__permissions__content_type__app_label="accounts", groups__permissions__content_type__model="user"),
        groups__permissions__codename__in=names,
    ).distinct()


def validate_capability_combination(codes):
    for pair in INCOMPATIBLE_CAPABILITIES:
        if pair.issubset(codes):
            labels = [CAPABILITIES[code] for code in sorted(pair)]
            raise ValueError(f"Séparation des tâches : les fonctions « {labels[0]} » et « {labels[1]} » sont incompatibles.")
