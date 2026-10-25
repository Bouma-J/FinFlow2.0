from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("guarantees", "0005_merge_guarantee_branches"),
        ("credits", "0014_financialanalysis_chemicals_pesticides_and_more"),
        ("clients", "0007_client_manager_details"),
        ("tenants", "0003_tenant_officers_agency_manager"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="GuaranteeReleaseRequest",
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
                    "reference",
                    models.CharField(
                        blank=True, db_index=True, max_length=30, verbose_name="référence"
                    ),
                ),
                (
                    "cbs_loan_reference",
                    models.CharField(
                        blank=True, max_length=100, verbose_name="référence prêt CBS"
                    ),
                ),
                (
                    "cbs_settled",
                    models.BooleanField(
                        blank=True, null=True, verbose_name="prêt soldé (CBS)"
                    ),
                ),
                (
                    "cbs_outstanding",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=18,
                        null=True,
                        verbose_name="encours CBS",
                    ),
                ),
                ("cbs_currency", models.CharField(blank=True, default="XAF", max_length=3)),
                (
                    "cbs_checked_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="vérifié CBS le"
                    ),
                ),
                (
                    "cbs_raw",
                    models.JSONField(blank=True, default=dict, verbose_name="réponse CBS"),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Brouillon"),
                            ("IN_APPROVAL", "En validation"),
                            ("APPROVED", "Approuvée"),
                            ("REJECTED", "Rejetée"),
                            ("RETURNED", "Retournée"),
                            ("COMPLETED", "Clôturée"),
                            ("CANCELLED", "Annulée"),
                            ("BLOCKED", "Bloquée (CBS)"),
                        ],
                        db_index=True,
                        default="DRAFT",
                        max_length=20,
                    ),
                ),
                ("comment", models.TextField(blank=True, verbose_name="commentaire")),
                (
                    "completed_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="clôturée le"
                    ),
                ),
                (
                    "agency",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="release_requests",
                        to="tenants.agency",
                        verbose_name="agence",
                    ),
                ),
                (
                    "application",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="release_requests",
                        to="credits.creditapplication",
                        verbose_name="dossier",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="créé par",
                    ),
                ),
                (
                    "guarantee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="release_requests",
                        to="guarantees.guarantee",
                        verbose_name="garantie",
                    ),
                ),
                (
                    "loan",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="release_requests",
                        to="credits.loan",
                        verbose_name="prêt",
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
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="modifié par",
                    ),
                ),
            ],
            options={
                "verbose_name": "demande de main levée",
                "verbose_name_plural": "demandes de main levée",
                "ordering": ["-created_at"],
                "permissions": [
                    (
                        "initiate_guaranteereleaserequest",
                        "Peut initier une demande de main levée",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="DationRequest",
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
                    "reference",
                    models.CharField(
                        blank=True, db_index=True, max_length=30, verbose_name="référence"
                    ),
                ),
                (
                    "cbs_client_id",
                    models.CharField(
                        blank=True, max_length=100, verbose_name="identifiant client CBS"
                    ),
                ),
                (
                    "cbs_total_outstanding",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=18,
                        null=True,
                        verbose_name="encours total CBS",
                    ),
                ),
                ("cbs_currency", models.CharField(blank=True, default="XAF", max_length=3)),
                (
                    "cbs_checked_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="vérifié CBS le"
                    ),
                ),
                (
                    "cbs_raw",
                    models.JSONField(blank=True, default=dict, verbose_name="réponse CBS"),
                ),
                (
                    "asset_description",
                    models.TextField(blank=True, verbose_name="description du bien cédé"),
                ),
                (
                    "asset_value",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=18,
                        null=True,
                        verbose_name="valeur du bien",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Brouillon"),
                            ("IN_APPROVAL", "En validation"),
                            ("APPROVED", "Approuvée"),
                            ("REJECTED", "Rejetée"),
                            ("RETURNED", "Retournée"),
                            ("COMPLETED", "Clôturée"),
                            ("CANCELLED", "Annulée"),
                            ("BLOCKED", "Bloquée (CBS)"),
                        ],
                        db_index=True,
                        default="DRAFT",
                        max_length=20,
                    ),
                ),
                ("comment", models.TextField(blank=True, verbose_name="commentaire")),
                (
                    "completed_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="clôturée le"
                    ),
                ),
                (
                    "agency",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="dation_requests",
                        to="tenants.agency",
                        verbose_name="agence",
                    ),
                ),
                (
                    "application",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="dation_requests",
                        to="credits.creditapplication",
                        verbose_name="dossier",
                    ),
                ),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="dation_requests",
                        to="clients.client",
                        verbose_name="client",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="créé par",
                    ),
                ),
                (
                    "resulting_guarantee",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="dation_origins",
                        to="guarantees.guarantee",
                        verbose_name="garantie créée",
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
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="modifié par",
                    ),
                ),
            ],
            options={
                "verbose_name": "demande de dation en paiement",
                "verbose_name_plural": "demandes de dation en paiement",
                "ordering": ["-created_at"],
                "permissions": [
                    ("initiate_dationrequest", "Peut initier une dation en paiement")
                ],
            },
        ),
    ]
