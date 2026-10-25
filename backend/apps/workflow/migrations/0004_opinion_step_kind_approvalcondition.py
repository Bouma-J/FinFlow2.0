# Generated manually for Phase 1 workflow enhancements

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0003_approvaltask_proposed_amount"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="approvalstep",
            name="step_kind",
            field=models.CharField(
                choices=[
                    ("CONSULTATIVE", "Consultative"),
                    ("DECISIONAL", "Décisionnelle"),
                ],
                default="CONSULTATIVE",
                max_length=20,
                verbose_name="nature de l'étape",
            ),
        ),
        migrations.AddField(
            model_name="approvaltask",
            name="opinion",
            field=models.CharField(
                blank=True,
                choices=[
                    ("FAVORABLE", "Favorable"),
                    ("FAVORABLE_SOUS_RESERVE", "Favorable sous réserve"),
                    ("DEFAVORABLE", "Défavorable"),
                ],
                max_length=25,
                verbose_name="avis du validateur",
            ),
        ),
        migrations.AlterField(
            model_name="workflowinstance",
            name="status",
            field=models.CharField(
                choices=[
                    ("IN_PROGRESS", "En cours"),
                    ("AWAITING_CONDITIONS", "En attente de levée des réserves"),
                    ("APPROVED", "Approuvé"),
                    ("REJECTED", "Rejeté"),
                    ("RETURNED", "Retourné pour correction"),
                    ("CANCELLED", "Annulé"),
                ],
                default="IN_PROGRESS",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="ApprovalCondition",
            fields=[
                ("id", models.UUIDField(editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("description", models.TextField(verbose_name="description de la réserve")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "En attente de levée"),
                            ("LIFTED", "Levée — en attente de validation"),
                            ("VALIDATED", "Validée"),
                        ],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                ("issued_at", models.DateTimeField(auto_now_add=True, verbose_name="émis le")),
                ("lifted_at", models.DateTimeField(blank=True, null=True, verbose_name="levée le")),
                ("lift_comment", models.TextField(blank=True, verbose_name="commentaire de levée")),
                (
                    "validated_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="validée le"),
                ),
                (
                    "validation_comment",
                    models.TextField(blank=True, verbose_name="commentaire de validation"),
                ),
                (
                    "application",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="approval_conditions",
                        to="credits.creditapplication",
                        verbose_name="dossier",
                    ),
                ),
                (
                    "issued_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="issued_conditions",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="émis par",
                    ),
                ),
                (
                    "lifted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="lifted_conditions",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="levée par",
                    ),
                ),
                (
                    "task",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="conditions",
                        to="workflow.approvaltask",
                        verbose_name="tâche d'origine",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(app_label)s_%(class)s_set",
                        to="tenants.tenant",
                    ),
                ),
                (
                    "validated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="validated_conditions",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="validée par",
                    ),
                ),
            ],
            options={
                "verbose_name": "réserve d'approbation",
                "verbose_name_plural": "réserves d'approbation",
                "ordering": ["created_at"],
            },
        ),
    ]
