# Generated manually to deepen financial analysis by borrower profile.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0030_creditapplication_cbs_disbursement_refs"),
    ]

    operations = [
        migrations.AlterField(
            model_name="financialanalysis", name="other_activity_income",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="revenus d'activité (hors bloc dédié)"),
        ),
        migrations.AddField(
            model_name="financialanalysis", name="analysis_details",
            field=models.JSONField(blank=True, default=dict, verbose_name="détail de la reconstitution financière", help_text="Produits, stocks, dettes, historique et plan de trésorerie détaillés."),
        ),
        # Cadre et fiabilité de l'analyse
        migrations.AddField(
            model_name="financialanalysis",
            name="information_quality",
            field=models.CharField(
                choices=[
                    ("DECLARED", "Déclarée par le client"),
                    ("PARTIALLY_VERIFIED", "Partiellement vérifiée"),
                    ("VERIFIED", "Vérifiée sur pièces / visite"),
                    ("AUDITED", "Comptes certifiés / audités"),
                ],
                default="DECLARED",
                max_length=25,
                verbose_name="niveau de fiabilité des informations",
            ),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="financial_statement_date",
            field=models.DateField(blank=True, null=True, verbose_name="date d'arrêté des données financières"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="bank_statement_months",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="nombre de mois de relevés examinés"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="financial_documents_verified",
            field=models.BooleanField(default=False, verbose_name="pièces financières vérifiées"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="field_visit_confirmed",
            field=models.BooleanField(default=False, verbose_name="visite terrain prise en compte"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="stock_count_verified",
            field=models.BooleanField(default=False, verbose_name="stock vérifié / inventorié"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="cash_position_verified",
            field=models.BooleanField(default=False, verbose_name="caisse et banques vérifiées"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="verification_comment",
            field=models.TextField(blank=True, verbose_name="commentaire de vérification et écarts constatés"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="primary_repayment_source",
            field=models.CharField(blank=True, max_length=250, verbose_name="source principale de remboursement"),
        ),
        # Personne physique : stabilité, patrimoine et engagements non bancaires
        migrations.AddField(
            model_name="financialanalysis",
            name="employment_type",
            field=models.CharField(blank=True, choices=[("PERMANENT", "CDI / fonctionnaire"), ("FIXED_TERM", "CDD / contrat à terme"), ("RETIRED", "Retraité"), ("DAILY", "Journalier / intermittent"), ("OTHER", "Autre situation")], max_length=20, verbose_name="type d'emploi"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="employer_name",
            field=models.CharField(blank=True, max_length=250, verbose_name="employeur"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="employer_sector",
            field=models.CharField(blank=True, max_length=150, verbose_name="secteur de l'employeur"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="salary_paid_through_bank",
            field=models.BooleanField(default=False, verbose_name="salaire domicilié / traçable en banque"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="salary_verified",
            field=models.BooleanField(default=False, verbose_name="salaire vérifié sur bulletin ou relevé"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="variable_income",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="primes et revenus variables récurrents"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="pension_income",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="pension / retraite"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="other_monthly_obligations",
            field=models.DecimalField(decimal_places=2, default=0, help_text="Pensions, loyers dus, assurances, engagements non bancaires.", max_digits=18, verbose_name="autres obligations récurrentes"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="personal_savings",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="épargne disponible du ménage"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="personal_real_estate_value",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="valeur immobilière nette du ménage"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="personal_vehicle_value",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="valeur des véhicules du ménage"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="personal_productive_assets",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="valeur des actifs productifs du ménage"),
        ),
        # Entreprise : P&L détaillé et bilan reconstitué
        migrations.AddField(
            model_name="financialanalysis",
            name="other_operating_income",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="autres produits d'exploitation"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="cash_in_hand",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="caisse"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="bank_balance",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="solde bancaire disponible"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="other_current_assets",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="autres actifs courants"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="land_building_value",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="terrains et bâtiments"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="equipment_value",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="matériel et équipements"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="vehicle_value",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="véhicules d'exploitation"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="other_fixed_assets",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="autres immobilisations"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="tax_social_debt",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="dettes fiscales et sociales"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="other_current_debt",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="autres dettes d'exploitation"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="long_term_debt",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="dettes financières long terme"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="shareholder_debt",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="comptes courants d'associés"),
        ),
        # Activité indépendante
        migrations.AddField(
            model_name="financialanalysis",
            name="activity_name",
            field=models.CharField(blank=True, max_length=250, verbose_name="activité principale"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="activity_business_age_months",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="ancienneté de l'activité (mois)"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="activity_sales_days",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="jours de vente sur la période"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="activity_purchases",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="achats / approvisionnements activité"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="activity_stock_value",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="stock de l'activité"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="activity_receivables",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="créances clients de l'activité"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="activity_cash_available",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="trésorerie disponible de l'activité"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="activity_fixed_assets",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="actifs productifs de l'activité"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="activity_supplier_debt",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="dettes fournisseurs de l'activité"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="activity_is_formal",
            field=models.BooleanField(default=False, verbose_name="activité formalisée"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="activity_records_available",
            field=models.BooleanField(default=False, verbose_name="cahier de caisse / pièces d'activité disponibles"),
        ),
        # Groupement
        migrations.AddField(
            model_name="financialanalysis",
            name="group_age_months",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="ancienneté du groupement (mois)"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="members_with_arrears",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="membres en retard de cotisation"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="group_records_verified",
            field=models.BooleanField(default=False, verbose_name="registres et épargne du groupement vérifiés"),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="collective_savings_locked",
            field=models.BooleanField(default=False, verbose_name="épargne collective mobilisable / nantie"),
        ),
    ]
