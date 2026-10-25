# Allow display-name From headers (e.g. FIN_FLOW <noreply@x.com>)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0002_tenant_smtp_settings"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tenantnotificationsettings",
            name="from_email",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Adresse ou forme « Nom <adresse@domaine> ». "
                    "Si vide, utilise l'identifiant SMTP ou DEFAULT_FROM_EMAIL."
                ),
                max_length=255,
                verbose_name="expéditeur (From)",
            ),
        ),
    ]
