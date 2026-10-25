"""Catalogue des produits de crédit et référentiels paramétrables."""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.common.models import ReferenceModel, TenantScopedModel


class ProductCategory(ReferenceModel):
    """Famille de produits de crédit (ex. Immobilier, Trésorerie, Conso)."""

    class Meta(ReferenceModel.Meta):
        verbose_name = "famille de produits"
        verbose_name_plural = "familles de produits"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"], name="unique_productcategory_code_per_tenant"
            )
        ]


class CreditProduct(ReferenceModel):
    """Produit de crédit proposé par une filiale."""

    class ClientType(models.TextChoices):
        INDIVIDUAL = "INDIVIDUAL", "Particulier"
        PROFESSIONAL = "PROFESSIONAL", "Groupement"
        CORPORATE = "CORPORATE", "Entreprise"
        ALL = "ALL", "Tous"

    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name="famille",
    )
    client_type = models.CharField(
        max_length=20, choices=ClientType.choices, default=ClientType.ALL
    )
    currency = models.CharField("devise", max_length=3, default="XOF")

    amount_min = models.DecimalField(
        "montant minimum", max_digits=18, decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    amount_max = models.DecimalField(
        "montant maximum", max_digits=18, decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    duration_min_months = models.PositiveIntegerField("durée min (mois)", default=1)
    duration_max_months = models.PositiveIntegerField("durée max (mois)", default=60)

    interest_rate = models.DecimalField(
        "taux d'intérêt annuel (%)", max_digits=6, decimal_places=3, default=0
    )
    processing_fee_rate = models.DecimalField(
        "frais de dossier (%)", max_digits=6, decimal_places=3, default=0
    )
    requires_guarantee = models.BooleanField("garantie obligatoire", default=False)
    cbs_product_code = models.CharField(
        "code produit crédit CBS (idProduitCrd)",
        max_length=64,
        blank=True,
        help_text="Identifiant Perfect / CBS du produit de crédit.",
    )
    cbs_repayment_product_code = models.CharField(
        "code produit remboursement CBS (idProduitRemb)",
        max_length=64,
        blank=True,
        help_text="Identifiant Perfect / CBS du produit de remboursement "
        "(ex. compte courant).",
    )
    cbs_credit_product = models.ForeignKey(
        "catalog.CbsProductReference", on_delete=models.PROTECT,
        null=True, blank=True, related_name="credit_product_mappings",
        verbose_name="produit crédit CBS confirmé",
    )
    cbs_repayment_product = models.ForeignKey(
        "catalog.CbsProductReference", on_delete=models.PROTECT,
        null=True, blank=True, related_name="repayment_product_mappings",
        verbose_name="produit de remboursement CBS confirmé",
    )

    class Meta(ReferenceModel.Meta):
        verbose_name = "produit de crédit"
        verbose_name_plural = "produits de crédit"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"], name="unique_creditproduct_code_per_tenant"
            )
        ]


class RejectReason(ReferenceModel):
    """Motif de rejet paramétrable (référentiel commun pour consolidation)."""

    class Meta(ReferenceModel.Meta):
        verbose_name = "motif de rejet"
        verbose_name_plural = "motifs de rejet"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"], name="unique_rejectreason_code_per_tenant"
            )
        ]


class CbsMappedReference(ReferenceModel):
    """Référentiel filiale avec code métier + identifiant CBS Perfect."""

    cbs_code = models.CharField(
        "identifiant CBS",
        max_length=64,
        blank=True,
        help_text="Code Perfect / CBS envoyé lors des appels d'intégration.",
    )
    sort_order = models.PositiveIntegerField("ordre d'affichage", default=0)

    class Meta(ReferenceModel.Meta):
        abstract = True
        ordering = ["sort_order", "label"]


class LoanPeriodicity(CbsMappedReference):
    """Périodicité de remboursement (ex. MONTHLY → MENSUEL)."""

    periods_per_year = models.PositiveIntegerField(
        "périodes / an",
        default=12,
        help_text="Utilisé pour calculer le nombre d'échéances.",
    )

    class Meta(CbsMappedReference.Meta):
        verbose_name = "périodicité"
        verbose_name_plural = "périodicités"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"],
                name="unique_loanperiodicity_code_per_tenant",
            )
        ]


class RepaymentMethod(CbsMappedReference):
    """Mécanisme d'amortissement ; cbs_code est transmis comme idProduitRemb."""

    class Meta(CbsMappedReference.Meta):
        verbose_name = "méthode de remboursement"
        verbose_name_plural = "méthodes de remboursement"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"],
                name="unique_repaymentmethod_code_per_tenant",
            )
        ]


class Currency(CbsMappedReference):
    """Devise paramétrable (code ISO + identifiant CBS / codeDevise)."""

    class Meta(CbsMappedReference.Meta):
        verbose_name = "devise"
        verbose_name_plural = "devises"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"],
                name="unique_currency_code_per_tenant",
            )
        ]


