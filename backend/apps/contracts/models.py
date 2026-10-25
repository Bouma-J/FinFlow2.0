"""Modèles de contrats paramétrables par filiale et contrats générés.

Chaque filiale (tenant) gère librement son propre catalogue de modèles
(`ContractTemplate`) : elle ajoute, retire ou désactive les contrats selon
sa réalité. La mise en forme des documents est préservée : on n'injecte que
les données du dossier dans le modèle Word/Excel d'origine (voir
``rendering.py``).
"""
from django.db import models

from apps.common.files import safe_filename
from apps.common.models import AuthoredModel, TenantScopedModel


def _tenant_segment(instance) -> str:
    """Identifiant filiale pour le chemin S3 (jamais la chaîne littérale « None »)."""
    tenant_id = getattr(instance, "tenant_id", None)
    if tenant_id:
        return str(tenant_id)
    application = getattr(instance, "application", None)
    if application is not None and getattr(application, "tenant_id", None):
        return str(application.tenant_id)
    template = getattr(instance, "template", None)
    if template is not None and getattr(template, "tenant_id", None):
        return str(template.tenant_id)
    return "unscoped"


def template_file_path(instance, filename):
    """Chemin de stockage d'un modèle de contrat (par filiale)."""
    return (
        f"contracts/{_tenant_segment(instance)}/templates/"
        f"{safe_filename(filename)}"
    )


def generated_file_path(instance, filename):
    """Chemin de stockage d'un contrat généré (par filiale et dossier)."""
    return (
        f"contracts/{_tenant_segment(instance)}/generated/"
        f"{instance.application_id}/{safe_filename(filename)}"
    )


def signed_file_path(instance, filename):
    """Chemin de stockage du scan signé d'un contrat."""
    return (
        f"contracts/{_tenant_segment(instance)}/signed/"
        f"{instance.application_id}/{safe_filename(filename)}"
    )


class ContractCategory(models.TextChoices):
    """Suggestions de catégories (indicatives, non restrictives)."""

    NOTIFICATION = "NOTIFICATION", "Notification de crédit"
    LOAN = "LOAN", "Contrat de prêt"
    SURETY = "SURETY", "Cautionnement"
    PLEDGE_VEHICLE = "PLEDGE_VEHICLE", "Gage véhicule"
    PLEDGE_JEWELRY = "PLEDGE_JEWELRY", "Gage bijoux"
    PLEDGE_SHARES = "PLEDGE_SHARES", "Nantissement d'actions"
    SALARY_ASSIGNMENT = "SALARY_ASSIGNMENT", "Cession sur salaire"
    PROMISSORY_NOTE = "PROMISSORY_NOTE", "Billet à ordre"
    FIDUCIARY_TRANSFER = "FIDUCIARY_TRANSFER", "Transfert fiduciaire"
    OTHER = "OTHER", "Autre"


