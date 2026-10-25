"""Gestion électronique des documents (GED)."""
import hashlib

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.common.files import safe_filename
from apps.common.managers import SoftDeleteAllTenantsManager, SoftDeleteTenantManager
from apps.common.models import ReferenceModel, SoftDeleteModel, TenantScopedModel


def document_upload_path(instance, filename):
    return (
        f"documents/{instance.tenant_id}/{instance.category_id}/"
        f"{safe_filename(filename)}"
    )


class DocumentCategory(ReferenceModel):
    """Catégorie documentaire paramétrable (CNI, RCCM, états financiers…)."""

    tracks_expiry = models.BooleanField(
        "suivi d'expiration", default=False,
        help_text="Génère des alertes à l'approche de la date d'expiration.",
    )

    class Meta(ReferenceModel.Meta):
        verbose_name = "catégorie de document"
        verbose_name_plural = "catégories de documents"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"],
                name="unique_documentcategory_code_per_tenant",
            )
        ]


class Document(SoftDeleteModel, TenantScopedModel):
    """
    Document électronique rattaché à une entité métier (client, dossier,
    garantie…) via une relation générique. Versionné et contrôlé en intégrité.
    Suppression logique (rétention) via SoftDeleteModel.
    """

    objects = SoftDeleteTenantManager()
    all_tenants = SoftDeleteAllTenantsManager()
    # Accès y compris soft-deleted (purge, audit)
    including_deleted = models.Manager()

    category = models.ForeignKey(
        DocumentCategory,
        on_delete=models.PROTECT,
        related_name="documents",
        verbose_name="catégorie",
    )
    name = models.CharField("nom", max_length=255)
    file = models.FileField(
        "fichier", upload_to=document_upload_path, max_length=255
    )
    mime_type = models.CharField("type MIME", max_length=100, blank=True)
    size_bytes = models.PositiveBigIntegerField("taille (octets)", default=0)
    sha256 = models.CharField("empreinte SHA-256", max_length=64, blank=True)
    version = models.PositiveIntegerField("version", default=1)
    verification_status = models.CharField(max_length=12, default="PENDING", choices=[("PENDING", "À vérifier"), ("VERIFIED", "Vérifié"), ("REJECTED", "Rejeté")])
    verified_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="verified_documents")
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_comment = models.TextField(blank=True)

    issue_date = models.DateField("date d'émission", null=True, blank=True)
    expiry_date = models.DateField("date d'expiration", null=True, blank=True)

    # Rattachement générique à une entité métier
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True
    )
    object_id = models.UUIDField(null=True, blank=True)
    related_object = GenericForeignKey("content_type", "object_id")

    uploaded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_documents",
    )
    # Lien vers la pièce métier d'origine (ex. credits.CreditDocument:<uuid>)
    origin_key = models.CharField(
        "clé d'origine",
        max_length=120,
        blank=True,
        db_index=True,
        help_text="Identifiant stable du silo source pour dédoublonnage / purge.",
    )

    class Meta:
        verbose_name = "document"
        verbose_name_plural = "documents"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["tenant", "category"]),
        ]

    def __str__(self):
        return f"{self.name} (v{self.version})"

    def compute_hash(self):
        """Calcule l'empreinte SHA-256 et la taille du fichier."""
        if not self.file:
            return
        sha = hashlib.sha256()
        size = 0
        for chunk in self.file.chunks():
            sha.update(chunk)
            size += len(chunk)
        self.sha256 = sha.hexdigest()
        self.size_bytes = size
