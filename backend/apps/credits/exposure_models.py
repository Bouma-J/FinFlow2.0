"""Relations économiques et situations d'engagement justifiées et revues."""
from django.conf import settings
from django.db import models

from apps.common.models import AuthoredModel, TenantScopedModel


class BorrowerGroup(TenantScopedModel, AuthoredModel):
    code = models.SlugField(max_length=60)
    name = models.CharField(max_length=180)
    reason = models.TextField()
    is_active = models.BooleanField(default=True)
    clients = models.ManyToManyField("clients.Client", related_name="borrower_groups")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "code"], name="unique_borrower_group_code")]
        ordering = ["code"]

    def __str__(self):
        return self.name


class CreditExposureObservation(TenantScopedModel, AuthoredModel):
    """Total externe incluant le CBS ; il n'est jamais additionné au portefeuille local.

    Aucune synchronisation CBS n'est présumée. Une situation est saisie à partir
    d'une pièce et vérifiée par une deuxième personne avant d'être utilisée.
    """
    client = models.ForeignKey("clients.Client", on_delete=models.PROTECT, related_name="exposure_observations")
    currency = models.CharField(max_length=3)
    as_of = models.DateField()
    drawn_principal = models.DecimalField(max_digits=18, decimal_places=2)
    undrawn_commitments = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    guarantees_given = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    source_reference = models.CharField(max_length=180)
    # Une référence GED réelle permet à l'examinateur de consulter le justificatif.
    evidence = models.ForeignKey("documents.Document", on_delete=models.PROTECT, related_name="exposure_observations")
    completeness_confirmed = models.BooleanField(default=False)
    note = models.TextField(blank=True)
    status = models.CharField(max_length=12, default="DRAFT", choices=[("DRAFT", "Brouillon"), ("VERIFIED", "Vérifiée"), ("REVOKED", "Révoquée")])
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    verified_at = models.DateTimeField(null=True, blank=True)
    revocation_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-as_of", "-created_at"]
        permissions = [("verify_creditexposureobservation", "Peut vérifier ou révoquer une situation consolidée d'engagements")]
        indexes = [models.Index(fields=["tenant", "client", "currency", "status"])]

    def __str__(self):
        return f"Engagements {self.client_id} au {self.as_of}"
