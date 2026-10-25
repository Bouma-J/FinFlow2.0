# Generated manually — reporting.view_dashboard

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0001_long_term_snapshots_ged_quota"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="reportingsnapshot",
            options={
                "permissions": [
                    ("view_dashboard", "Consulter le tableau de bord / reporting"),
                ],
                "verbose_name": "snapshot reporting",
                "verbose_name_plural": "snapshots reporting",
            },
        ),
    ]
