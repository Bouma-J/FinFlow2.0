# Generated manually for Document soft-delete fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0003_document_origin_key"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="is_deleted",
            field=models.BooleanField(
                db_index=True, default=False, verbose_name="supprimé"
            ),
        ),
        migrations.AddField(
            model_name="document",
            name="deleted_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                null=True,
                verbose_name="supprimé le",
            ),
        ),
    ]
