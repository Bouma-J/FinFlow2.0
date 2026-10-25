# Generated manually for credit application extra fees

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0015_disburse_permission"),
        ("tenants", "0003_tenant_officers_agency_manager"),
    ]

    operations = [
        migrations.CreateModel(
            name="CreditApplicationFee",
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
                ("label", models.CharField(max_length=150, verbose_name="intitulé")),
                (
                    "mode",
                    models.CharField(
                        choices=[
                            ("PERCENT", "Pourcentage"),
                            ("AMOUNT", "Montant"),
                        ],
                        default="AMOUNT",
                        max_length=10,
                        verbose_name="mode",
                    ),
                ),
                (
                    "value",
                    models.DecimalField(
                        decimal_places=3,
                        help_text="Pourcentage du montant proposé, ou montant fixe.",
                        max_digits=18,
                        verbose_name="valeur",
                    ),
                ),
                (
                    "sort_order",
                    models.PositiveIntegerField(default=0, verbose_name="ordre"),
                ),
                (
                    "application",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="extra_fees",
                        to="credits.creditapplication",
                        verbose_name="dossier",
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
                "verbose_name": "frais de dossier additionnel",
                "verbose_name_plural": "frais de dossier additionnels",
                "ordering": ["sort_order", "id"],
            },
        ),
    ]
