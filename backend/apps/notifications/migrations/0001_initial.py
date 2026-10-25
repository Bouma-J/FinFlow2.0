import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("tenants", "0003_tenant_officers_agency_manager"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TenantNotificationSettings",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, db_index=True, verbose_name="créé le"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="modifié le"),
                ),
                (
                    "enabled",
                    models.BooleanField(
                        default=True,
                        help_text="Interrupteur général des e-mails pour cette filiale.",
                        verbose_name="notifications actives",
                    ),
                ),
                (
                    "notify_on_step",
                    models.BooleanField(
                        default=True,
                        help_text=(
                            "Envoie un e-mail aux utilisateurs du rôle de l'étape "
                            "suivante lorsqu'une action leur est assignée."
                        ),
                        verbose_name="alerter l'étape suivante",
                    ),
                ),
                (
                    "notify_on_completion",
                    models.BooleanField(
                        default=True,
                        help_text=(
                            "Envoie un e-mail à tous les intervenants lorsque le "
                            "circuit est terminé (approuvé, rejeté ou retourné "
                            "au soumissionnaire)."
                        ),
                        verbose_name="informer les intervenants en fin de circuit",
                    ),
                ),
                (
                    "notify_on_rejection",
                    models.BooleanField(
                        default=True, verbose_name="informer en cas de rejet"
                    ),
                ),
                (
                    "notify_on_return",
                    models.BooleanField(
                        default=True, verbose_name="informer en cas de renvoi"
                    ),
                ),
                (
                    "from_email",
                    models.EmailField(
                        blank=True,
                        help_text=(
                            "Si vide, utilise l'expéditeur global de la plateforme."
                        ),
                        max_length=254,
                        verbose_name="expéditeur",
                    ),
                ),
                (
                    "reply_to",
                    models.EmailField(
                        blank=True, max_length=254, verbose_name="répondre à"
                    ),
                ),
                (
                    "cc_tenant_email",
                    models.BooleanField(
                        default=False,
                        verbose_name="mettre l'e-mail de la filiale en copie",
                    ),
                ),
                (
                    "tenant",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notification_settings",
                        to="tenants.tenant",
                        verbose_name="filiale",
                    ),
                ),
            ],
            options={
                "verbose_name": "paramètres de notification",
                "verbose_name_plural": "paramètres de notification",
            },
        ),
        migrations.CreateModel(
            name="NotificationLog",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, db_index=True, verbose_name="créé le"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="modifié le"),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("STEP", "Action à effectuer"),
                            ("COMPLETION", "Fin de circuit"),
                            ("REJECTION", "Rejet"),
                            ("RETURN", "Renvoi"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "En attente"),
                            ("SENT", "Envoyé"),
                            ("FAILED", "Échec"),
                            ("SKIPPED", "Ignoré"),
                        ],
                        default="PENDING",
                        max_length=10,
                    ),
                ),
                ("subject", models.CharField(blank=True, max_length=255)),
                ("recipients", models.JSONField(blank=True, default=list)),
                ("body_preview", models.TextField(blank=True)),
                ("error_message", models.TextField(blank=True)),
                (
                    "workflow_instance_id",
                    models.UUIDField(blank=True, db_index=True, null=True),
                ),
                (
                    "approval_task_id",
                    models.UUIDField(blank=True, db_index=True, null=True),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(app_label)s_%(class)s_set",
                        to="tenants.tenant",
                        verbose_name="filiale",
                    ),
                ),
            ],
            options={
                "verbose_name": "journal de notification",
                "verbose_name_plural": "journaux de notification",
                "ordering": ["-created_at"],
            },
        ),
    ]
