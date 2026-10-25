"""
Moteur de workflow paramétrable.

Un `WorkflowDefinition` décrit un circuit d'approbation composé
d'`ApprovalStep` ordonnées, chacune conditionnée par des seuils (montant,
niveau de risque). Un `WorkflowInstance` matérialise l'exécution du
circuit pour un objet cible (ex. un dossier de crédit), via une relation
générique afin de rester découplé des modules métier.
"""
from django.contrib.auth.models import Group
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.common.models import AuthoredModel, TenantScopedModel


def default_working_days():
    return [0, 1, 2, 3, 4]


class BusinessCalendar(TenantScopedModel, AuthoredModel):
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    timezone = models.CharField(max_length=64, default="UTC")
    working_days = models.JSONField(default=default_working_days)
    opening_time = models.TimeField(default="08:00")
    closing_time = models.TimeField(default="17:00")
    holidays = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        constraints = [models.UniqueConstraint(fields=["tenant", "code"], name="unique_calendar_code_per_tenant")]

    def __str__(self):
        return self.name


class WorkflowDefinition(TenantScopedModel):
    """Circuit d'approbation paramétrable et versionné."""

    class TargetType(models.TextChoices):
        CREDIT = "CREDIT", "Dossier de crédit"
        MAIN_LEVEE = "MAIN_LEVEE", "Main levée"
        DATION = "DATION", "Dation en paiement"
        FORMALISATION = "FORMALISATION", "Formalisation de garantie"

    code = models.CharField("code", max_length=50)
    name = models.CharField("nom", max_length=255)
    target_type = models.CharField(
        max_length=20, choices=TargetType.choices, default=TargetType.CREDIT
    )
    version = models.PositiveIntegerField("version", default=1)
    is_active = models.BooleanField("actif", default=True)
    execution_mode = models.CharField(
        max_length=20, default="EXPLICIT_MODE",
        choices=[("LEGACY_ORDER", "Historique : même ordre en parallèle"), ("EXPLICIT_MODE", "Modes explicites")],
    )
    business_calendar = models.ForeignKey(
        BusinessCalendar, on_delete=models.PROTECT, null=True, blank=True,
        related_name="workflow_definitions",
    )

    # Critères de sélection du circuit (optionnels, combinables).
    # - montant seul, produit/famille seul, ou les deux
    # - null = pas de filtre sur ce critère
    min_amount = models.DecimalField(
        "montant plancher (circuit)",
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Inclusif. Vide = pas de plancher.",
    )
    max_amount = models.DecimalField(
        "montant plafond (circuit)",
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Inclusif. Vide = pas de plafond.",
    )
    product = models.ForeignKey(
        "catalog.CreditProduct",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="workflow_definitions",
        verbose_name="produit de crédit",
        help_text="Circuit réservé à ce produit. Vide = tous les produits "
        "(sauf filtre famille).",
    )
    product_category = models.ForeignKey(
        "catalog.ProductCategory",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="workflow_definitions",
        verbose_name="famille de produits",
        help_text="Circuit réservé à cette famille (ex. immobilier). "
        "Ignoré si un produit précis est renseigné.",
    )

    class Meta:
        verbose_name = "circuit d'approbation"
        verbose_name_plural = "circuits d'approbation"
        ordering = ["code", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code", "version"],
                name="unique_workflow_code_version_per_tenant",
            )
        ]

    def __str__(self):
        return f"{self.code} v{self.version}"

    def matches_amount(self, amount) -> bool:
        """True si le montant entre dans la tranche du circuit (bornes inclusives)."""
        if amount is None:
            amount = 0
        if self.min_amount is not None and amount < self.min_amount:
            return False
        if self.max_amount is not None and amount > self.max_amount:
            return False
        return True

    def matches_product(self, product) -> bool:
        """True si le produit du dossier satisfait les filtres produit/famille."""
        if self.product_id is None and self.product_category_id is None:
            return True
        if product is None:
            return False
        if self.product_id is not None:
            return str(product.pk) == str(self.product_id)
        category_id = getattr(product, "category_id", None)
        return (
            category_id is not None
            and str(category_id) == str(self.product_category_id)
        )

    def matches(self, amount, product=None) -> bool:
        return self.matches_amount(amount) and self.matches_product(product)

    def specificity_score(self) -> int:
        """Plus le score est élevé, plus le circuit est ciblé (prioritaire)."""
        score = 0
        if self.min_amount is not None or self.max_amount is not None:
            score += 2
        if self.product_id is not None:
            score += 2
        elif self.product_category_id is not None:
            score += 1
        return score


