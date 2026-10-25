from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0003_cbs_referentials"),
    ]

    operations = [
        migrations.AlterField(
            model_name="creditproduct",
            name="client_type",
            field=models.CharField(
                choices=[
                    ("INDIVIDUAL", "Particulier"),
                    ("PROFESSIONAL", "Groupement"),
                    ("CORPORATE", "Entreprise"),
                    ("ALL", "Tous"),
                ],
                default="ALL",
                max_length=20,
            ),
        ),
    ]
