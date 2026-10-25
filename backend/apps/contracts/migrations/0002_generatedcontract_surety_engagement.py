# Generated manually for surety engagement enrichment

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("contracts", "0001_initial"),
        ("sureties", "0006_surety_documents"),
    ]

    operations = [
        migrations.AddField(
            model_name="generatedcontract",
            name="surety_engagement",
            field=models.ForeignKey(
                blank=True,
                help_text="Renseigné pour les contrats de cautionnement liés à une caution.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="generated_contracts",
                to="sureties.suretyengagement",
                verbose_name="engagement de caution",
            ),
        ),
    ]
