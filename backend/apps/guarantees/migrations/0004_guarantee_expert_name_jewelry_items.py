import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0001_initial"),
        ("guarantees", "0003_alter_guarantee_document_scan_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="guarantee",
            name="expert_name",
            field=models.CharField(
                blank=True, max_length=200, verbose_name="nom de l'expert"
            ),
        ),
        migrations.CreateModel(
            name="GuaranteeJewelryItem",
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
                    "nature",
                    models.CharField(
                        max_length=150, verbose_name="nature du bijou"
                    ),
                ),
                (
                    "weight",
                    models.DecimalField(
                        blank=True,
                        decimal_places=3,
                        max_digits=10,
                        null=True,
                        verbose_name="poids (g)",
                    ),
                ),
                (
                    "description",
                    models.CharField(
                        blank=True, max_length=255, verbose_name="description"
                    ),
                ),
                (
                    "guarantee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="jewelry_items",
                        to="guarantees.guarantee",
                        verbose_name="garantie",
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
                "verbose_name": "composante de bijou",
                "verbose_name_plural": "composantes de bijou",
                "ordering": ["id"],
            },
        ),
    ]
