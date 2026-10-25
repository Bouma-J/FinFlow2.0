from django.db import migrations, models

import apps.tenants.models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="logo",
            field=models.ImageField(
                blank=True, max_length=255, upload_to=apps.tenants.models.tenant_logo_upload,
                verbose_name="logo",
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="brand_primary",
            field=models.CharField(
                default="#0f9488",
                help_text="Couleur principale (hex, ex. #0f9488).",
                max_length=7,
                verbose_name="couleur principale",
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="brand_secondary",
            field=models.CharField(
                default="#0d7a72",
                help_text="Couleur secondaire / foncée (hex).",
                max_length=7,
                verbose_name="couleur secondaire",
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="brand_accent",
            field=models.CharField(
                default="#d4a017",
                help_text="Couleur d'accent (hex).",
                max_length=7,
                verbose_name="couleur d'accent",
            ),
        ),
    ]
