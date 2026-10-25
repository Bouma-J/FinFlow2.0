from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("credits", "0019_medium_term_mfa_and_indexes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="creditapplication",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Brouillon"),
                    ("SUBMITTED", "Soumis"),
                    ("IN_APPROVAL", "En cours d'approbation"),
                    ("APPROVED", "Approuvé"),
                    ("REJECTED", "Rejeté"),
                    ("RETURNED", "Retourné pour correction"),
                    ("CONTRACT_GENERATED", "Contrat généré"),
                    (
                        "DISBURSEMENT_PENDING",
                        "Décaissement en attente de validation",
                    ),
                    ("DISBURSED", "Décaissé"),
                    ("CLOSED", "Clôturé"),
                    ("CANCELLED", "Annulé"),
                ],
                db_index=True,
                default="DRAFT",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="disbursement_previous_status",
            field=models.CharField(
                blank=True,
                default="",
                max_length=32,
                verbose_name="statut avant demande de décaissement",
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="disbursement_requested_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="décaissement demandé le",
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="disbursement_requested_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                verbose_name="décaissement demandé par",
            ),
        ),
        migrations.AlterModelOptions(
            name="creditapplication",
            options={
                "ordering": ["-created_at"],
                "permissions": [
                    (
                        "disburse_creditapplication",
                        "Peut valider / exécuter le décaissement d'un dossier",
                    ),
                    (
                        "initiate_disburse_creditapplication",
                        "Peut initier une demande de décaissement",
                    ),
                ],
                "verbose_name": "dossier de crédit",
                "verbose_name_plural": "dossiers de crédit",
            },
        ),
    ]
