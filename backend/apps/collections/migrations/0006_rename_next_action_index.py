from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("collections", "0005_contentieux_v2"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="collectioncase",
            new_name="coll_tenant_next_act_idx",
            old_name="collections_tenant__next_act_idx",
        ),
    ]
