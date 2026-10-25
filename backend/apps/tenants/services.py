"""Services de provisionnement d'une nouvelle filiale."""

from apps.accounts.services import (
    DEFAULT_ROLE_PACKS,
    FILIALE_ADMIN_ROLE_NAME,
    ensure_default_role_packs,
)

DEFAULT_TENANT_ROLES = (
    FILIALE_ADMIN_ROLE_NAME,
    *DEFAULT_ROLE_PACKS.keys(),
)


def bootstrap_tenant(tenant):
    """Crée les rôles métier, référentiels catalogue, packs RBAC et connecteur Perfect."""
    from apps.catalog.defaults import ensure_catalog_defaults
    from apps.corebanking.perfect_defaults import ensure_perfect_connector
    from apps.documents.category_seed import ensure_all_process_document_categories
    from apps.workflow.defaults import ensure_process_workflows

    ensure_default_role_packs(tenant)
    ensure_catalog_defaults(tenant)
    ensure_perfect_connector(tenant, demo=False)
    ensure_process_workflows(tenant)
    ensure_all_process_document_categories(tenant)


# Entités dont la présence rend une filiale non supprimable : elles portent
# l'historique métier à valeur probante. Les référentiels créés par
# `bootstrap_tenant` (rôles, catégories GED, workflows…) n'en font pas partie,
# afin qu'une filiale créée par erreur reste supprimable.
BUSINESS_DATA_MODELS = (
    ("clients.Client", "clients"),
    ("credits.CreditApplication", "dossiers de crédit"),
    ("credits.Loan", "prêts"),
    ("guarantees.Guarantee", "garanties"),
    ("sureties.Surety", "cautions"),
    ("documents.Document", "documents GED"),
    ("collections.CollectionCase", "dossiers de recouvrement"),
    ("accounts.User", "utilisateurs"),
)


def tenant_business_data(tenant):
    """Inventaire des données métier d'une filiale : ``[(libellé, nombre)]``.

    Ne remonte que les entités non vides, dans l'ordre de `BUSINESS_DATA_MODELS`.
    """
    from django.apps import apps

    found = []
    for label, wording in BUSINESS_DATA_MODELS:
        model = apps.get_model(label)
        manager = getattr(model, "all_tenants", model._default_manager)
        count = manager.filter(tenant_id=tenant.pk).count()
        if count:
            found.append((wording, count))
    return found
