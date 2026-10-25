# Generated manually for dossier cleanup & analysis reference

import django.db.models.deletion
from django.db import migrations, models


def forwards_copy_and_flags(apps, schema_editor):
    CreditApplication = apps.get_model("credits", "CreditApplication")
    FinancialAnalysis = apps.get_model("credits", "FinancialAnalysis")

    for app in CreditApplication.objects.all().iterator():
        analyses = list(
            FinancialAnalysis.objects.filter(application_id=app.pk).order_by(
                "-created_at"
            )
        )
        if not analyses:
            continue
        # Dernière analyse = référence
        latest = analyses[0]
        FinancialAnalysis.objects.filter(application_id=app.pk).update(
            is_reference=False
        )
        FinancialAnalysis.objects.filter(pk=latest.pk).update(is_reference=True)

        # Copie des champs dossier → analyse de référence si vides
        updates = {}
        if getattr(app, "activity", None) and not latest.sub_sector:
            updates["sub_sector"] = (app.activity or "")[:200]
        if getattr(app, "employees_count", None) is not None and latest.workforce_count is None:
            updates["workforce_count"] = app.employees_count
        if (
            getattr(app, "job_seniority_months", None) is not None
            and latest.employment_seniority_months is None
        ):
            updates["employment_seniority_months"] = app.job_seniority_months
        if getattr(app, "bceao_check_done", False) and not latest.credit_bureau_checked:
            updates["credit_bureau_checked"] = True
        if getattr(app, "bceao_check_result", "") and not latest.incidents_comment:
            updates["incidents_comment"] = app.bceao_check_result
        if getattr(app, "has_past_incidents", False) and not latest.has_payment_incidents:
            updates["has_payment_incidents"] = True
        if getattr(app, "credit_history_notes", "") and not latest.incidents_comment:
            notes = app.credit_history_notes
            existing = updates.get("incidents_comment") or latest.incidents_comment or ""
            updates["incidents_comment"] = (
                f"{existing}\n{notes}".strip() if existing else notes
            )
        if getattr(app, "seasonality", "") and not latest.sector_comment:
            updates["sector_comment"] = app.seasonality
        # Salaire net unique
        if latest.salary_income and (
            not latest.net_salary or latest.net_salary == 0
        ):
            updates["net_salary"] = latest.salary_income
        if updates:
            FinancialAnalysis.objects.filter(pk=latest.pk).update(**updates)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0016_credit_application_fees"),
    ]

    operations = [
        migrations.AddField(
            model_name="financialanalysis",
            name="is_reference",
            field=models.BooleanField(
                default=False,
                help_text="Une seule analyse de référence par dossier (score, risque, comité).",
                verbose_name="analyse de référence",
            ),
        ),
        migrations.AddField(
            model_name="financialanalysis",
            name="workforce_count",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="effectif actuel (nombre d'employés)",
            ),
        ),
        migrations.RunPython(forwards_copy_and_flags, noop_reverse),
        migrations.AlterField(
            model_name="creditapplication",
            name="financed_quota",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Calculée automatiquement : montant de référence / coût total.",
                max_digits=6,
                null=True,
                verbose_name="quotité financée (%)",
            ),
        ),
        migrations.AlterField(
            model_name="creditapplication",
            name="risk_level",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Dérivé de l'analyse financière de référence à la soumission.",
                null=True,
                verbose_name="niveau de risque (1-5)",
            ),
        ),
        migrations.AlterField(
            model_name="financialanalysis",
            name="new_installment",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=18,
                null=True,
                verbose_name="échéance institution (hors épargne)",
            ),
        ),
        migrations.RemoveField(model_name="creditapplication", name="activity"),
        migrations.RemoveField(model_name="creditapplication", name="analysis"),
        migrations.RemoveField(model_name="creditapplication", name="bceao_check_done"),
        migrations.RemoveField(model_name="creditapplication", name="bceao_check_result"),
        migrations.RemoveField(model_name="creditapplication", name="competitive_advantage"),
        migrations.RemoveField(model_name="creditapplication", name="credit_history_notes"),
        migrations.RemoveField(model_name="creditapplication", name="direct_competitors_count"),
        migrations.RemoveField(model_name="creditapplication", name="employees_count"),
        migrations.RemoveField(model_name="creditapplication", name="has_past_incidents"),
        migrations.RemoveField(model_name="creditapplication", name="internal_rating"),
        migrations.RemoveField(model_name="creditapplication", name="job_seniority_months"),
        migrations.RemoveField(model_name="creditapplication", name="main_suppliers_count"),
        migrations.RemoveField(model_name="creditapplication", name="main_suppliers_names"),
        migrations.RemoveField(model_name="creditapplication", name="risk_class"),
        migrations.RemoveField(model_name="creditapplication", name="seasonality"),
    ]