class ApprovalStep(TenantScopedModel):
    """Étape d'un circuit d'approbation."""

    class StepKind(models.TextChoices):
        CONSULTATIVE = "CONSULTATIVE", "Consultative"
        DECISIONAL = "DECISIONAL", "Décisionnelle"

    class Mode(models.TextChoices):
        SEQUENTIAL = "SEQUENTIAL", "Séquentielle"
        PARALLEL = "PARALLEL", "Parallèle"

    definition = models.ForeignKey(
        WorkflowDefinition,
        on_delete=models.CASCADE,
        related_name="steps",
        verbose_name="circuit",
    )
    name = models.CharField("nom de l'étape", max_length=255)
    order = models.PositiveIntegerField("ordre", default=1)
    required_group = models.ForeignKey(
        Group,
        on_delete=models.PROTECT,
        related_name="approval_steps",
        verbose_name="rôle habilité",
    )
    mode = models.CharField(max_length=20, choices=Mode.choices, default=Mode.SEQUENTIAL)
    step_kind = models.CharField(
        "nature de l'étape",
        max_length=20,
        choices=StepKind.choices,
        default=StepKind.CONSULTATIVE,
    )

    # Conditions d'application (seuils)
    min_amount = models.DecimalField(
        "montant plancher", max_digits=18, decimal_places=2, null=True, blank=True
    )
    max_amount = models.DecimalField(
        "montant plafond", max_digits=18, decimal_places=2, null=True, blank=True
    )
    min_risk_level = models.PositiveIntegerField(
        "niveau de risque minimal", null=True, blank=True
    )

    sla_hours = models.PositiveIntegerField("SLA (heures)", default=48)
    allow_return = models.BooleanField("autorise le retour", default=True)
    committee_quorum = models.PositiveIntegerField(default=1)
    sla_mode = models.CharField(max_length=10, default="CALENDAR", choices=[("CALENDAR", "Heures continues"), ("BUSINESS", "Heures ouvrées")])
    committee_enabled = models.BooleanField(default=False)
    committee_majority = models.CharField(max_length=12, default="SIMPLE", choices=[("SIMPLE", "Majorité stricte"), ("QUALIFIED", "Majorité qualifiée"), ("UNANIMOUS", "Unanimité")])
    committee_majority_numerator = models.PositiveIntegerField(default=2)
    committee_majority_denominator = models.PositiveIntegerField(default=3)
    committee_abstentions = models.CharField(max_length=10, default="INCLUDE", choices=[("INCLUDE", "Incluses"), ("EXCLUDE", "Exclues")])
    committee_record_required = models.BooleanField(default=False)
    committee_pv_required = models.BooleanField(default=True)

    class Meta:
        verbose_name = "étape d'approbation"
        verbose_name_plural = "étapes d'approbation"
        ordering = ["definition", "order"]

    def __str__(self):
        return f"{self.order}. {self.name}"

    def applies_to(self, amount, risk_level):
        """Indique si l'étape s'applique compte tenu des seuils."""
        if self.min_amount is not None and amount < self.min_amount:
            return False
        if self.max_amount is not None and amount > self.max_amount:
            return False
        if self.min_risk_level is not None and (risk_level or 0) < self.min_risk_level:
            return False
        return True


