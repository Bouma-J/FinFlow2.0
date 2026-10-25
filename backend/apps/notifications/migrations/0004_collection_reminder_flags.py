from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0003_alter_from_email_charfield"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantnotificationsettings",
            name="notify_collection_email",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Envoie un e-mail de relance au client lorsque la prochaine "
                    "action du dossier est un courriel dû."
                ),
                verbose_name="relances recouvrement par e-mail",
            ),
        ),
        migrations.AddField(
            model_name="tenantnotificationsettings",
            name="notify_collection_sms",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Journalise une tentative SMS (provider non branché : statut SKIPPED)."
                ),
                verbose_name="relances recouvrement par SMS (stub)",
            ),
        ),
        migrations.AlterField(
            model_name="notificationlog",
            name="kind",
            field=models.CharField(
                choices=[
                    ("STEP", "Action à effectuer"),
                    ("COMPLETION", "Fin de circuit"),
                    ("REJECTION", "Rejet"),
                    ("RETURN", "Renvoi"),
                    ("COLLECTION_REMINDER", "Relance recouvrement"),
                ],
                max_length=20,
            ),
        ),
    ]
