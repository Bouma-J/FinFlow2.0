"""Journal d'audit inaltérable des opérations."""
import uuid

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Enregistrement d'une opération sur une entité métier."""

    class Action(models.TextChoices):
        CREATE = "CREATE", "Création"
        UPDATE = "UPDATE", "Modification"
        DELETE = "DELETE", "Suppression"
        LOGIN = "LOGIN", "Connexion"
        LOGOUT = "LOGOUT", "Déconnexion"
        WORKFLOW = "WORKFLOW", "Action workflow"
        INTEGRATION = "INTEGRATION", "Échange Core Banking"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    model_label = models.CharField("entité", max_length=120, blank=True)
    object_id = models.CharField("id objet", max_length=64, blank=True)
    object_repr = models.CharField("libellé objet", max_length=255, blank=True)
    changes = models.JSONField("changements", default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "entrée d'audit"
        verbose_name_plural = "piste d'audit"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["model_label", "object_id"]),
            models.Index(fields=["tenant", "-timestamp"]),
        ]

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.action} {self.model_label}"
