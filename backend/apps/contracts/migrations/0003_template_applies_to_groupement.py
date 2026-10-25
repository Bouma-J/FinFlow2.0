from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contracts", "0002_generatedcontract_surety_engagement"),
    ]

    operations = [
        migrations.AlterField(
            model_name="contracttemplate",
            name="applies_to",
            field=models.CharField(
                choices=[
                    ("ANY", "Tous les clients"),
                    ("INDIVIDUAL", "Particuliers uniquement"),
                    ("CORPORATE", "Entreprises et groupements"),
                ],
                default="ANY",
                max_length=15,
                verbose_name="s'applique à",
            ),
        ),
    ]
