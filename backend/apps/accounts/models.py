"""
Utilisateurs, rôles et délégations de pouvoirs.

RBAC : on s'appuie sur les groupes et permissions natifs de Django
(un « rôle » = un `Group`). Les délégations permettent de transférer
temporairement les pouvoirs d'un valideur à un autre.
"""
import uuid

from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.db import models
from django.utils import timezone

from .capabilities import CAPABILITY_PERMISSIONS


class DataScope(models.TextChoices):
    OWN = "OWN", "Ses propres dossiers"
    AGENCY = "AGENCY", "Son agence"
    TENANT = "TENANT", "Toute la filiale"


class UserManager(DjangoUserManager):
    """Superuser CLI = administrateur Groupe (is_group_level=True)."""

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_group_level", True)
        extra_fields.setdefault("tenant", None)
        extra_fields.setdefault("agency", None)
        return super().create_superuser(
            username, email=email, password=password, **extra_fields
        )


class User(AbstractUser):
    """Utilisateur rattaché à une filiale, ou de niveau Groupe."""

    objects = UserManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
        verbose_name="filiale",
        help_text="Vide pour un utilisateur de niveau Groupe.",
    )
    agency = models.ForeignKey(
        "tenants.Agency",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="primary_users",
        verbose_name="agence principale",
        help_text="Agence par défaut pour la création des dossiers.",
    )
    agencies = models.ManyToManyField(
        "tenants.Agency",
        blank=True,
        related_name="members",
        verbose_name="agences",
        help_text="Agences auxquelles l'utilisateur a accès.",
    )
    data_scope = models.CharField(
        "périmètre de données",
        max_length=10,
        choices=DataScope.choices,
        default=DataScope.AGENCY,
    )
    is_group_level = models.BooleanField(
        "utilisateur Groupe",
        default=False,
        help_text="Accès transverse de consolidation Groupe.",
    )
    employee_id = models.CharField("matricule", max_length=50, blank=True)
    cbs_id = models.CharField(
        "identifiant CBS (idGestionnaire)",
        max_length=64,
        blank=True,
        help_text="Identifiant Perfect / CBS du gestionnaire (optionnel).",
    )
    phone = models.CharField("téléphone", max_length=50, blank=True)
    mfa_enabled = models.BooleanField("MFA activé", default=False)
    mfa_secret = models.CharField(
        "secret TOTP",
        max_length=64,
        blank=True,
        help_text="Secret base32 pour l'authentification TOTP (vide si MFA inactif).",
    )
    must_change_password = models.BooleanField(
        "doit changer le mot de passe",
        default=False,
        help_text=(
            "Si vrai, l'utilisateur doit définir un nouveau mot de passe "
            "après connexion (création ou régénération admin)."
        ),
    )

    class Meta:
        verbose_name = "utilisateur"
        verbose_name_plural = "utilisateurs"
        permissions = CAPABILITY_PERMISSIONS

    def __str__(self):
        return self.get_full_name() or self.username

    def clean(self):
        from django.core.exceptions import ValidationError

        if not self.is_group_level and self.tenant_id is None:
            raise ValidationError(
                "Un utilisateur filiale doit être rattaché à une filiale."
            )
        if self.is_group_level and self.tenant_id is not None:
            raise ValidationError(
                "Un utilisateur Groupe ne doit pas être rattaché à une filiale."
            )
        # Admin filiale (périmètre TENANT) : agence optionnelle.
        if (
            not self.is_group_level
            and self.agency_id is None
            and self.data_scope != DataScope.TENANT
        ):
            raise ValidationError(
                "Un utilisateur filiale doit être rattaché à une agence."
            )
        if self.agency_id and self.tenant_id:
            if self.agency.tenant_id != self.tenant_id:
                raise ValidationError(
                    "L'agence principale doit appartenir à la filiale de l'utilisateur."
                )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.agency_id and not self.agencies.filter(pk=self.agency_id).exists():
            self.agencies.add(self.agency)


class Delegation(models.Model):
    """Délégation temporaire de pouvoirs entre deux utilisateurs."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    delegator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="delegations_given",
        verbose_name="délégant",
    )
    delegate = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="delegations_received",
        verbose_name="délégataire",
    )
    reason = models.CharField("motif", max_length=255, blank=True)
    max_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    approval_required = models.BooleanField(default=False)
    product = models.ForeignKey("catalog.CreditProduct", null=True, blank=True, on_delete=models.PROTECT)
    agency = models.ForeignKey("tenants.Agency", null=True, blank=True, on_delete=models.PROTECT)
    step_kind = models.CharField(max_length=20, blank=True, choices=[("CONSULTATIVE", "Consultative"), ("DECISIONAL", "Décisionnelle")])
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="approved_delegations")
    approved_at = models.DateTimeField(null=True, blank=True)
    start_date = models.DateField("début")
    end_date = models.DateField("fin")
    is_active = models.BooleanField("active", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "délégation de pouvoirs"
        verbose_name_plural = "délégations de pouvoirs"
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.delegator} → {self.delegate}"

    @property
    def is_currently_valid(self):
        today = timezone.now().date()
        return self.is_active and self.start_date <= today <= self.end_date and (not self.approval_required or self.approved_by_id is not None)


class TenantRole(models.Model):
    """Rôle métier rattaché à une filiale (lié à un Group Django technique)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="roles",
        verbose_name="filiale",
    )
    name = models.CharField("nom du rôle", max_length=150)
    pack_code = models.CharField("code du profil standard", max_length=50, blank=True, editable=False)
    group = models.OneToOneField(
        "auth.Group",
        on_delete=models.CASCADE,
        related_name="tenant_role",
        verbose_name="groupe Django",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "rôle filiale"
        verbose_name_plural = "rôles filiale"
        ordering = ["tenant", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "name"],
                name="unique_role_name_per_tenant",
            ),
            models.UniqueConstraint(fields=["tenant", "pack_code"], condition=~models.Q(pack_code=""), name="unique_role_pack_per_tenant"),
        ]

    def __str__(self):
        return f"{self.tenant.code} — {self.name}"
