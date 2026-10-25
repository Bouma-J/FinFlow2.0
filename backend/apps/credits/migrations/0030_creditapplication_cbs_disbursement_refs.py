# Generated manually for CBS disbursement refs on CreditApplication

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0029_financialanalysis_individual_profile"),
    ]

    operations = [
        migrations.AddField(
            model_name="creditapplication",
            name="cbs_demande_number",
            field=models.CharField(
                blank=True,
                default="",
                max_length=100,
                verbose_name="n° demande CBS (numDemande)",
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="cbs_demande_ref",
            field=models.CharField(
                blank=True,
                default="",
                max_length=100,
                verbose_name="réf. demande CBS (refDemande)",
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="cbs_contract_number",
            field=models.CharField(
                blank=True,
                default="",
                max_length=100,
                verbose_name="n° contrat CBS (numContrat)",
            ),
        ),
        migrations.AddField(
            model_name="creditapplication",
            name="cbs_operation_date",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="date opération CBS (dateOperation)",
            ),
        ),
    ]
