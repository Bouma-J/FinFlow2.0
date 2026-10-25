from django.db import migrations, models
import apps.sureties.models


class Migration(migrations.Migration):

    dependencies = [
        ("sureties", "0004_surety_agency_authored"),
    ]

    operations = [
        migrations.AddField(
            model_name="surety",
            name="company_name",
            field=models.CharField(
                blank=True, max_length=255, verbose_name="raison sociale"
            ),
        ),
        migrations.AddField(
            model_name="surety",
            name="legal_form",
            field=models.CharField(
                blank=True,
                choices=[
                    ("SARL", "SARL"),
                    ("SA", "SA"),
                    ("ASSOCIATION", "Association"),
                    ("INDIVIDUAL", "Entreprise individuelle"),
                    ("SASU", "SASU"),
                    ("SAS", "SAS"),
                    ("EURL", "EURL"),
                    ("SNC_SCS", "SNC / SCS"),
                ],
                max_length=20,
                verbose_name="statut juridique",
            ),
        ),
        migrations.AddField(
            model_name="surety",
            name="ifu",
            field=models.CharField(
                blank=True, max_length=50, verbose_name="numéro IFU"
            ),
        ),
        migrations.AddField(
            model_name="surety",
            name="rccm",
            field=models.CharField(
                blank=True, max_length=50, verbose_name="numéro RCCM"
            ),
        ),
        migrations.AddField(
            model_name="surety",
            name="ifu_scan",
            field=models.FileField(
                blank=True,
                max_length=255,
                upload_to=apps.sureties.models.surety_file_path,
                verbose_name="scan IFU",
            ),
        ),
        migrations.AddField(
            model_name="surety",
            name="rccm_scan",
            field=models.FileField(
                blank=True,
                max_length=255,
                upload_to=apps.sureties.models.surety_file_path,
                verbose_name="scan RCCM",
            ),
        ),
        migrations.AddField(
            model_name="surety",
            name="city",
            field=models.CharField(
                blank=True, max_length=100, verbose_name="ville"
            ),
        ),
        migrations.AddField(
            model_name="surety",
            name="manager_last_name",
            field=models.CharField(
                blank=True, max_length=100, verbose_name="nom du gérant"
            ),
        ),
        migrations.AddField(
            model_name="surety",
            name="manager_first_name",
            field=models.CharField(
                blank=True, max_length=100, verbose_name="prénom du gérant"
            ),
        ),
        migrations.AddField(
            model_name="surety",
            name="manager_phone",
            field=models.CharField(
                blank=True, max_length=50, verbose_name="téléphone du gérant"
            ),
        ),
        migrations.AddField(
            model_name="surety",
            name="manager_email",
            field=models.EmailField(
                blank=True, max_length=254, verbose_name="email du gérant"
            ),
        ),
        migrations.AddField(
            model_name="surety",
            name="manager_address",
            field=models.CharField(
                blank=True, max_length=255, verbose_name="adresse du gérant"
            ),
        ),
        migrations.AddField(
            model_name="surety",
            name="manager_id_document_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("CNI", "Carte nationale d'identité"),
                    ("PASSPORT", "Passeport"),
                    ("DRIVING_LICENSE", "Permis de conduire"),
                    ("CONSULAR_CARD", "Carte consulaire"),
                ],
                max_length=20,
                verbose_name="type de pièce du gérant",
            ),
        ),
        migrations.AddField(
            model_name="surety",
            name="manager_id_document_number",
            field=models.CharField(
                blank=True, max_length=50, verbose_name="n° de pièce du gérant"
            ),
        ),
        migrations.AddField(
            model_name="surety",
            name="manager_id_document_issue_date",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="date d'établissement de la pièce du gérant",
            ),
        ),
        migrations.AddField(
            model_name="surety",
            name="manager_id_document_expiry_date",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="date d'expiration de la pièce du gérant",
            ),
        ),
        migrations.AddField(
            model_name="surety",
            name="manager_id_document_scan",
            field=models.FileField(
                blank=True,
                max_length=255,
                upload_to=apps.sureties.models.surety_file_path,
                verbose_name="scan pièce du gérant",
            ),
        ),
        migrations.AddField(
            model_name="surety",
            name="manager_position",
            field=models.CharField(
                blank=True,
                max_length=150,
                verbose_name="poste du gérant dans l'entreprise",
            ),
        ),
        migrations.AddField(
            model_name="surety",
            name="manager_birth_date",
            field=models.DateField(
                blank=True, null=True, verbose_name="date de naissance du gérant"
            ),
        ),
        migrations.AddField(
            model_name="surety",
            name="manager_birth_country",
            field=models.CharField(
                blank=True, max_length=100, verbose_name="pays de naissance du gérant"
            ),
        ),
        migrations.AddField(
            model_name="surety",
            name="manager_birth_city",
            field=models.CharField(
                blank=True, max_length=100, verbose_name="ville de naissance du gérant"
            ),
        ),
        migrations.AlterField(
            model_name="surety",
            name="identifier",
            field=models.CharField(
                blank=True,
                help_text="Conservé pour compatibilité ; préférer rccm pour les entreprises.",
                max_length=100,
                verbose_name="pièce / RCCM (legacy)",
            ),
        ),
    ]
