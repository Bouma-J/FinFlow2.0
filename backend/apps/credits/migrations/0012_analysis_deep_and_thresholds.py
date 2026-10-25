import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0011_financial_analysis_multiple_and_roles"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        # ----- Nouveaux champs de saisie (endettement consolidé & historique) -----
        migrations.AddField(
            model_name="financialanalysis",
            name="active_loans_count",
            field=models.PositiveIntegerField(
                default=0, verbose_name="nombre de crédits actifs (tous prêteurs)"
            ),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="credit_bureau_checked",
            field=models.BooleanField(
                default=False, verbose_name="centrale des risques / BIC consultée"
            ),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="credit_bureau_date",
            field=models.DateField(
                blank=True, null=True,
                verbose_name="date de consultation centrale des risques",
            ),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="has_payment_incidents",
            field=models.BooleanField(
                default=False, verbose_name="incidents de paiement recensés"
            ),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="max_days_late",
            field=models.PositiveIntegerField(
                blank=True, null=True,
                verbose_name="retard maximum constaté (jours)",
            ),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="incidents_comment",
            field=models.TextField(
                blank=True,
                verbose_name="détails des incidents / engagements externes",
            ),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="prior_loans_count",
            field=models.PositiveIntegerField(
                default=0,
                verbose_name="nombre de crédits antérieurs dans l'institution",
            ),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="prior_repayment_rate",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=6, null=True,
                verbose_name="taux de remboursement historique (%)",
            ),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="prior_max_delay_days",
            field=models.PositiveIntegerField(
                blank=True, null=True,
                verbose_name="retard maximum historique interne (jours)",
            ),
        ),
        # ----- Particulier : charges informelles & stabilité / quotité -----
        migrations.AddField(
            model_name="financialanalysis",
            name="tontine_expense",
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=18,
                verbose_name="tontines / cotisations d'épargne",
            ),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="social_contributions",
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=18,
                verbose_name="cotisations sociales / assurances",
            ),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="family_support_expense",
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=18,
                verbose_name="soutien familial / transferts",
            ),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="net_salary",
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=18,
                verbose_name="salaire net (base quotité cessible)",
            ),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="salary_deductions",
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=18,
                verbose_name="retenues déjà prélevées à la source",
            ),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="employment_seniority_months",
            field=models.PositiveIntegerField(
                blank=True, null=True,
                verbose_name="ancienneté dans l'emploi / l'activité (mois)",
            ),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="informal_income_weight",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=6, null=True,
                help_text="Laisser vide pour utiliser le seuil de la filiale.",
                verbose_name="pondération appliquée aux revenus informels (%)",
            ),
        ),
        # ----- Entreprise : dettes court terme & période N-1 -----
        migrations.AddField(
            model_name="financialanalysis",
            name="short_term_debt",
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=18,
                verbose_name="autres dettes court terme (fiscales, sociales…)",
            ),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="turnover_prev",
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=18,
                verbose_name="chiffre d'affaires N-1",
            ),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="net_result_prev",
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=18,
                verbose_name="résultat net N-1",
            ),
        ),
        # ----- Indicateurs calculés (stress, couverture) & synthèse -----
        migrations.AddField(
            model_name="financialanalysis",
            name="debt_ratio_stress",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=8, null=True,
                verbose_name="taux d'endettement sous stress (%)",
            ),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="dscr_stress",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=8, null=True,
                verbose_name="DSCR sous stress",
            ),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="guarantee_coverage",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=8, null=True,
                verbose_name="couverture par les garanties (%)",
            ),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="score_breakdown",
            field=models.JSONField(
                blank=True, default=dict, verbose_name="détail du score"
            ),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="strengths",
            field=models.TextField(blank=True, verbose_name="points forts"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="weaknesses",
            field=models.TextField(
                blank=True, verbose_name="points de vigilance"
            ),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="recommended_conditions",
            field=models.TextField(
                blank=True,
                verbose_name="conditions / recommandations proposées",
            ),
        ),
        migrations.AlterField(
            model_name="financialanalysis",
            name="internal_score",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=6, null=True,
                verbose_name="score interne (/100)",
            ),
        ),
        # ----- Modèle des seuils paramétrables par filiale -----
        migrations.CreateModel(
            name="AnalysisThreshold",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="créé le")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="modifié le")),
                ("max_debt_ratio", models.DecimalField(decimal_places=2, default=40, max_digits=6, verbose_name="taux d'endettement max — particulier (%)")),
                ("min_dscr", models.DecimalField(decimal_places=2, default=1.2, max_digits=6, verbose_name="DSCR minimum")),
                ("max_leverage_ratio", models.DecimalField(decimal_places=2, default=70, max_digits=6, verbose_name="ratio d'endettement max — entreprise (%)")),
                ("min_living_wage_per_capita", models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="reste à vivre minimum par personne")),
                ("min_interest_coverage", models.DecimalField(decimal_places=2, default=3, max_digits=6, verbose_name="couverture minimale des charges financières (x)")),
                ("max_gearing", models.DecimalField(decimal_places=2, default=1.5, max_digits=6, verbose_name="gearing max (dettes fin. / capitaux propres)")),
                ("min_financial_autonomy", models.DecimalField(decimal_places=2, default=20, max_digits=6, verbose_name="autonomie financière minimale (%)")),
                ("min_current_ratio", models.DecimalField(decimal_places=2, default=1, max_digits=6, verbose_name="liquidité générale minimale")),
                ("min_guarantee_coverage", models.DecimalField(decimal_places=2, default=100, max_digits=6, verbose_name="couverture minimale par les garanties (%)")),
                ("stress_pct", models.DecimalField(decimal_places=2, default=20, max_digits=6, verbose_name="baisse appliquée au stress test (%)")),
                ("transferable_quota_fraction", models.DecimalField(decimal_places=2, default=33.33, max_digits=6, verbose_name="quotité cessible du salaire (%)")),
                ("informal_income_weight", models.DecimalField(decimal_places=2, default=70, max_digits=6, verbose_name="pondération des revenus informels (%)")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="%(app_label)s_%(class)s_set", to="tenants.tenant", verbose_name="filiale")),
            ],
            options={
                "verbose_name": "seuils d'analyse financière",
                "verbose_name_plural": "seuils d'analyse financière",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="analysisthreshold",
            constraint=models.UniqueConstraint(
                fields=["tenant"], name="unique_analysis_threshold_per_tenant"
            ),
        ),
    ]
