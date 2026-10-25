# Generated manually for dation multi-assets

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("guarantees", "0007_guarantee_renewed_from"),
        ("tenants", "0003_tenant_officers_agency_manager"),
    ]

    operations = [
        migrations.CreateModel(
            name="DationAsset",
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
                    "source",
                    models.CharField(
                        choices=[
                            ("EXISTING_GUARANTEE", "Garantie existante"),
                            ("ADDITIONAL", "Bien additionnel"),
                        ],
                        default="ADDITIONAL",
                        max_length=30,
                    ),
                ),
                ("description", models.TextField(blank=True, verbose_name="description")),
                (
                    "value",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=18,
                        null=True,
                        verbose_name="valeur",
                    ),
                ),
                (
                    "dation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assets",
                        to="guarantees.dationrequest",
                        verbose_name="demande de dation",
                    ),
                ),
                (
                    "guarantee",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="dation_asset_links",
                        to="guarantees.guarantee",
                        verbose_name="garantie source",
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
                "verbose_name": "bien de dation",
                "verbose_name_plural": "biens de dation",
                "ordering": ["created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="dationasset",
            constraint=models.UniqueConstraint(
                condition=models.Q(("guarantee__isnull", False)),
                fields=("dation", "guarantee"),
                name="uniq_dation_guarantee_asset",
            ),
        ),
    ]
