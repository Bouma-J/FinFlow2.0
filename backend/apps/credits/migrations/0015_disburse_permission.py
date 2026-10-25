from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0014_financialanalysis_chemicals_pesticides_and_more"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="creditapplication",
            options={
                "ordering": ["-created_at"],
                "permissions": [
                    (
                        "disburse_creditapplication",
                        "Peut décaisser un dossier de crédit approuvé",
                    )
                ],
                "verbose_name": "dossier de crédit",
                "verbose_name_plural": "dossiers de crédit",
            },
        ),
    ]
