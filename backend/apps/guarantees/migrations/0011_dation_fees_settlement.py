import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("guarantees", "0010_guarantee_ownership_and_documents"),
        ("tenants", "0003_tenant_officers_agency_manager"),
    ]

    operations = [
        migrations.AddField(
            model_name="dationrequest",
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
            model_name="dationrequest",
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
            model_name="dationrequest",
            name="claim_to_cover",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Créance CBS + frais client.",
                max_digits=18,
                null=True,
                verbose_name="créance à couvrir",
            ),
        ),
        migrations.AddField(
            model_name="dationrequest",
            name="residual_balance",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Max(0, créance à couvrir − total biens).",
                max_digits=18,
                null=True,
                verbose_name="solde résiduel",
            ),
        ),
        migrations.AddField(
            model_name="dationrequest",
            name="surplus_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Max(0, total biens − créance à couvrir).",
                max_digits=18,
                null=True,
                verbose_name="trop-perçu / trop-value",
            ),
        ),
        migrations.AddField(
            model_name="dationrequest",
            name="require_full_coverage",
            field=models.BooleanField(
                default=False,
                help_text="Si vrai, la soumission est refusée en sous-couverture.",
                verbose_name="exiger la couverture intégrale",
            ),
        ),
        migrations.AddField(
            model_name="dationrequest",
            name="settlement_notes",
            field=models.TextField(blank=True, verbose_name="notes de règlement"),
        ),
        migrations.AddField(
            model_name="dationasset",
            name="asset_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("REAL_ESTATE", "Immobilier"),
                    ("VEHICLE", "Véhicule"),
                    ("EQUIPMENT", "Matériel / équipement"),
                    ("JEWELRY", "Bijoux / objets de valeur"),
                    ("FINANCIAL", "Actif financier"),
                    ("OTHER", "Autre"),
                ],
                default="OTHER",
                max_length=30,
                verbose_name="type de bien",
            ),
        ),
        migrations.AddField(
            model_name="dationasset",
            name="notes",
            field=models.TextField(blank=True, verbose_name="notes"),
        ),
        migrations.AlterField(
            model_name="dationasset",
            name="value",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=18,
                null=True,
                verbose_name="valeur retenue",
            ),
        ),
        migrations.CreateModel(
            name="DationFee",
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
                            ("APPRAISAL", "Expertise"),
                            ("REGISTRATION", "Enregistrement / publicité"),
                            ("BAILIFF", "Huissier"),
                            ("TRANSFER_TAX", "Droits de mutation"),
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
                    "asset",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="fees",
                        to="guarantees.dationasset",
                        verbose_name="bien concerné",
                    ),
                ),
                (
                    "dation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fees",
                        to="guarantees.dationrequest",
                        verbose_name="demande de dation",
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
                "verbose_name": "frais de dation",
                "verbose_name_plural": "frais de dation",
                "ordering": ["fee_date", "created_at"],
            },
        ),
    ]
