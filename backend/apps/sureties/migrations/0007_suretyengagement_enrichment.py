# Generated manually for surety engagement enrichment

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sureties", "0006_surety_documents"),
        ("contracts", "0002_generatedcontract_surety_engagement"),
    ]

    operations = [
        migrations.AddField(
            model_name="suretyengagement",
            name="called_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="appelé le"
            ),
        ),
        migrations.AddField(
            model_name="suretyengagement",
            name="engagement_type",
            field=models.CharField(
                choices=[
                    ("SIMPLE", "Caution simple"),
                    ("SOLIDAIRE", "Caution solidaire"),
                ],
                db_index=True,
                default="SOLIDAIRE",
                max_length=20,
                verbose_name="type d'engagement",
            ),
        ),
        migrations.AddField(
            model_name="suretyengagement",
            name="notes",
            field=models.TextField(
                blank=True, verbose_name="observations"
            ),
        ),
        migrations.AddField(
            model_name="suretyengagement",
            name="released_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="libéré le"
            ),
        ),
    ]
