"""Préférences et journal des alertes e-mail par filiale."""
from django.conf import settings
from django.db import models

from apps.common.models import BaseModel, TenantScopedModel


class TenantNotificationSettings(BaseModel):
    """Paramétrage des alertes e-mail d'une filiale."""

    tenant = models.OneToOneField(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="notification_settings",
        verbose_name="filiale",
    )
    enabled = models.BooleanField(
        "notifications actives",
        default=True,
        help_text="Interrupteur général des e-mails pour cette filiale.",
    )
    notify_on_step = models.BooleanField(
        "alerter l'étape suivante",
        default=True,
        help_text=(
            "Envoie un e-mail aux utilisateurs du rôle de l'étape suivante "
            "lorsqu'une action leur est assignée."
        ),
    )
    notify_on_completion = models.BooleanField(
        "informer en fin de circuit (approbation)",
        default=True,
        help_text=(
            "Lorsque le circuit est approuvé : e-mail à l'initiateur du dossier "
            "(et aux intervenants) pour l'informer que le dossier est validé "
            "et qu'il peut générer les contrats à faire signer. "
            "Couvre aussi les autres fins de circuit selon les options ci-dessous."
        ),
    )
    notify_on_rejection = models.BooleanField(
        "informer l'initiateur en cas de rejet",
        default=True,
        help_text=(
            "Envoie un e-mail à l'initiateur du dossier (et aux intervenants) "
            "lorsque le circuit est rejeté."
        ),
    )
    notify_on_return = models.BooleanField(
        "informer l'initiateur en cas de renvoi",
        default=True,
        help_text=(
            "Envoie un e-mail à l'initiateur du dossier (et aux intervenants) "
            "lorsque le dossier est renvoyé pour correction."
        ),
    )
    notify_collection_email = models.BooleanField(
        "relances recouvrement par e-mail",
        default=False,
        help_text=(
            "Envoie un e-mail de relance au client lorsque la prochaine "
            "action du dossier est un courriel dû."
        ),
    )
    notify_collection_sms = models.BooleanField(
        "relances recouvrement par SMS (stub)",
        default=False,
        help_text=(
            "Journalise une tentative SMS (provider non branché : statut SKIPPED)."
        ),
    )
    notify_collection_transfer = models.BooleanField(
        "alerte transfert de tranche",
        default=True,
        help_text=(
            "E-mail aux responsables de la nouvelle tranche lorsqu'un "
            "dossier de recouvrement y est transmis."
        ),
    )
    notify_collection_dialogue = models.BooleanField(
        "alerte commentaire / recommandation",
        default=True,
        help_text=(
            "E-mail à l'agent affecté et aux responsables de la tranche "
            "quand un commentaire, une demande ou une recommandation "
            "est déposé sur le dossier."
        ),
    )
    from_email = models.CharField(
        "expéditeur (From)",
        max_length=255,
        blank=True,
        help_text=(
            "Adresse seule (ex. noreply@filiale.com). "
            "Si vide, utilise l'identifiant SMTP. "
            "L'affichage est toujours « NOREPLY {filiale} <adresse> », "
            "sauf si vous saisissez déjà un nom complet « Nom <adresse> »."
        ),
    )
    reply_to = models.EmailField("répondre à", blank=True)
    cc_tenant_email = models.BooleanField(
        "mettre l'e-mail de la filiale en copie",
        default=False,
    )

    # --- SMTP propre à la filiale ---
    smtp_host = models.CharField(
        "serveur SMTP",
        max_length=255,
        blank=True,
        help_text="Ex. smtp.gmail.com. Si vide, utilise la configuration globale Django.",
    )
    smtp_port = models.PositiveIntegerField("port SMTP", default=587)
    smtp_use_tls = models.BooleanField("TLS (STARTTLS)", default=True)
    smtp_use_ssl = models.BooleanField("SSL", default=False)
    smtp_username = models.CharField(
        "identifiant SMTP",
        max_length=255,
        blank=True,
        help_text="En général la même adresse que l'expéditeur.",
    )
    smtp_password = models.CharField(
        "mot de passe SMTP",
        max_length=255,
        blank=True,
        help_text="Mot de passe ou « App Password ». Ne jamais exposer en clair côté API lecture.",
    )

    class Meta:
        verbose_name = "paramètres de notification"
        verbose_name_plural = "paramètres de notification"

    def __str__(self):
        return f"Notifications — {self.tenant}"

    @classmethod
    def for_tenant(cls, tenant):
        """Renvoie (et crée si besoin) les paramètres de la filiale."""
        if tenant is None:
            return None
        obj, _ = cls.objects.get_or_create(tenant=tenant)
        return obj


class NotificationLog(TenantScopedModel):
    """Journal d'un e-mail de notification (traçabilité)."""

    class Kind(models.TextChoices):
        STEP = "STEP", "Action à effectuer"
        COMPLETION = "COMPLETION", "Fin de circuit"
        REJECTION = "REJECTION", "Rejet"
        RETURN = "RETURN", "Renvoi"
        COLLECTION_REMINDER = "COLLECTION_REMINDER", "Relance recouvrement"
        COLLECTION_TRANSFER = "COLLECTION_TRANSFER", "Transfert de tranche"
        COLLECTION_DIALOGUE = "COLLECTION_DIALOGUE", "Dialogue recouvrement"

    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        SENT = "SENT", "Envoyé"
        FAILED = "FAILED", "Échec"
        SKIPPED = "SKIPPED", "Ignoré"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    subject = models.CharField(max_length=255, blank=True)
    recipients = models.JSONField(default=list, blank=True)
    body_preview = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    workflow_instance_id = models.UUIDField(null=True, blank=True, db_index=True)
    approval_task_id = models.UUIDField(null=True, blank=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "journal de notification"
        verbose_name_plural = "journaux de notification"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.get_status_display()}"
