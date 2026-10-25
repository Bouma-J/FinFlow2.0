# Generated manually for main levée form enrichment

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("guarantees", "0008_dation_assets"),
    ]

    operations = [
        migrations.AddField(
            model_name="guaranteereleaserequest",
            name="cbs_client_id",
            field=models.CharField(
                blank=True, max_length=100, verbose_name="matricule client CBS"
            ),
        ),
        migrations.AddField(
            model_name="guaranteereleaserequest",
            name="request_date",
            field=models.DateField(
                blank=True, null=True, verbose_name="date de la demande"
            ),
        ),
        migrations.AddField(
            model_name="guaranteereleaserequest",
            name="release_fees",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=18,
                null=True,
                verbose_name="frais de main levée",
            ),
        ),
    ]
