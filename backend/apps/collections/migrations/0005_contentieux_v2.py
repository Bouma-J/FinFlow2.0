# Contentieux v2 — C1 à C5

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("collections", "0004_p3_litigation_restructure_writeoff"),
        ("guarantees", "0010_guarantee_ownership_and_documents"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="LegalParty",
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
                    "party_type",
                    models.CharField(
                        choices=[
                            ("LAW_FIRM", "Cabinet d'avocats"),
                            ("LAWYER", "Avocat"),
                            ("BAILIFF", "Huissier"),
                            ("NOTARY", "Notaire"),
                            ("EXPERT", "Expert"),
                            ("OTHER", "Autre"),
                        ],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        max_length=255, verbose_name="nom / raison sociale"
                    ),
                ),
                (
                    "registration_no",
                    models.CharField(
                        blank=True,
                        max_length=100,
                        verbose_name="n° barreau / agrément / RCCM",
                    ),
                ),
                (
                    "contact_name",
                    models.CharField(
                        blank=True, max_length=255, verbose_name="contact principal"
                    ),
                ),
                (
                    "phone",
                    models.CharField(blank=True, max_length=50, verbose_name="téléphone"),
                ),
                ("email", models.EmailField(blank=True, max_length=254, verbose_name="e-mail")),
                ("address", models.TextField(blank=True, verbose_name="adresse")),
                ("notes", models.TextField(blank=True, verbose_name="notes")),
                (
                    "is_active",
                    models.BooleanField(db_index=True, default=True, verbose_name="actif"),
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
                "verbose_name": "intervenant juridique",
                "verbose_name_plural": "intervenants juridiques",
                "ordering": ["name"],
            },
        ),
        migrations.AddIndex(
            model_name="legalparty",
            index=models.Index(
                fields=["tenant", "party_type", "is_active"],
                name="collections_legal_party_idx",
            ),
        ),
        # OneToOne → FK (plusieurs procédures par dossier)
        migrations.AlterField(
            model_name="litigationfile",
            name="case",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="litigations",
                to="collections.collectioncase",
                verbose_name="dossier de recouvrement",
            ),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="title",
            field=models.CharField(blank=True, max_length=255, verbose_name="intitulé"),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="action_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("PAYMENT_ORDER", "Injonction de payer"),
                    ("SUMMONS", "Assignation"),
                    ("SUMMARY", "Référé"),
                    ("ATTACHMENT", "Saisie-arrêt"),
                    ("OHADA", "Procédure OHADA"),
                    ("APPEAL", "Appel"),
                    ("OTHER", "Autre"),
                ],
                default="SUMMONS",
                max_length=20,
                verbose_name="nature de l'action",
            ),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="court_registry",
            field=models.CharField(blank=True, max_length=255, verbose_name="greffe"),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="chamber",
            field=models.CharField(blank=True, max_length=100, verbose_name="chambre"),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="law_firm",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="litigations_as_firm",
                to="collections.legalparty",
                verbose_name="cabinet mandaté",
            ),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="lawyer_party",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="litigations_as_lawyer",
                to="collections.legalparty",
                verbose_name="avocat référent",
            ),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="bailiff_party",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="litigations_as_bailiff",
                to="collections.legalparty",
                verbose_name="huissier",
            ),
        ),
        migrations.AlterField(
            model_name="litigationfile",
            name="lawyer",
            field=models.CharField(blank=True, max_length=255, verbose_name="avocat (texte)"),
        ),
        migrations.AlterField(
            model_name="litigationfile",
            name="bailiff",
            field=models.CharField(
                blank=True, max_length=255, verbose_name="huissier (texte)"
            ),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="mandate_start",
            field=models.DateField(blank=True, null=True, verbose_name="début mandat"),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="mandate_end",
            field=models.DateField(blank=True, null=True, verbose_name="fin mandat"),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="mandate_fee",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=18,
                null=True,
                verbose_name="honoraires forfaitaires",
            ),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="mandate_notes",
            field=models.TextField(blank=True, verbose_name="notes de mission"),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="claimed_principal",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=18,
                null=True,
                verbose_name="capital réclamé",
            ),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="claimed_interest",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=18,
                null=True,
                verbose_name="intérêts réclamés",
            ),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="claimed_penalties",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=18,
                null=True,
                verbose_name="pénalités réclamées",
            ),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="claimed_costs",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=18,
                null=True,
                verbose_name="frais réclamés",
            ),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="claimed_total",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=18,
                null=True,
                verbose_name="total réclamé",
            ),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="notice_date",
            field=models.DateField(
                blank=True, null=True, verbose_name="date mise en demeure"
            ),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="service_date",
            field=models.DateField(
                blank=True, null=True, verbose_name="date de signification"
            ),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="first_hearing_date",
            field=models.DateField(
                blank=True, null=True, verbose_name="première audience"
            ),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="hearing_time",
            field=models.TimeField(blank=True, null=True, verbose_name="heure audience"),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="hearing_location",
            field=models.CharField(
                blank=True, max_length=255, verbose_name="lieu audience"
            ),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="judgment_date",
            field=models.DateField(
                blank=True, null=True, verbose_name="date du jugement"
            ),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="judgment_outcome",
            field=models.CharField(
                blank=True,
                choices=[
                    ("FAVORABLE", "Favorable"),
                    ("PARTIAL", "Partiellement favorable"),
                    ("UNFAVORABLE", "Défavorable"),
                    ("SETTLEMENT", "Transaction"),
                    ("PENDING", "En attente"),
                ],
                max_length=20,
                verbose_name="sens du jugement",
            ),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="judgment_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=18,
                null=True,
                verbose_name="montant accordé",
            ),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="judgment_enforceable",
            field=models.BooleanField(default=False, verbose_name="exécutoire"),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="judgment_served_at",
            field=models.DateField(
                blank=True, null=True, verbose_name="date signification jugement"
            ),
        ),
        migrations.AlterField(
            model_name="litigationfile",
            name="status",
            field=models.CharField(
                choices=[
                    ("PRE_LITIGATION", "Précontentieux"),
                    ("FILED", "Introduite"),
                    ("IN_PROGRESS", "En cours"),
                    ("JUDGMENT", "Jugement rendu"),
                    ("ENFORCEMENT", "Exécution"),
                    ("APPEAL", "Appel / opposition"),
                    ("SETTLED", "Transaction / accord"),
                    ("ABANDONED", "Abandonnée"),
                    ("CLOSED", "Clôturée"),
                    ("OPEN", "Ouvert"),
                    ("SUSPENDED", "Suspendu"),
                ],
                db_index=True,
                default="PRE_LITIGATION",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="litigationfile",
            name="hearing_date",
            field=models.DateField(
                blank=True, db_index=True, null=True, verbose_name="prochaine audience"
            ),
        ),
        migrations.AddField(
            model_name="litigationfile",
            name="related_guarantees",
            field=models.ManyToManyField(
                blank=True,
                related_name="litigation_files",
                to="guarantees.guarantee",
                verbose_name="garanties concernées",
            ),
        ),
        migrations.AddIndex(
            model_name="litigationfile",
            index=models.Index(
                fields=["tenant", "status", "hearing_date"],
                name="collections_lit_status_hear_idx",
            ),
        ),
        # Events enrichis
        migrations.AddField(
            model_name="litigationevent",
            name="event_time",
            field=models.TimeField(blank=True, null=True, verbose_name="heure"),
        ),
        migrations.AddField(
            model_name="litigationevent",
            name="location",
            field=models.CharField(blank=True, max_length=255, verbose_name="lieu"),
        ),
        migrations.AddField(
            model_name="litigationevent",
            name="outcome",
            field=models.CharField(blank=True, max_length=255, verbose_name="résultat"),
        ),
        migrations.AddField(
            model_name="litigationevent",
            name="amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=18,
                null=True,
                verbose_name="montant lié",
            ),
        ),
        migrations.AddField(
            model_name="litigationevent",
            name="postponed",
            field=models.BooleanField(default=False, verbose_name="reportée"),
        ),
        migrations.AddField(
            model_name="litigationevent",
            name="next_date",
            field=models.DateField(blank=True, null=True, verbose_name="date de suite"),
        ),
        migrations.AddField(
            model_name="litigationevent",
            name="performed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="litigation_events",
                to="collections.legalparty",
                verbose_name="intervenant",
            ),
        ),
        migrations.AlterField(
            model_name="litigationevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("NOTICE", "Mise en demeure"),
                    ("FILING", "Introduction / dépôt"),
                    ("HEARING", "Audience"),
                    ("BRIEF", "Conclusions / mémoire"),
                    ("JUDGMENT", "Jugement / ordonnance"),
                    ("SERVICE", "Signification"),
                    ("SEIZURE", "Saisie"),
                    ("APPEAL", "Appel / opposition"),
                    ("SETTLEMENT", "Transaction / désistement"),
                    ("OTHER", "Autre"),
                ],
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="litigationevent",
            name="event_date",
            field=models.DateField(db_index=True, verbose_name="date"),
        ),
        migrations.CreateModel(
            name="LitigationSeizure",
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
                    "seizure_type",
                    models.CharField(
                        choices=[
                            ("ATTRIBUTION", "Saisie-attribution"),
                            ("MOVABLE", "Saisie mobilière"),
                            ("IMMOVABLE", "Saisie immobilière"),
                            ("SALE", "Vente forcée"),
                            ("WAGE", "Saisie sur salaire"),
                            ("OTHER", "Autre"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PLANNED", "Planifiée"),
                            ("DONE", "Réalisée"),
                            ("FAILED", "Échouée"),
                            ("CANCELLED", "Annulée"),
                        ],
                        default="PLANNED",
                        max_length=20,
                    ),
                ),
                (
                    "seizure_date",
                    models.DateField(blank=True, null=True, verbose_name="date"),
                ),
                (
                    "amount",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=18,
                        null=True,
                        verbose_name="montant",
                    ),
                ),
                (
                    "report_reference",
                    models.CharField(blank=True, max_length=100, verbose_name="réf. PV"),
                ),
                (
                    "inventory",
                    models.TextField(blank=True, verbose_name="inventaire / description"),
                ),
                ("notes", models.TextField(blank=True, verbose_name="notes")),
                (
                    "bailiff",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="seizures",
                        to="collections.legalparty",
                        verbose_name="huissier",
                    ),
                ),
                (
                    "guarantee",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="litigation_seizures",
                        to="guarantees.guarantee",
                        verbose_name="garantie liée",
                    ),
                ),
                (
                    "litigation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="seizures",
                        to="collections.litigationfile",
                        verbose_name="dossier contentieux",
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
                "verbose_name": "saisie",
                "verbose_name_plural": "saisies",
                "ordering": ["-seizure_date", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="LitigationCost",
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
                    "cost_type",
                    models.CharField(
                        choices=[
                            ("RETAINER", "Provision"),
                            ("FEE", "Honoraire"),
                            ("REGISTRY", "Frais de greffe"),
                            ("BAILIFF", "Frais d'huissier"),
                            ("TRAVEL", "Déplacement"),
                            ("OTHER", "Autre"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "label",
                    models.CharField(blank=True, max_length=255, verbose_name="libellé"),
                ),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2, max_digits=18, verbose_name="montant"
                    ),
                ),
                ("cost_date", models.DateField(verbose_name="date")),
                ("is_paid", models.BooleanField(default=False, verbose_name="payé")),
                (
                    "recoverable",
                    models.BooleanField(default=True, verbose_name="récupérable"),
                ),
                (
                    "notes",
                    models.CharField(blank=True, max_length=255, verbose_name="notes"),
                ),
                (
                    "litigation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="costs",
                        to="collections.litigationfile",
                        verbose_name="dossier contentieux",
                    ),
                ),
                (
                    "party",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="costs",
                        to="collections.legalparty",
                        verbose_name="bénéficiaire",
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
                "verbose_name": "frais contentieux",
                "verbose_name_plural": "frais contentieux",
                "ordering": ["-cost_date", "-created_at"],
            },
        ),
    ]
