# Generated manually — circuit d'analyse restructuration / perte.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("collections", "0011_action_dialogue"),
    ]

    operations = [
        migrations.AlterField(
            model_name="loanrestructure",
            name="case",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="restructures",
                to="collections.collectioncase",
                verbose_name="dossier de recouvrement",
            ),
        ),
        migrations.AlterField(
            model_name="loanrestructure",
            name="reason",
            field=models.CharField(max_length=255, verbose_name="motif"),
        ),
        migrations.AlterField(
            model_name="loanrestructure",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "En attente"),
                    ("APPROVED", "Approuvée"),
                    ("REJECTED", "Rejetée"),
                    ("CANCELLED", "Annulée"),
                    ("APPLIED", "Appliquée (historique)"),
                ],
                default="PENDING",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="loanrestructure",
            name="applied_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="loan_restructures",
                to=settings.AUTH_USER_MODEL,
                verbose_name="décidé par",
            ),
        ),
        migrations.AddField(
            model_name="loanrestructure",
            name="origin",
            field=models.CharField(
                choices=[
                    ("LOAN", "Fiche prêt"),
                    ("COLLECTION", "Recouvrement"),
                ],
                default="COLLECTION",
                max_length=20,
                verbose_name="origine",
            ),
        ),
        migrations.AddField(
            model_name="loanrestructure",
            name="request_kind",
            field=models.CharField(
                choices=[
                    ("CLIENT", "Demande client"),
                    ("INTERNAL", "Initiative interne"),
                ],
                default="INTERNAL",
                max_length=20,
                verbose_name="nature",
            ),
        ),
        migrations.AddField(
            model_name="loanrestructure",
            name="first_due_date",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="première échéance proposée",
            ),
        ),
        migrations.AddField(
            model_name="loanrestructure",
            name="proposed_schedule",
            field=models.JSONField(
                blank=True, default=dict, verbose_name="échéancier proposé"
            ),
        ),
        migrations.AddField(
            model_name="loanrestructure",
            name="requested_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="requested_loan_restructures",
                to=settings.AUTH_USER_MODEL,
                verbose_name="demandé par",
            ),
        ),
        migrations.AddField(
            model_name="loanrestructure",
            name="decided_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="décidé le"
            ),
        ),
        migrations.AddField(
            model_name="loanrestructure",
            name="decision_comment",
            field=models.CharField(
                blank=True,
                max_length=255,
                verbose_name="commentaire de décision",
            ),
        ),
        migrations.AlterField(
            model_name="writeoff",
            name="reason",
            field=models.CharField(max_length=255, verbose_name="motif"),
        ),
        migrations.AddField(
            model_name="writeoff",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "En attente"),
                    ("APPLIED", "Appliquée"),
                    ("REJECTED", "Rejetée"),
                    ("CANCELLED", "Annulée"),
                ],
                default="APPLIED",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="writeoff",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "En attente"),
                    ("APPLIED", "Appliquée"),
                    ("REJECTED", "Rejetée"),
                    ("CANCELLED", "Annulée"),
                ],
                default="PENDING",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="writeoff",
            name="requested_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="requested_write_offs",
                to=settings.AUTH_USER_MODEL,
                verbose_name="demandé par",
            ),
        ),
        migrations.AddField(
            model_name="writeoff",
            name="decided_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="décidé le"
            ),
        ),
        migrations.AddField(
            model_name="writeoff",
            name="decision_comment",
            field=models.CharField(
                blank=True,
                max_length=255,
                verbose_name="commentaire de décision",
            ),
        ),
    ]
