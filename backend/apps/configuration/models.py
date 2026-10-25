"""Versions publiées des adaptations de la politique filiale."""
from django.conf import settings
from django.db import models

from apps.common.models import AuthoredModel, TenantScopedModel


class ConfigurationProfile(TenantScopedModel, AuthoredModel):
    # Une absence de filiale désigne un socle Groupe, jamais une donnée métier.
    tenant = models.ForeignKey("tenants.Tenant", null=True, blank=True, on_delete=models.CASCADE)
    locked_keys = models.JSONField(default=list, blank=True)
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Brouillon"
        REVIEW = "REVIEW", "À valider"
        PUBLISHED = "PUBLISHED", "Publié"
        RETIRED = "RETIRED", "Retiré"

    code = models.SlugField(max_length=60)
    name = models.CharField(max_length=180)
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    product = models.ForeignKey("catalog.CreditProduct", null=True, blank=True, on_delete=models.PROTECT)
    agency = models.ForeignKey("tenants.Agency", null=True, blank=True, on_delete=models.PROTECT)
    client_type = models.CharField(max_length=20, blank=True, choices=[
        ("", "Tous"), ("INDIVIDUAL", "Personne physique"),
        ("CORPORATE", "Personne morale"), ("PROFESSIONAL", "Groupement"),
    ])
    individual_profile = models.CharField(max_length=20, blank=True, choices=[
        ("", "Tous"), ("SALARIE", "Salarié"),
        ("INDEPENDANT", "Indépendant / AGR"), ("MIXTE", "Mixte"),
    ])
    effective_from = models.DateTimeField(null=True, blank=True)
    # Uniquement des clés déclarées au catalogue, jamais du code exécutable.
    overrides = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name="+")
    retired_at = models.DateTimeField(null=True, blank=True)
    retired_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    retirement_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["code", "-version"]
        constraints = [models.UniqueConstraint(fields=["tenant", "code", "version"],
                                               name="unique_configuration_profile_version"),
                       models.UniqueConstraint(fields=["code", "version"], condition=models.Q(tenant__isnull=True),
                                               name="unique_group_configuration_version")]
        permissions = [
            ("publish_configurationprofile", "Peut publier et retirer une configuration métier"),
            ("preview_configurationprofile", "Peut simuler une configuration métier"),
        ]

    def __str__(self):
        return f"{self.name} v{self.version}"

    def save(self, *args, **kwargs):
        # Contrairement aux données métier, None est ici un périmètre explicite.
        models.Model.save(self, *args, **kwargs)


class ConfigurationPublicationLock(models.Model):
    """Sérialise les publications Groupe et filiales sur le même verrou."""
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
