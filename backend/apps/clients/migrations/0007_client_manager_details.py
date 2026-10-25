from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0006_client_cbs_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="manager_id_document_issue_date",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="date d'établissement de la pièce du gérant",
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="manager_id_document_expiry_date",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="date d'expiration de la pièce du gérant",
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="manager_position",
            field=models.CharField(
                blank=True,
                max_length=150,
                verbose_name="poste du gérant dans l'entreprise",
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="manager_birth_date",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="date de naissance du gérant",
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="manager_birth_country",
            field=models.CharField(
                blank=True,
                max_length=100,
                verbose_name="pays de naissance du gérant",
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="manager_birth_city",
            field=models.CharField(
                blank=True,
                max_length=100,
                verbose_name="ville de naissance du gérant",
            ),
        ),
    ]
