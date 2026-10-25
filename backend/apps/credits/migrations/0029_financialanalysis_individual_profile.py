# Generated manually for individual_profile on FinancialAnalysis

from decimal import Decimal

from django.db import migrations, models


def _dec(value):
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def backfill_individual_profile(apps, schema_editor):
    FinancialAnalysis = apps.get_model("credits", "FinancialAnalysis")
    for row in FinancialAnalysis.objects.all().iterator():
        if row.individual_profile:
            continue
        if row.client_type in ("CORPORATE", "PROFESSIONAL"):
            continue
        has_salary = _dec(row.salary_income) > 0 or _dec(row.net_salary) > 0
        has_activity = bool(row.has_side_activity) or _dec(row.activity_turnover) > 0
        if has_salary and has_activity:
            profile = "MIXTE"
        elif has_activity:
            profile = "INDEPENDANT"
        elif has_salary:
            profile = "SALARIE"
        else:
            continue
        FinancialAnalysis.objects.filter(pk=row.pk).update(
            individual_profile=profile,
            has_side_activity=True
            if profile in ("INDEPENDANT", "MIXTE")
            else row.has_side_activity,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0028_require_formalization_before_disbursement"),
    ]

    operations = [
        migrations.AddField(
            model_name="financialanalysis",
            name="individual_profile",
            field=models.CharField(
                blank=True,
                choices=[
                    ("SALARIE", "Salarié"),
                    ("INDEPENDANT", "Indépendant"),
                    ("MIXTE", "Mixte (salarié + activité)"),
                ],
                help_text=(
                    "Salarié, indépendant ou mixte — oriente les blocs de l'analyse "
                    "pour les personnes physiques."
                ),
                max_length=20,
                verbose_name="profil particulier",
            ),
        ),
        migrations.AlterField(
            model_name="financialanalysis",
            name="has_side_activity",
            field=models.BooleanField(
                default=False,
                verbose_name="exerce une activité génératrice de revenus",
            ),
        ),
        migrations.AlterField(
            model_name="financialanalysis",
            name="activity_turnover",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=18,
                verbose_name="CA / recettes activité",
            ),
        ),
        migrations.AlterField(
            model_name="financialanalysis",
            name="activity_expenses",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=18,
                verbose_name="charges activité",
            ),
        ),
        migrations.AlterField(
            model_name="financialanalysis",
            name="activity_comment",
            field=models.TextField(blank=True, verbose_name="commentaire activité"),
        ),
        migrations.RunPython(backfill_individual_profile, migrations.RunPython.noop),
    ]
