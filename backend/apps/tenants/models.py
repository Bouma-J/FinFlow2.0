"""
Modèles d'organisation : filiales (tenants) et agences.
"""
from django.db import models
from django.core.validators import RegexValidator

from apps.common.files import safe_filename
from apps.common.models import BaseModel

HEX_COLOR = RegexValidator(r"\A#[0-9a-fA-F]{6}\Z", "Indiquez une couleur hexadécimale au format #RRGGBB.")


def tenant_logo_upload(instance, filename):
    return f"tenants/{instance.id}/logo/{safe_filename(filename)}"


class Tenant(BaseModel):
    """Une filiale du Groupe (unité d'isolation des données)."""

    code = models.CharField("code filiale", max_length=20, unique=True)
    name = models.CharField("raison sociale", max_length=255)
    country = models.CharField("pays", max_length=100)
    zone = models.CharField(
        "zone / région Groupe",
        max_length=100,
        blank=True,
        help_text="Axe de consolidation Groupe (ex. UEMOA, CEMAC).",
    )
    currency = models.CharField("devise locale", max_length=3, default="XOF")
    timezone = models.CharField("fuseau horaire", max_length=64, default="UTC")
    is_active = models.BooleanField("filiale active", default=True)

    # Coordonnées
    address = models.CharField("adresse", max_length=255, blank=True)
    phone = models.CharField("téléphone", max_length=50, blank=True)
    email = models.EmailField("email", blank=True)

    # Charte graphique (personnalisation de l'interface)
    logo = models.ImageField(
        "logo", upload_to=tenant_logo_upload, max_length=255, blank=True
    )
    brand_primary = models.CharField(
        "couleur principale", max_length=7, default="#0f9488",
        validators=[HEX_COLOR],
        help_text="Couleur principale (hex, ex. #0f9488).",
    )
    brand_secondary = models.CharField(
        "couleur secondaire", max_length=7, default="#0d7a72",
        validators=[HEX_COLOR],
        help_text="Couleur secondaire / foncée (hex).",
    )
    brand_accent = models.CharField(
        "couleur d'accent", max_length=7, default="#d4a017",
        validators=[HEX_COLOR],
        help_text="Couleur d'accent (hex).",
    )
    brand_sidebar = models.CharField(
        "couleur barre latérale", max_length=7, default="#084f4a", validators=[HEX_COLOR],
        help_text="Couleur de fond du menu latéral (hex).",
    )
    brand_sidebar_text = models.CharField(
        "couleur texte de la barre", max_length=7, default="#ffffff", validators=[HEX_COLOR],
        help_text="Couleur des textes et icônes du menu latéral (hex).",
    )

    # Quotas GED (long terme — volume documentaire)
    ged_quota_bytes = models.PositiveBigIntegerField(
        "quota GED (octets)",
        default=10 * 1024 * 1024 * 1024,
        help_text="Plafond de stockage documentaire pour la filiale (défaut 10 Go).",
    )
    ged_used_bytes = models.PositiveBigIntegerField(
        "GED utilisé (octets)",
        default=0,
        help_text="Compteur maintenu à l'upload / suppression de documents.",
    )

    class Meta:
        verbose_name = "filiale"
        verbose_name_plural = "filiales"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name}"


class Agency(BaseModel):
    """Agence rattachée à une filiale (axe organisationnel)."""

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="agencies",
        verbose_name="filiale",
    )
    code = models.CharField("code agence", max_length=20)
    name = models.CharField("nom", max_length=255)
    region = models.CharField("région", max_length=100, blank=True)
    address = models.CharField("adresse", max_length=255, blank=True)
    is_active = models.BooleanField("active", default=True)

    # Chef d'agence
    manager_last_name = models.CharField(
        "nom du chef d'agence", max_length=100, blank=True
    )
    manager_first_name = models.CharField(
        "prénom du chef d'agence", max_length=100, blank=True
    )
    manager_phone = models.CharField(
        "téléphone du chef d'agence", max_length=50, blank=True
    )
    cbs_point_of_service_id = models.CharField(
        "identifiant point de service CBS (idPointService)",
        max_length=64,
        blank=True,
        help_text="Code Perfect / CBS du point de service de l'agence.",
    )

    class Meta:
        verbose_name = "agence"
        verbose_name_plural = "agences"
        ordering = ["tenant", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"], name="unique_agency_code_per_tenant"
            )
        ]

    def __str__(self):
        return f"{self.code} — {self.name}"

    @property
    def manager_display_name(self):
        return f"{self.manager_first_name} {self.manager_last_name}".strip()


class TenantOfficer(BaseModel):
    """Responsable d'une filiale (DG, Directeur d'exploitation, etc.)."""

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="officers",
        verbose_name="filiale",
    )
    title = models.CharField("intitulé du poste", max_length=150)
    last_name = models.CharField("nom", max_length=100)
    first_name = models.CharField("prénom", max_length=100, blank=True)
    phone = models.CharField("téléphone", max_length=50, blank=True)
    ordering = models.PositiveSmallIntegerField("ordre", default=0)

    class Meta:
        verbose_name = "responsable de filiale"
        verbose_name_plural = "responsables de filiale"
        ordering = ["ordering", "created_at"]

    def __str__(self):
        return f"{self.title} — {self.first_name} {self.last_name}".strip()

    @property
    def display_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.last_name
