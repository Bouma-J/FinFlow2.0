"""Modèles de base réutilisables par tous les modules FIN_FLOW."""
import uuid

from django.conf import settings
from django.db import models

from .managers import AllTenantsManager, TenantManager
from .tenancy import get_current_tenant_id


class UUIDModel(models.Model):
    """Clé primaire UUID (non prédictible, adaptée au multi-tenants)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    """Horodatage de création et de dernière modification."""

    created_at = models.DateTimeField("créé le", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("modifié le", auto_now=True)

    class Meta:
        abstract = True


class AuthoredModel(models.Model):
    """Traçabilité de l'auteur de la création/modification."""

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="créé par",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="modifié par",
    )

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    def delete(self):
        from django.utils import timezone

        return super().update(is_deleted=True, deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()

    def alive(self):
        return self.filter(is_deleted=False)

    def dead(self):
        return self.filter(is_deleted=True)


class SoftDeleteModel(models.Model):
    """
    Suppression logique (rétention). Les managers applicatifs doivent
    exclure ``is_deleted=True`` ; ``all_tenants`` / admin voient tout.
    """

    is_deleted = models.BooleanField("supprimé", default=False, db_index=True)
    deleted_at = models.DateTimeField(
        "supprimé le", null=True, blank=True, db_index=True
    )

    class Meta:
        abstract = True

    def soft_delete(self, *, user=None):
        from django.utils import timezone

        self.is_deleted = True
        self.deleted_at = timezone.now()
        update = ["is_deleted", "deleted_at"]
        if hasattr(self, "updated_at"):
            update.append("updated_at")
        if user is not None and hasattr(self, "updated_by_id"):
            self.updated_by = user
            update.append("updated_by")
        self.save(update_fields=update)

    def restore(self, *, user=None):
        self.is_deleted = False
        self.deleted_at = None
        update = ["is_deleted", "deleted_at"]
        if hasattr(self, "updated_at"):
            update.append("updated_at")
        if user is not None and hasattr(self, "updated_by_id"):
            self.updated_by = user
            update.append("updated_by")
        self.save(update_fields=update)


class BaseModel(UUIDModel, TimeStampedModel):
    """Modèle de base commun (non scopé tenant)."""

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class TenantScopedModel(UUIDModel, TimeStampedModel):
    """
    Modèle rattaché à une filiale (tenant). Le champ `tenant` est
    renseigné automatiquement à la sauvegarde à partir du contexte courant.

    - `objects` : filtré sur le tenant courant (usage applicatif standard).
    - `all_tenants` : accès à toutes les données (admin, système, batchs).
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
        db_index=True,
        verbose_name="filiale",
    )

    objects = TenantManager()
    all_tenants = AllTenantsManager()

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        # Affecte automatiquement le tenant courant si absent.
        if self.tenant_id is None:
            current = get_current_tenant_id()
            if current is not None:
                self.tenant_id = current
        super().save(*args, **kwargs)


class ReferenceModel(TenantScopedModel):
    """
    Base pour les référentiels paramétrables par filiale
    (produits, catégories, motifs, etc.).
    """

    code = models.CharField("code", max_length=50)
    label = models.CharField("libellé", max_length=255)
    description = models.TextField("description", blank=True)
    is_active = models.BooleanField("actif", default=True)

    class Meta:
        abstract = True
        ordering = ["label"]

    def __str__(self):
        return f"{self.code} — {self.label}"
