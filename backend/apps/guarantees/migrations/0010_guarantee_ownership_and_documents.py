# Generated manually for guarantee ownership + free documents

import uuid

import django.db.models.deletion
from django.db import migrations, models

import apps.guarantees.models


class Migration(migrations.Migration):

    dependencies = [
        ("guarantees", "0009_release_request_form_fields"),
        ("sureties", "0005_surety_corporate_fields"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="guarantee",
            name="belongs_to_applicant",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Si Non, une caution doit être renseignée (le bien "
                    "n'appartient pas au client demandeur du crédit)."
                ),
                verbose_name="bien appartenant au client demandeur",
            ),
        ),
        migrations.AddField(
            model_name="guarantee",
            name="surety",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Obligatoire si le bien n'appartient pas au client demandeur."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="guarantees",
                to="sureties.surety",
                verbose_name="caution (propriétaire du bien)",
            ),
        ),
        migrations.CreateModel(
            name="GuaranteeDocument",
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
                        upload_to=apps.guarantees.models.guarantee_file_path,
                        verbose_name="scan / fichier",
                    ),
                ),
                (
                    "guarantee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
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
                "verbose_name": "document de garantie",
                "verbose_name_plural": "documents de garantie",
                "ordering": ["created_at"],
            },
        ),
    ]
