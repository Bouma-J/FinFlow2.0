from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0005_alter_tenantnotificationsettings_from_email_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantnotificationsettings",
            name="notify_collection_transfer",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "E-mail aux responsables de la nouvelle tranche lorsqu'un "
                    "dossier de recouvrement y est transmis."
                ),
                verbose_name="alerte transfert de tranche",
            ),
        ),
        migrations.AddField(
            model_name="tenantnotificationsettings",
            name="notify_collection_dialogue",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "E-mail à l'agent affecté et aux responsables de la tranche "
                    "quand un commentaire, une demande ou une recommandation "
                    "est déposé sur le dossier."
                ),
                verbose_name="alerte commentaire / recommandation",
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
                    ("COLLECTION_TRANSFER", "Transfert de tranche"),
                    ("COLLECTION_DIALOGUE", "Dialogue recouvrement"),
                ],
                max_length=20,
            ),
        ),
    ]
