from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0005_alter_approvalcondition_created_at_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workflowdefinition",
            name="target_type",
            field=models.CharField(
                choices=[
                    ("CREDIT", "Dossier de crédit"),
                    ("MAIN_LEVEE", "Main levée"),
                    ("DATION", "Dation en paiement"),
                ],
                default="CREDIT",
                max_length=20,
            ),
        ),
    ]
