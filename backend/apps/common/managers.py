"""Managers et QuerySets appliquant l'isolation multi-tenants."""
from django.db import models
from django.utils import timezone

from .tenancy import get_current_tenant_id, is_group_context


class TenantQuerySet(models.QuerySet):
    """QuerySet filtrant automatiquement sur le tenant courant."""

    def for_current_tenant(self):
        tenant_id = get_current_tenant_id()
        # En contexte Groupe, aucune restriction implicite : les vues
        # de consolidation appliquent leurs propres filtres explicites.
        if is_group_context():
            return self
        if tenant_id is None:
            # Aucun tenant résolu : par sécurité, on ne renvoie rien.
            return self.none()
        return self.filter(tenant_id=tenant_id)


class SoftDeleteTenantQuerySet(TenantQuerySet):
    def delete(self):
        return models.QuerySet.update(
            self, is_deleted=True, deleted_at=timezone.now()
        )

    def hard_delete(self):
        return models.QuerySet.delete(self)

    def alive(self):
        return self.filter(is_deleted=False)

    def dead(self):
        return self.filter(is_deleted=True)


class TenantManager(models.Manager):
    """Manager par défaut : renvoie uniquement les données du tenant courant."""

    def get_queryset(self):
        return TenantQuerySet(self.model, using=self._db).for_current_tenant()


class SoftDeleteTenantManager(TenantManager):
    """Tenant courant + exclusion des enregistrements soft-deleted."""

    def get_queryset(self):
        return (
            SoftDeleteTenantQuerySet(self.model, using=self._db)
            .for_current_tenant()
            .alive()
        )


class AllTenantsManager(models.Manager):
    """Manager d'échappement explicite (admin, migrations, tâches système)."""

    def get_queryset(self):
        return TenantQuerySet(self.model, using=self._db)


class SoftDeleteAllTenantsManager(AllTenantsManager):
    """Toutes filiales, hors soft-deleted (batchs / miroirs)."""

    def get_queryset(self):
        return SoftDeleteTenantQuerySet(self.model, using=self._db).alive()
