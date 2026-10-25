# Generated manually for free surety documents

import uuid

import django.db.models.deletion
from django.db import migrations, models

import apps.sureties.models


class Migration(migrations.Migration):

    dependencies = [
        ("sureties", "0005_surety_corporate_fields"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="SuretyDocument",
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
                ("title", models.CharField(max_length=200, verbose_name="intitulé")),
                (
                    "file",
                    models.FileField(
                        max_length=255,
                        upload_to=apps.sureties.models.surety_file_path,
                        verbose_name="scan / fichier",
                    ),
                ),
                (
                    "surety",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
                        to="sureties.surety",
                        verbose_name="caution",
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
                "verbose_name": "document de caution",
                "verbose_name_plural": "documents de caution",
                "ordering": ["created_at"],
            },
        ),
    ]
