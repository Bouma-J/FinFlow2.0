from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0020_disbursement_pending"),
    ]

    operations = [
        migrations.AlterField(
            model_name="loan",
            name="status",
            field=models.CharField(
                choices=[
                    ("ACTIVE", "En cours"),
                    ("CLOSED", "Soldé"),
                    ("DEFAULTED", "Passé en perte / défaut"),
                ],
                default="ACTIVE",
                max_length=20,
            ),
        ),
    ]
