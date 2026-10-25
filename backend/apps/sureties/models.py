"""Gestion des cautions (personnes physiques et morales)."""
from django.db import models

from apps.clients.models import IdDocumentType, LegalForm
from apps.common.files import safe_filename
from apps.common.models import AuthoredModel, TenantScopedModel


def surety_file_path(instance, filename):
    """Chemin de stockage des pièces jointes d'une caution (scan, photo)."""
    surety_id = getattr(instance, "surety_id", None) or instance.id
    return f"sureties/{instance.tenant_id}/{surety_id}/{safe_filename(filename)}"


class Surety(TenantScopedModel, AuthoredModel):
    """Caution : personne physique ou morale s'engageant pour un emprunteur."""

    agency = models.ForeignKey(
        "tenants.Agency",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sureties",
        verbose_name="agence",
    )

    class SuretyType(models.TextChoices):
        PHYSICAL = "PHYSICAL", "Personne physique"
        MORAL = "MORAL", "Personne morale"

    surety_type = models.CharField(
        max_length=20, choices=SuretyType.choices,
        default=SuretyType.PHYSICAL,
    )
    name = models.CharField("nom / raison sociale", max_length=255, blank=True)

    # ------------------------------------------------------------------ #
    # Identité (personne physique)
    # ------------------------------------------------------------------ #
    first_name = models.CharField("prénom", max_length=100, blank=True)
    last_name = models.CharField("nom", max_length=100, blank=True)
    birth_date = models.DateField("date de naissance", null=True, blank=True)
    birth_country = models.CharField("pays de naissance", max_length=100, blank=True)
    activity = models.CharField("activité de la caution", max_length=200, blank=True)
    estimated_income = models.DecimalField(
        "estimation de revenu", max_digits=18, decimal_places=2,
        null=True, blank=True,
    )

    # Pièce d'identité
    id_document_type = models.CharField(
        "type de pièce d'identité", max_length=20,
        choices=IdDocumentType.choices, blank=True,
    )
    national_id = models.CharField(
        "n° de la pièce d'identité", max_length=50, blank=True
    )
    id_document_issue_date = models.DateField(
        "date d'établissement de la pièce", null=True, blank=True
    )
    id_document_expiry_date = models.DateField(
        "date d'expiration de la pièce", null=True, blank=True
    )
    id_document_scan = models.FileField(
        "scan de la pièce d'identité", upload_to=surety_file_path,
        max_length=255, blank=True,
    )
    photo = models.ImageField(
        "photo", upload_to=surety_file_path, max_length=255, blank=True
    )

    # ------------------------------------------------------------------ #
    # Personne morale (entreprise)
    # ------------------------------------------------------------------ #
    company_name = models.CharField("raison sociale", max_length=255, blank=True)
    legal_form = models.CharField(
        "statut juridique", max_length=20, choices=LegalForm.choices, blank=True
    )
    ifu = models.CharField("numéro IFU", max_length=50, blank=True)
    rccm = models.CharField("numéro RCCM", max_length=50, blank=True)
    ifu_scan = models.FileField(
        "scan IFU", upload_to=surety_file_path, max_length=255, blank=True
    )
    rccm_scan = models.FileField(
        "scan RCCM", upload_to=surety_file_path, max_length=255, blank=True
    )
    city = models.CharField("ville", max_length=100, blank=True)

    # Gérant de l'entreprise de caution
    manager_last_name = models.CharField("nom du gérant", max_length=100, blank=True)
    manager_first_name = models.CharField(
        "prénom du gérant", max_length=100, blank=True
    )
    manager_phone = models.CharField(
        "téléphone du gérant", max_length=50, blank=True
    )
    manager_email = models.EmailField("email du gérant", blank=True)
    manager_address = models.CharField(
        "adresse du gérant", max_length=255, blank=True
    )
    manager_id_document_type = models.CharField(
        "type de pièce du gérant", max_length=20,
        choices=IdDocumentType.choices, blank=True,
    )
    manager_id_document_number = models.CharField(
        "n° de pièce du gérant", max_length=50, blank=True
    )
    manager_id_document_issue_date = models.DateField(
        "date d'établissement de la pièce du gérant", null=True, blank=True
    )
    manager_id_document_expiry_date = models.DateField(
        "date d'expiration de la pièce du gérant", null=True, blank=True
    )
    manager_id_document_scan = models.FileField(
        "scan pièce du gérant", upload_to=surety_file_path,
        max_length=255, blank=True,
    )
    manager_position = models.CharField(
        "poste du gérant dans l'entreprise", max_length=150, blank=True
    )
    manager_birth_date = models.DateField(
        "date de naissance du gérant", null=True, blank=True
    )
    manager_birth_country = models.CharField(
        "pays de naissance du gérant", max_length=100, blank=True
    )
    manager_birth_city = models.CharField(
        "ville de naissance du gérant", max_length=100, blank=True
    )

    # ------------------------------------------------------------------ #
    # Coordonnées
    # ------------------------------------------------------------------ #
    identifier = models.CharField(
        "pièce / RCCM (legacy)",
        max_length=100,
        blank=True,
        help_text="Conservé pour compatibilité ; préférer rccm pour les entreprises.",
    )
    phone = models.CharField("téléphone", max_length=50, blank=True)
    email = models.EmailField("email", blank=True)
    address = models.CharField("adresse", max_length=255, blank=True)

    commitment_ceiling = models.DecimalField(
        "plafond d'engagement", max_digits=18, decimal_places=2, default=0
    )
    is_active = models.BooleanField("active", default=True)

    class Meta:
        verbose_name = "caution"
        verbose_name_plural = "cautions"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "name"])]

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        if self.surety_type == self.SuretyType.MORAL:
            return (
                self.company_name
                or self.name
                or "(entreprise de caution sans nom)"
            )
        person = f"{self.first_name} {self.last_name}".strip()
        return self.name or person or "(caution sans nom)"

    def save(self, *args, **kwargs):
        # Synchroniser `name` pour l'affichage / la recherche.
        if self.surety_type == self.SuretyType.MORAL:
            if self.company_name:
                self.name = self.company_name
            if not self.rccm and self.identifier:
                self.rccm = self.identifier
            elif self.rccm and not self.identifier:
                self.identifier = self.rccm
        elif not self.name:
            person = f"{self.first_name} {self.last_name}".strip()
            if person:
                self.name = person
        super().save(*args, **kwargs)

    @property
    def total_committed(self):
        # ACTIVE + CALLED : l'appel en garantie garde l'exposition jusqu'à libération.
        agg = self.engagements.filter(
            status__in=[
                SuretyEngagement.Status.ACTIVE,
                SuretyEngagement.Status.CALLED,
            ]
        ).aggregate(models.Sum("amount"))
        return agg["amount__sum"] or 0

    @property
    def available_ceiling(self):
        return self.commitment_ceiling - self.total_committed


