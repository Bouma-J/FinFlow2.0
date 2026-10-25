# Generated manually for must_change_password

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_medium_term_mfa_and_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="must_change_password",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Si vrai, l'utilisateur doit définir un nouveau mot de passe "
                    "après connexion (création ou régénération admin)."
                ),
                verbose_name="doit changer le mot de passe",
            ),
        ),
    ]
