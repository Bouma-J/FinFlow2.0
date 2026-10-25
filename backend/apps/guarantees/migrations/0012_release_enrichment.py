import uuid

import django.db.models.deletion
from django.db import migrations, models

import apps.guarantees.models


class Migration(migrations.Migration):

    dependencies = [
        ("guarantees", "0011_dation_fees_settlement"),
        ("tenants", "0003_tenant_officers_agency_manager"),
    ]

    operations = [
        migrations.AddField(
            model_name="guaranteereleaserequest",
            name="fees_client_total",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=18,
                null=True,
                verbose_name="frais à charge client",
            ),
        ),
        migrations.AddField(
            model_name="guaranteereleaserequest",
            name="fees_institution_total",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=18,
                null=True,
                verbose_name="frais à charge institution",
            ),
        ),
        migrations.AddField(
            model_name="guaranteereleaserequest",
            name="acte_status",
            field=models.CharField(
                choices=[
                    ("NONE", "Non généré"),
                    ("GENERATED", "Généré"),
                    ("SIGNED", "Signé déposé"),
                ],
                db_index=True,
                default="NONE",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="guaranteereleaserequest",
            name="acte_generated",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to=apps.guarantees.models.release_acte_upload_path,
                verbose_name="acte généré",
            ),
        ),
        migrations.AddField(
            model_name="guaranteereleaserequest",
            name="acte_generated_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="acte généré le"
            ),
        ),
        migrations.AddField(
            model_name="guaranteereleaserequest",
            name="acte_signed",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to=apps.guarantees.models.release_acte_upload_path,
                verbose_name="acte signé",
            ),
        ),
        migrations.AddField(
            model_name="guaranteereleaserequest",
            name="acte_signed_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="acte signé déposé le"
            ),
        ),
        migrations.CreateModel(
            name="ReleaseFee",
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
                    "fee_type",
                    models.CharField(
                        choices=[
                            ("NOTARY", "Notaire / acte"),
                            ("REGISTRATION", "Radiation / publicité"),
                            ("BAILIFF", "Huissier"),
                            ("ADMIN", "Frais administratifs"),
                            ("OTHER", "Divers"),
                        ],
                        default="OTHER",
                        max_length=30,
                    ),
                ),
                ("label", models.CharField(blank=True, max_length=255, verbose_name="libellé")),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2, max_digits=18, verbose_name="montant"
                    ),
                ),
                (
                    "payer",
                    models.CharField(
                        choices=[
                            ("CLIENT", "Client"),
                            ("INSTITUTION", "Institution"),
                        ],
                        default="CLIENT",
                        max_length=20,
                    ),
                ),
                (
                    "fee_date",
                    models.DateField(blank=True, null=True, verbose_name="date"),
                ),
                (
                    "recoverable",
                    models.BooleanField(default=True, verbose_name="récupérable"),
                ),
                ("notes", models.TextField(blank=True, verbose_name="notes")),
                (
                    "release",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fees",
                        to="guarantees.guaranteereleaserequest",
                        verbose_name="demande de main levée",
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
                "verbose_name": "frais de main levée",
                "verbose_name_plural": "frais de main levée",
                "ordering": ["fee_date", "created_at"],
            },
        ),
    ]
