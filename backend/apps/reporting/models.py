"""Snapshots de reporting matérialisés (consolidation Groupe à grande échelle)."""
import uuid

from django.db import models


class ReportingSnapshot(models.Model):
    """
    Agrégat pré-calculé pour éviter les full-scans live multi-filiales.

    scope=TENANT → un tableau de bord filiale
    scope=GROUP  → consolidation Groupe (tenant null)
    """

    class Scope(models.TextChoices):
        TENANT = "TENANT", "Filiale"
        GROUP = "GROUP", "Groupe"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scope = models.CharField(max_length=10, choices=Scope.choices, db_index=True)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reporting_snapshots",
    )
    kind = models.CharField(
        "type",
        max_length=64,
        default="dashboard",
        help_text="dashboard | breakdown:<dimension>",
        db_index=True,
    )
    params_hash = models.CharField(
        "empreinte filtres",
        max_length=64,
        blank=True,
        default="",
        help_text="Hash des filtres (vide = sans filtre).",
    )
    payload = models.JSONField(default=dict)
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "snapshot reporting"
        verbose_name_plural = "snapshots reporting"
        permissions = [
            ("view_dashboard", "Consulter le tableau de bord / reporting"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "tenant", "kind", "params_hash"],
                name="uniq_reporting_snapshot",
            )
        ]
        indexes = [
            models.Index(fields=["scope", "kind", "-computed_at"]),
        ]

    def __str__(self):
        target = self.tenant_id or "GROUP"
        return f"{self.scope}/{self.kind} @ {target} ({self.computed_at})"
