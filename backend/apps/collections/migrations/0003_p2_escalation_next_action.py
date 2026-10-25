# Generated manually for P2 recouvrement

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("collections", "0002_initial"),
        ("tenants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="collectionaction",
            name="next_follow_up_date",
            field=models.DateField(
                blank=True,
                help_text="Si renseigné, met à jour la prochaine action du dossier.",
                null=True,
                verbose_name="suivi prévu",
            ),
        ),
        migrations.AddField(
            model_name="collectioncase",
            name="next_action_date",
            field=models.DateField(
                blank=True, db_index=True, null=True, verbose_name="prochaine action"
            ),
        ),
        migrations.AddField(
            model_name="collectioncase",
            name="next_action_note",
            field=models.CharField(
                blank=True, max_length=255, verbose_name="note prochaine action"
            ),
        ),
        migrations.AddField(
            model_name="collectioncase",
            name="next_action_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("CALL", "Appel téléphonique"),
                    ("SMS", "SMS"),
                    ("EMAIL", "Courriel"),
                    ("LETTER", "Courrier"),
                    ("VISIT", "Visite terrain"),
                    ("LEGAL", "Acte judiciaire"),
                ],
                max_length=10,
                verbose_name="type prochaine action",
            ),
        ),
        migrations.AddField(
            model_name="collectioncase",
            name="stage_changed_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="dernier changement de stade"
            ),
        ),
        migrations.CreateModel(
            name="CollectionEscalationRule",
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
                    "min_days_overdue",
                    models.PositiveIntegerField(verbose_name="seuil jours de retard"),
                ),
                (
                    "target_stage",
                    models.CharField(
                        choices=[
                            ("AMICABLE", "Amiable"),
                            ("PRECONTENTIOUS", "Précontentieux"),
                            ("LITIGATION", "Contentieux"),
                        ],
                        max_length=20,
                    ),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="active")),
                (
                    "label",
                    models.CharField(blank=True, max_length=100, verbose_name="libellé"),
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
                "verbose_name": "règle d'escalade",
                "verbose_name_plural": "règles d'escalade",
                "ordering": ["min_days_overdue"],
            },
        ),
        migrations.CreateModel(
            name="CollectionStageHistory",
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
                    "from_stage",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("AMICABLE", "Amiable"),
                            ("PRECONTENTIOUS", "Précontentieux"),
                            ("LITIGATION", "Contentieux"),
                            ("CLOSED", "Clôturé"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "to_stage",
                    models.CharField(
                        choices=[
                            ("AMICABLE", "Amiable"),
                            ("PRECONTENTIOUS", "Précontentieux"),
                            ("LITIGATION", "Contentieux"),
                            ("CLOSED", "Clôturé"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "reason",
                    models.CharField(blank=True, max_length=255, verbose_name="motif"),
                ),
                (
                    "automatic",
                    models.BooleanField(
                        default=False, verbose_name="escalade automatique"
                    ),
                ),
                (
                    "case",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stage_history",
                        to="collections.collectioncase",
                        verbose_name="dossier",
                    ),
                ),
                (
                    "changed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="collection_stage_changes",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="modifié par",
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
                "verbose_name": "historique de stade",
                "verbose_name_plural": "historiques de stade",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="collectioncase",
            index=models.Index(
                fields=["tenant", "next_action_date"],
                name="collections_tenant__next_act_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="collectionescalationrule",
            constraint=models.UniqueConstraint(
                fields=("tenant", "min_days_overdue"),
                name="unique_escalation_days_per_tenant",
            ),
        ),
    ]
