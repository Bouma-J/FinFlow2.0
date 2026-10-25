# Generated manually — retrait legacy FinancialAnalysis (transaction séparée)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0017_dossier_reference_amount_and_analysis_cleanup"),
    ]

    operations = [
        migrations.RemoveField(model_name="financialanalysis", name="existing_debt"),
        migrations.RemoveField(model_name="financialanalysis", name="monthly_charges"),
        migrations.RemoveField(model_name="financialanalysis", name="monthly_income"),
    ]
