"""
Connecteurs vers les Core Banking Systems des filiales.

Chaque filiale dispose d'un connecteur paramétrable indépendant. Les
échanges sont journalisés (traçabilité, idempotence, reprise sur échec).
"""
from django.db import models

from apps.common.models import TenantScopedModel


class CoreBankingConnector(TenantScopedModel):
    """Configuration d'accès au Core Banking d'une filiale."""

    class Protocol(models.TextChoices):
        REST = "REST", "API REST"
        SOAP = "SOAP", "Service SOAP"
        SFTP = "SFTP", "Échange SFTP"
        BATCH = "BATCH", "Fichier batch"

    name = models.CharField("nom", max_length=255)
    protocol = models.CharField(max_length=10, choices=Protocol.choices)
    base_url = models.CharField("URL d'accès", max_length=500, blank=True)

    # Paramètres sensibles / techniques (chiffrés au niveau infra / coffre-fort)
    auth_config = models.JSONField("authentification", default=dict, blank=True)
    mapping_rules = models.JSONField("règles de mapping", default=dict, blank=True)
    certificate_reference = models.CharField("réf. certificat", max_length=255, blank=True)

    is_active = models.BooleanField("actif", default=True)
    timeout_seconds = models.PositiveIntegerField("timeout (s)", default=30)
    max_retries = models.PositiveIntegerField("tentatives max", default=3)

    class Meta:
        verbose_name = "connecteur Core Banking"
        verbose_name_plural = "connecteurs Core Banking"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "name"],
                name="unique_connector_name_per_tenant",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.get_protocol_display()})"

    def get_auth_config_decrypted(self) -> dict:
        """auth_config avec mots de passe / tokens déchiffrés."""
        from apps.common.secret_crypto import decrypt_auth_config

        return decrypt_auth_config(self.auth_config)


class IntegrationLog(TenantScopedModel):
    """Journal d'un échange avec un Core Banking (traçabilité et reprise)."""

    class Direction(models.TextChoices):
        OUTBOUND = "OUTBOUND", "Sortant"
        INBOUND = "INBOUND", "Entrant"

    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        SUCCESS = "SUCCESS", "Succès"
        FAILED = "FAILED", "Échec"
        RETRY = "RETRY", "À rejouer"

    connector = models.ForeignKey(
        CoreBankingConnector,
        on_delete=models.PROTECT,
        related_name="logs",
        verbose_name="connecteur",
    )
    operation = models.CharField("opération", max_length=100)
    direction = models.CharField(
        max_length=10, choices=Direction.choices, default=Direction.OUTBOUND
    )
    # Clé d'idempotence pour éviter les doublons (ex. doubla mise en place)
    idempotency_key = models.CharField(max_length=120, blank=True, db_index=True)

    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    attempts = models.PositiveIntegerField("tentatives", default=0)
    external_reference = models.CharField("réf. externe (CBS)", max_length=100, blank=True)
    error_message = models.TextField("message d'erreur", blank=True)

    class Meta:
        verbose_name = "journal d'intégration"
        verbose_name_plural = "journaux d'intégration"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["connector", "idempotency_key"],
                condition=models.Q(idempotency_key__gt=""),
                name="unique_idempotency_per_connector",
            )
        ]

    def __str__(self):
        return f"{self.operation} — {self.get_status_display()}"
