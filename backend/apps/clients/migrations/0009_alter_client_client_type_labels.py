from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0008_medium_term_mfa_and_indexes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="client",
            name="client_type",
            field=models.CharField(
                choices=[
                    ("INDIVIDUAL", "Personne physique"),
                    ("PROFESSIONAL", "Groupement"),
                    ("CORPORATE", "Personne morale"),
                ],
                max_length=20,
            ),
        ),
    ]