class FinancingObject(CbsMappedReference):
    """Objet de financement Perfect (idObjetFinancement).

    ``code`` = code Vision (ex. CONSO), ``cbs_code`` = id Vision (ex. \"30\").
    ``purpose_type`` optionnel : lien vers l'enum FinFlow ``PurposeType``.
    """

    purpose_type = models.CharField(
        "type d'objet FinFlow",
        max_length=32,
        blank=True,
        help_text="Code PurposeType (CONSUMPTION, REAL_ESTATE…) pour le mapping mise en place.",
    )

    class Meta(CbsMappedReference.Meta):
        verbose_name = "objet de financement"
        verbose_name_plural = "objets de financement"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"],
                name="unique_financingobject_code_per_tenant",
            )
        ]


class ServicePoint(CbsMappedReference):
    """Point de service Perfect (idPointService) — source CBS uniquement."""

    class Meta(CbsMappedReference.Meta):
        verbose_name = "point de service CBS"
        verbose_name_plural = "points de service CBS"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"],
                name="unique_servicepoint_code_per_tenant",
            )
        ]


class CbsManager(CbsMappedReference):
    """Gestionnaire Perfect (idGestionnaire) — source CBS uniquement.

    Associé à un utilisateur FinFlow via ``User.cbs_id`` (= ``cbs_code``).
    """

    class Meta(CbsMappedReference.Meta):
        verbose_name = "gestionnaire CBS"
        verbose_name_plural = "gestionnaires CBS"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"],
                name="unique_cbsmanager_code_per_tenant",
            )
        ]


class CbsProductReference(TenantScopedModel):
    """Identifiant produit documenté pour un connecteur, confirmé par un admin.

    La confirmation est documentaire tant que le CBS n'expose pas de catalogue
    produit connu ; elle ne prétend pas effectuer une vérification distante.
    """

    class Kind(models.TextChoices):
        CREDIT = "CREDIT", "Produit de crédit"
        REPAYMENT = "REPAYMENT", "Produit de remboursement"

    class VerificationStatus(models.TextChoices):
        PENDING = "PENDING", "À confirmer"
        VERIFIED = "VERIFIED", "Confirmé sur justificatif"

    connector = models.ForeignKey("corebanking.CoreBankingConnector", on_delete=models.PROTECT)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    cbs_code = models.CharField("identifiant produit CBS", max_length=64)
    label = models.CharField("libellé", max_length=255)
    currency = models.CharField("devise locale (facultative)", max_length=8, blank=True)
    source_reference = models.TextField("référence documentaire ou preuve CBS", max_length=2000)
    is_active = models.BooleanField(default=True)
    verification_status = models.CharField(
        max_length=16, choices=VerificationStatus.choices, default=VerificationStatus.PENDING,
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["kind", "label", "cbs_code"]
        verbose_name = "référence produit CBS"
        constraints = [models.UniqueConstraint(
            fields=["tenant", "connector", "kind", "cbs_code"], name="unique_cbs_product_reference",
        )]

    def __str__(self):
        return f"{self.label} ({self.cbs_code})"


class FinancingSource(CbsMappedReference):
    """Source de financement Perfect (ref/source-fin-list) — source CBS uniquement."""

    class Meta(CbsMappedReference.Meta):
        verbose_name = "source de financement CBS"
        verbose_name_plural = "sources de financement CBS"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"],
                name="unique_financingsource_code_per_tenant",
            )
        ]


class DecisionMotif(CbsMappedReference):
    """Motif de décision Perfect (ref/motif-decision-list) — source CBS uniquement."""

    class Meta(CbsMappedReference.Meta):
        verbose_name = "motif de décision CBS"
        verbose_name_plural = "motifs de décision CBS"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"],
                name="unique_decisionmotif_code_per_tenant",
            )
        ]


class CbsProfession(CbsMappedReference):
    """Profession Perfect (ref/profession-list) — source CBS uniquement.

    Associée au client via ``Client.cbs_profession_id`` (= ``cbs_code``).
    """

    class Meta(CbsMappedReference.Meta):
        verbose_name = "profession CBS"
        verbose_name_plural = "professions CBS"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"],
                name="unique_cbsprofession_code_per_tenant",
            )
        ]


class ChecklistItem(TenantScopedModel):
    """Pièce attendue d'une check-list documentaire, liée à un produit."""

    product = models.ForeignKey(
        CreditProduct,
        on_delete=models.CASCADE,
        related_name="checklist_items",
        verbose_name="produit",
    )
    label = models.CharField("libellé", max_length=255)
    is_mandatory = models.BooleanField("obligatoire", default=True)
    order = models.PositiveIntegerField("ordre", default=0)

    class Meta:
        verbose_name = "pièce de check-list"
        verbose_name_plural = "check-list documentaire"
        ordering = ["order", "label"]

    def __str__(self):
        return self.label
