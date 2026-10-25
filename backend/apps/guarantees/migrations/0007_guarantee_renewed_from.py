# Generated manually for guarantee renewal (renewed_from + RENEWAL movement)

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("guarantees", "0006_release_dation_requests"),
    ]

    operations = [
        migrations.AddField(
            model_name="guarantee",
            name="renewed_from",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Si renseigné, cette garantie a été créée par reconduction "
                    "d'une garantie antérieure du client."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="renewals",
                to="guarantees.guarantee",
                verbose_name="garantie d'origine (reconduction)",
            ),
        ),
        migrations.AlterField(
            model_name="guaranteemovement",
            name="movement_type",
            field=models.CharField(
                choices=[
                    ("REVALUATION", "Réévaluation"),
                    ("RELEASE", "Mainlevée"),
                    ("REALIZATION", "Réalisation"),
                    ("TRANSFER", "Transfert"),
                    ("RENEWAL", "Reconduction"),
                ],
                max_length=20,
            ),
        ),
    ]
