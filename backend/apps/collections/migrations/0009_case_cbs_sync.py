from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("collections", "0008_collection_tranches"),
    ]

    operations = [
        migrations.AddField(
            model_name="collectioncase",
            name="cbs_synced_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="dernière synchro CBS"
            ),
        ),
        migrations.AddField(
            model_name="collectioncase",
            name="cbs_sync_error",
            field=models.CharField(
                blank=True, max_length=255, verbose_name="erreur synchro CBS"
            ),
        ),
    ]