class WorkflowInstance(TenantScopedModel):
    """Exécution d'un circuit pour un objet cible."""

    class Status(models.TextChoices):
        IN_PROGRESS = "IN_PROGRESS", "En cours"
        AWAITING_CONDITIONS = "AWAITING_CONDITIONS", "En attente de levée des réserves"
        APPROVED = "APPROVED", "Approuvé"
        REJECTED = "REJECTED", "Rejeté"
        RETURNED = "RETURNED", "Retourné pour correction"
        CANCELLED = "CANCELLED", "Annulé"

    definition = models.ForeignKey(
        WorkflowDefinition,
        on_delete=models.PROTECT,
        related_name="instances",
        verbose_name="circuit",
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    target = GenericForeignKey("content_type", "object_id")

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.IN_PROGRESS
    )
    current_order = models.PositiveIntegerField("étape courante", default=0)
    amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    risk_level = models.PositiveIntegerField(null=True, blank=True)
    calendar_snapshot = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "instance de workflow"
        verbose_name_plural = "instances de workflow"
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self):
        return f"{self.definition} — {self.get_status_display()}"


class ApprovalTask(TenantScopedModel):
    """Tâche d'approbation confiée à un rôle pour une étape donnée."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        APPROVED = "APPROVED", "Approuvée"
        REJECTED = "REJECTED", "Rejetée"
        RETURNED = "RETURNED", "Retournée"
        SKIPPED = "SKIPPED", "Ignorée"

    class Opinion(models.TextChoices):
        FAVORABLE = "FAVORABLE", "Favorable"
        FAVORABLE_SOUS_RESERVE = "FAVORABLE_SOUS_RESERVE", "Favorable sous réserve"
        DEFAVORABLE = "DEFAVORABLE", "Défavorable"

    instance = models.ForeignKey(
        WorkflowInstance,
        on_delete=models.CASCADE,
        related_name="tasks",
        verbose_name="instance",
    )
    step = models.ForeignKey(
        ApprovalStep,
        on_delete=models.PROTECT,
        related_name="tasks",
        verbose_name="étape",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    opinion = models.CharField(
        "avis du validateur", max_length=25, choices=Opinion.choices, blank=True
    )
    decision_comment = models.TextField("commentaire de décision", blank=True)
    decision_snapshot = models.JSONField(default=dict, blank=True)
    committee_record = models.JSONField(default=dict, blank=True)
    proposed_amount = models.DecimalField(
        "montant proposé à cette étape", max_digits=18, decimal_places=2,
        null=True, blank=True,
    )
    reject_reason = models.ForeignKey(
        "catalog.RejectReason",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approval_tasks",
    )
    acted_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approval_tasks",
    )
    acted_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField("échéance SLA", null=True, blank=True)

    class Meta:
        verbose_name = "tâche d'approbation"
        verbose_name_plural = "tâches d'approbation"
        ordering = ["step__order", "created_at"]

    def __str__(self):
        return f"{self.step} — {self.get_status_display()}"


class ApprovalCondition(TenantScopedModel):
    """Réserve émise lors d'un avis favorable sous réserve.

    Cycle de vie : PENDING → LIFTED (par le chargé de dossier) → VALIDATED
    (par l'émetteur de la réserve). Tant qu'une réserve n'est pas validée,
    le dossier reste en cours de validation.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente de levée"
        LIFTED = "LIFTED", "Levée — en attente de validation"
        VALIDATED = "VALIDATED", "Validée"

    application = models.ForeignKey(
        "credits.CreditApplication",
        on_delete=models.CASCADE,
        related_name="approval_conditions",
        verbose_name="dossier",
    )
    task = models.ForeignKey(
        ApprovalTask,
        on_delete=models.CASCADE,
        related_name="conditions",
        verbose_name="tâche d'origine",
    )
    description = models.TextField("description de la réserve")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    issued_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="issued_conditions",
        verbose_name="émis par",
    )
    issued_at = models.DateTimeField("émis le", auto_now_add=True)
    lifted_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lifted_conditions",
        verbose_name="levée par",
    )
    lifted_at = models.DateTimeField("levée le", null=True, blank=True)
    lift_comment = models.TextField("commentaire de levée", blank=True)
    validated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="validated_conditions",
        verbose_name="validée par",
    )
    validated_at = models.DateTimeField("validée le", null=True, blank=True)
    validation_comment = models.TextField("commentaire de validation", blank=True)

    class Meta:
        verbose_name = "réserve d'approbation"
        verbose_name_plural = "réserves d'approbation"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.description[:60]} — {self.get_status_display()}"