class SuretyDocument(TenantScopedModel):
    """Document libre associé à une caution (intitulé + scan)."""

    surety = models.ForeignKey(
        Surety,
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name="caution",
    )
    title = models.CharField("intitulé", max_length=200)
    file = models.FileField(
        "scan / fichier",
        upload_to=surety_file_path,
        max_length=255,
    )

    class Meta:
        verbose_name = "document de caution"
        verbose_name_plural = "documents de caution"
        ordering = ["created_at"]

    def __str__(self):
        return self.title or f"Document {self.pk}"


class SuretyEngagement(TenantScopedModel):
    """Engagement d'une caution sur un dossier de crédit."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Actif"
        RELEASED = "RELEASED", "Libéré"
        CALLED = "CALLED", "Appelé"

    class EngagementType(models.TextChoices):
        SIMPLE = "SIMPLE", "Caution simple"
        SOLIDAIRE = "SOLIDAIRE", "Caution solidaire"

    surety = models.ForeignKey(
        Surety,
        on_delete=models.CASCADE,
        related_name="engagements",
        verbose_name="caution",
    )
    application = models.ForeignKey(
        "credits.CreditApplication",
        on_delete=models.PROTECT,
        related_name="surety_engagements",
        verbose_name="dossier",
    )
    amount = models.DecimalField("montant engagé", max_digits=18, decimal_places=2)
    engagement_type = models.CharField(
        "type d'engagement",
        max_length=20,
        choices=EngagementType.choices,
        default=EngagementType.SOLIDAIRE,
        db_index=True,
    )
    signed_date = models.DateField("date de signature", null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    notes = models.TextField("observations", blank=True)
    released_at = models.DateTimeField("libéré le", null=True, blank=True)
    called_at = models.DateTimeField("appelé le", null=True, blank=True)

    class Meta:
        verbose_name = "engagement de caution"
        verbose_name_plural = "engagements de caution"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.surety} — {self.amount}"

    @property
    def active_contract(self):
        """Dernier contrat de cautionnement non annulé lié à cet engagement."""
        from apps.contracts.models import GeneratedContract

        return (
            self.generated_contracts.exclude(
                status=GeneratedContract.Status.CANCELLED
            )
            .order_by("-created_at")
            .first()
        )


class SuretyPhone(TenantScopedModel):
    """Numéro de téléphone additionnel d'une caution (multi-numéros)."""

    surety = models.ForeignKey(
        Surety,
        on_delete=models.CASCADE,
        related_name="phones",
        verbose_name="caution",
    )
    number = models.CharField("numéro", max_length=50)
    label = models.CharField("libellé", max_length=50, blank=True)

    class Meta:
        verbose_name = "téléphone caution"
        verbose_name_plural = "téléphones caution"
        ordering = ["created_at"]

    def __str__(self):
        return self.number
