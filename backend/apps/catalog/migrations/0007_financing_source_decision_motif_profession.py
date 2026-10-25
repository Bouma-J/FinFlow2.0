# Generated manually for CBS ref source-fin / motif-decision / profession

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0006_service_point_cbs_manager"),
        ("tenants", "0005_cbs_disbursement_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="CbsProfession",
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
                ("code", models.CharField(max_length=50, verbose_name="code")),
                ("label", models.CharField(max_length=255, verbose_name="libellé")),
                (
                    "description",
                    models.TextField(blank=True, verbose_name="description"),
                ),
                (
                    "is_active",
                    models.BooleanField(default=True, verbose_name="actif"),
                ),
                (
                    "cbs_code",
                    models.CharField(
                        blank=True,
                        help_text="Code Perfect / CBS envoyé lors des appels d'intégration.",
                        max_length=64,
                        verbose_name="identifiant CBS",
                    ),
                ),
                (
                    "sort_order",
                    models.PositiveIntegerField(
                        default=0, verbose_name="ordre d'affichage"
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
                "verbose_name": "profession CBS",
                "verbose_name_plural": "professions CBS",
                "ordering": ["sort_order", "label"],
                "abstract": False,
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant", "code"),
                        name="unique_cbsprofession_code_per_tenant",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="DecisionMotif",
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
                ("code", models.CharField(max_length=50, verbose_name="code")),
                ("label", models.CharField(max_length=255, verbose_name="libellé")),
                (
                    "description",
                    models.TextField(blank=True, verbose_name="description"),
                ),
                (
                    "is_active",
                    models.BooleanField(default=True, verbose_name="actif"),
                ),
                (
                    "cbs_code",
                    models.CharField(
                        blank=True,
                        help_text="Code Perfect / CBS envoyé lors des appels d'intégration.",
                        max_length=64,
                        verbose_name="identifiant CBS",
                    ),
                ),
                (
                    "sort_order",
                    models.PositiveIntegerField(
                        default=0, verbose_name="ordre d'affichage"
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
                "verbose_name": "motif de décision CBS",
                "verbose_name_plural": "motifs de décision CBS",
                "ordering": ["sort_order", "label"],
                "abstract": False,
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant", "code"),
                        name="unique_decisionmotif_code_per_tenant",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="FinancingSource",
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
                ("code", models.CharField(max_length=50, verbose_name="code")),
                ("label", models.CharField(max_length=255, verbose_name="libellé")),
                (
                    "description",
                    models.TextField(blank=True, verbose_name="description"),
                ),
                (
                    "is_active",
                    models.BooleanField(default=True, verbose_name="actif"),
                ),
                (
                    "cbs_code",
                    models.CharField(
                        blank=True,
                        help_text="Code Perfect / CBS envoyé lors des appels d'intégration.",
                        max_length=64,
                        verbose_name="identifiant CBS",
                    ),
                ),
                (
                    "sort_order",
                    models.PositiveIntegerField(
                        default=0, verbose_name="ordre d'affichage"
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
                "verbose_name": "source de financement CBS",
                "verbose_name_plural": "sources de financement CBS",
                "ordering": ["sort_order", "label"],
                "abstract": False,
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant", "code"),
                        name="unique_financingsource_code_per_tenant",
                    )
                ],
            },
        ),
    ]