class ContractTemplate(TenantScopedModel, AuthoredModel):
    """Modèle de contrat d'une filiale, prêt à être rempli avec un dossier."""

    class Engine(models.TextChoices):
        DOCX = "DOCX", "Word (.docx)"
        XLSX = "XLSX", "Excel (.xlsx)"

    class AppliesTo(models.TextChoices):
        ANY = "ANY", "Tous les clients"
        INDIVIDUAL = "INDIVIDUAL", "Particuliers uniquement"
        CORPORATE = "CORPORATE", "Entreprises et groupements"

    code = models.CharField("code", max_length=40, blank=True)
    name = models.CharField("intitulé du contrat", max_length=200)
    category = models.CharField(
        "catégorie",
        max_length=30,
        choices=ContractCategory.choices,
        default=ContractCategory.OTHER,
        blank=True,
    )
    description = models.TextField("description", blank=True)
    engine = models.CharField(
        "moteur", max_length=10, choices=Engine.choices, default=Engine.DOCX
    )
    file = models.FileField(
        "modèle", upload_to=template_file_path, max_length=255
    )

    # --- Règles d'applicabilité (proposition automatique par dossier) ----- #
    applies_to = models.CharField(
        "s'applique à", max_length=15,
        choices=AppliesTo.choices, default=AppliesTo.ANY,
    )
    product = models.ForeignKey(
        "catalog.CreditProduct",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contract_templates",
        verbose_name="produit (optionnel)",
        help_text="Limiter ce modèle à un produit de crédit précis.",
    )
    amount_min = models.DecimalField(
        "montant minimum", max_digits=18, decimal_places=2, null=True, blank=True
    )
    amount_max = models.DecimalField(
        "montant maximum", max_digits=18, decimal_places=2, null=True, blank=True
    )

    # --- Variables saisies manuellement à la génération ------------------- #
    extra_fields = models.JSONField(
        "champs additionnels", default=list, blank=True,
        help_text=(
            "Liste [{key, label, type}] de variables saisies à la génération "
            "(ex. nom d'un témoin, mention spéciale)."
        ),
    )

    is_required = models.BooleanField(
        "obligatoire avant mise en place", default=False,
        help_text="Le dossier ne pourra être mis en place qu'une fois ce contrat généré.",
    )
    is_active = models.BooleanField("actif", default=True)
    ordering = models.PositiveIntegerField("ordre d'affichage", default=0)

    class Meta:
        verbose_name = "modèle de contrat"
        verbose_name_plural = "modèles de contrats"
        ordering = ["ordering", "name"]
        indexes = [
            models.Index(fields=["tenant", "is_active"]),
        ]

    def __str__(self):
        return self.name

    def applies_to_application(self, application) -> bool:
        """Indique si ce modèle est pertinent pour un dossier donné."""
        if not self.is_active:
            return False
        client = getattr(application, "client", None)
        is_legal_entity = bool(getattr(client, "is_legal_entity", False))
        if self.applies_to == self.AppliesTo.INDIVIDUAL and is_legal_entity:
            return False
        if self.applies_to == self.AppliesTo.CORPORATE and not is_legal_entity:
            return False
        if self.product_id and self.product_id != application.product_id:
            return False
        from apps.credits.amounts import reference_amount

        amount = reference_amount(application) or 0
        if self.amount_min is not None and amount < self.amount_min:
            return False
        if self.amount_max is not None and amount > self.amount_max:
            return False
        return True


class GeneratedContract(TenantScopedModel, AuthoredModel):
    """Contrat produit pour un dossier de crédit à partir d'un modèle."""

    class Status(models.TextChoices):
        GENERATED = "GENERATED", "Généré"
        SIGNED = "SIGNED", "Signé"
        CANCELLED = "CANCELLED", "Annulé"

    application = models.ForeignKey(
        "credits.CreditApplication",
        on_delete=models.CASCADE,
        related_name="generated_contracts",
        verbose_name="dossier",
    )
    surety_engagement = models.ForeignKey(
        "sureties.SuretyEngagement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_contracts",
        verbose_name="engagement de caution",
        help_text="Renseigné pour les contrats de cautionnement liés à une caution.",
    )
    template = models.ForeignKey(
        ContractTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_contracts",
        verbose_name="modèle",
    )
    template_name = models.CharField("intitulé", max_length=200)
    category = models.CharField("catégorie", max_length=30, blank=True)
    file = models.FileField(
        "document généré", upload_to=generated_file_path, max_length=255
    )
    context_snapshot = models.JSONField(
        "variables utilisées", default=dict, blank=True
    )
    extra_values = models.JSONField(
        "valeurs saisies manuellement", default=dict, blank=True
    )
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.GENERATED
    )
    signed_file = models.FileField(
        "scan signé", upload_to=signed_file_path, max_length=255, blank=True
    )
    signed_at = models.DateTimeField("signé le", null=True, blank=True)
    notes = models.TextField("observations", blank=True)

    class Meta:
        verbose_name = "contrat généré"
        verbose_name_plural = "contrats générés"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "application"]),
        ]

    def __str__(self):
        return f"{self.template_name} — {self.application_id}"
