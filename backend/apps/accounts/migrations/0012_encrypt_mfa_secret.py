"""Chiffre au repos les secrets TOTP existants et les nouveaux secrets."""
from django.db import migrations, models


def encrypt_existing_secrets(apps, schema_editor):
    from apps.common.secret_crypto import encrypt_str

    User = apps.get_model("accounts", "User")
    db = schema_editor.connection.alias
    for user in User.objects.using(db).only("pk", "mfa_secret_encrypted").iterator():
        value = user.mfa_secret_encrypted
        if value:
            user.mfa_secret_encrypted = encrypt_str(value)
            user.save(using=db, update_fields=["mfa_secret_encrypted"])


def decrypt_existing_secrets(apps, schema_editor):
    from apps.common.secret_crypto import decrypt_str

    User = apps.get_model("accounts", "User")
    db = schema_editor.connection.alias
    for user in User.objects.using(db).only("pk", "mfa_secret_encrypted").iterator():
        value = user.mfa_secret_encrypted
        if value:
            user.mfa_secret_encrypted = decrypt_str(value)
            user.save(using=db, update_fields=["mfa_secret_encrypted"])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0011_provision_business_capabilities")]

    operations = [
        migrations.RenameField(
            model_name="user",
            old_name="mfa_secret",
            new_name="mfa_secret_encrypted",
        ),
        migrations.AlterField(
            model_name="user",
            name="mfa_secret_encrypted",
            field=models.CharField(
                blank=True,
                help_text="Secret TOTP chiffré au repos (vide si MFA inactif).",
                max_length=256,
                verbose_name="secret TOTP",
            ),
        ),
        migrations.RunPython(encrypt_existing_secrets, decrypt_existing_secrets),
    ]
