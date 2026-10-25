# Generated manually for per-tenant SMTP settings

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tenantnotificationsettings",
            name="from_email",
            field=models.EmailField(
                blank=True,
                help_text="Adresse affichée comme expéditeur. Si vide, utilise DEFAULT_FROM_EMAIL.",
                max_length=254,
                verbose_name="expéditeur (From)",
            ),
        ),
        migrations.AddField(
            model_name="tenantnotificationsettings",
            name="smtp_host",
            field=models.CharField(
                blank=True,
                help_text="Ex. smtp.gmail.com. Si vide, utilise la configuration globale Django.",
                max_length=255,
                verbose_name="serveur SMTP",
            ),
        ),
        migrations.AddField(
            model_name="tenantnotificationsettings",
            name="smtp_port",
            field=models.PositiveIntegerField(
                default=587, verbose_name="port SMTP"
            ),
        ),
        migrations.AddField(
            model_name="tenantnotificationsettings",
            name="smtp_use_tls",
            field=models.BooleanField(
                default=True, verbose_name="TLS (STARTTLS)"
            ),
        ),
        migrations.AddField(
            model_name="tenantnotificationsettings",
            name="smtp_use_ssl",
            field=models.BooleanField(default=False, verbose_name="SSL"),
        ),
        migrations.AddField(
            model_name="tenantnotificationsettings",
            name="smtp_username",
            field=models.CharField(
                blank=True,
                help_text="En général la même adresse que l'expéditeur.",
                max_length=255,
                verbose_name="identifiant SMTP",
            ),
        ),
        migrations.AddField(
            model_name="tenantnotificationsettings",
            name="smtp_password",
            field=models.CharField(
                blank=True,
                help_text="Mot de passe ou « App Password ». Ne jamais exposer en clair côté API lecture.",
                max_length=255,
                verbose_name="mot de passe SMTP",
            ),
        ),
    ]
