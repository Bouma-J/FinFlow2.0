"""
Gestion du tenant courant (filiale) pour l'isolation multi-tenants.

On utilise un `ContextVar` afin d'être compatible avec les contextes
synchrones et asynchrones, et sûr vis-à-vis de la concurrence.

Approche retenue : base de données partagée + colonne discriminante
(`tenant`) avec filtrage automatique. Une alternative « un schéma par
filiale » (django-tenants) est documentée dans le README ; l'abstraction
`TenantScopedModel` permet de faire évoluer ce choix sans réécrire le
code métier.
"""
from contextlib import contextmanager
from contextvars import ContextVar

# Identifiant du tenant courant (UUID) ou None (contexte Groupe / système)
_current_tenant_id: ContextVar = ContextVar("current_tenant_id", default=None)

# Indique un contexte « Groupe » autorisé à voir plusieurs tenants
_is_group_context: ContextVar = ContextVar("is_group_context", default=False)


def set_current_tenant(tenant_id):
    """Définit le tenant courant. Retourne un token de réinitialisation."""
    return _current_tenant_id.set(tenant_id)


def get_current_tenant_id():
    """Retourne l'identifiant du tenant courant, ou None."""
    return _current_tenant_id.get()


def reset_current_tenant(token):
    """Réinitialise le tenant courant à sa valeur précédente."""
    _current_tenant_id.reset(token)


def set_group_context(value: bool):
    return _is_group_context.set(value)


def is_group_context() -> bool:
    return _is_group_context.get()


@contextmanager
def tenant_context(tenant_id, group: bool = False):
    """Context manager pratique (tâches Celery, scripts, tests)."""
    token = _current_tenant_id.set(tenant_id)
    gtoken = _is_group_context.set(group)
    try:
        yield
    finally:
        _current_tenant_id.reset(token)
        _is_group_context.reset(gtoken)
