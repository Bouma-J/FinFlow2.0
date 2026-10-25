# Generated manually for P3 recouvrement

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("collections", "0003_p2_escalation_next_action"),
        ("credits", "0020_disbursement_pending"),
        ("tenants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LitigationFile",
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
                    "court_name",
                    models.CharField(blank=True, max_length=255, verbose_name="juridiction"),
                ),
                (
                    "case_reference",
                    models.CharField(
                        blank=True, max_length=100, verbose_name="référence judiciaire"
                    ),
                ),
                (
                    "lawyer",
                    models.CharField(
                        blank=True, max_length=255, verbose_name="avocat / conseil"
                    ),
                ),
                (
                    "bailiff",
                    models.CharField(blank=True, max_length=255, verbose_name="huissier"),
                ),
                (
                    "filing_date",
                    models.DateField(
                        blank=True, null=True, verbose_name="date d'introduction"
                    ),
                ),
                (
                    "hearing_date",
                    models.DateField(
                        blank=True, null=True, verbose_name="prochaine audience"
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("OPEN", "Ouvert"),
                            ("SUSPENDED", "Suspendu"),
                            ("CLOSED", "Clôturé"),
                        ],
                        db_index=True,
                        default="OPEN",
                        max_length=20,
                    ),
                ),
                ("notes", models.TextField(blank=True, verbose_name="notes")),
                (
                    "case",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="litigation",
                        to="collections.collectioncase",
                        verbose_name="dossier de recouvrement",
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
                "verbose_name": "dossier contentieux",
                "verbose_name_plural": "dossiers contentieux",
            },
        ),
        migrations.CreateModel(
            name="LitigationEvent",
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
                ("event_date", models.DateField(verbose_name="date")),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("HEARING", "Audience"),
                            ("SEIZURE", "Saisie"),
                            ("JUDGMENT", "Jugement"),
                            ("NOTICE", "Mise en demeure"),
                            ("OTHER", "Autre"),
                        ],
                        max_length=20,
                    ),
                ),
                ("comment", models.TextField(blank=True, verbose_name="commentaire")),
                (
                    "litigation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="collections.litigationfile",
                        verbose_name="dossier contentieux",
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
                "verbose_name": "événement contentieux",
                "verbose_name_plural": "événements contentieux",
                "ordering": ["-event_date", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="LoanRestructure",
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
                ("effective_date", models.DateField(verbose_name="date d'effet")),
                ("previous_duration_months", models.PositiveIntegerField()),
                (
                    "new_duration_months",
                    models.PositiveIntegerField(verbose_name="nouvelle durée (mois)"),
                ),
                ("previous_rate", models.DecimalField(decimal_places=3, max_digits=6)),
                (
                    "new_rate",
                    models.DecimalField(
                        decimal_places=3, max_digits=6, verbose_name="nouveau taux (%)"
                    ),
                ),
                (
                    "outstanding_principal",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=18,
                        verbose_name="capital restant dû",
                    ),
                ),
                (
                    "reason",
                    models.CharField(blank=True, max_length=255, verbose_name="motif"),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("APPLIED", "Appliquée"),
                            ("CANCELLED", "Annulée"),
                        ],
                        default="APPLIED",
                        max_length=20,
                    ),
                ),
                (
                    "applied_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="loan_restructures",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "case",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="restructures",
                        to="collections.collectioncase",
                        verbose_name="dossier",
                    ),
                ),
                (
                    "loan",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="restructures",
                        to="credits.loan",
                        verbose_name="prêt",
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
                "verbose_name": "restructuration",
                "verbose_name_plural": "restructurations",
                "ordering": ["-effective_date", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="WriteOff",
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
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=18,
                        verbose_name="montant passé en perte",
                    ),
                ),
                ("write_off_date", models.DateField(verbose_name="date")),
                (
                    "reason",
                    models.CharField(blank=True, max_length=255, verbose_name="motif"),
                ),
                (
                    "approved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="loan_write_offs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "case",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="write_offs",
                        to="collections.collectioncase",
                        verbose_name="dossier",
                    ),
                ),
                (
                    "loan",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="write_offs",
                        to="credits.loan",
                        verbose_name="prêt",
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
                "verbose_name": "passage en perte",
                "verbose_name_plural": "passages en perte",
                "ordering": ["-write_off_date", "-created_at"],
            },
        ),
    ]
