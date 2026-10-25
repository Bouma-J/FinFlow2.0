from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("guarantees", "0012_release_enrichment"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dationrequest",
            name="cbs_currency",
            field=models.CharField(blank=True, default="XOF", max_length=3),
        ),
        migrations.AlterField(
            model_name="guaranteereleaserequest",
            name="cbs_currency",
            field=models.CharField(blank=True, default="XOF", max_length=3),
        ),
    ]
