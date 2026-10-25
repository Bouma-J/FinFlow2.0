from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0005_client_authored"),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="cbs_client_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Identifiant / matricule du client dans le Core Banking.",
                max_length=50,
                verbose_name="matricule Core Banking",
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="cbs_account_number",
            field=models.CharField(
                blank=True,
                help_text="Numéro de compte principal du client dans le Core Banking.",
                max_length=50,
                verbose_name="n° de compte Core Banking",
            ),
        ),
    ]
