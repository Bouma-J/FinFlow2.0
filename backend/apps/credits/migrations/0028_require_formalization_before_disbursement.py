# Generated manually for Fin Flow maturity lot B3

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0027_require_surety_signed_contracts"),
    ]

    operations = [
        migrations.AddField(
            model_name="creditinstructionpolicy",
            name="require_formalization_before_disbursement",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Si activé, les garanties hypothécaires / gages / nantissements "
                    "rattachés au dossier doivent être formalisées (formalized_at) "
                    "avant décaissement. Désactivé par défaut (processus parallèle)."
                ),
                verbose_name="exiger la formalisation des garanties avant décaissement",
            ),
        ),
    ]
