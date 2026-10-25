from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0002_tenant_branding"),
    ]

    operations = [
        migrations.AddField(
            model_name="agency",
            name="manager_last_name",
            field=models.CharField(
                blank=True, max_length=100, verbose_name="nom du chef d'agence"
            ),
        ),
        migrations.AddField(
            model_name="agency",
            name="manager_first_name",
            field=models.CharField(
                blank=True, max_length=100, verbose_name="prénom du chef d'agence"
            ),
        ),
        migrations.AddField(
            model_name="agency",
            name="manager_phone",
            field=models.CharField(
                blank=True, max_length=50, verbose_name="téléphone du chef d'agence"
            ),
        ),
        migrations.CreateModel(
            name="TenantOfficer",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, db_index=True, verbose_name="créé le"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="modifié le"),
                ),
                (
                    "title",
                    models.CharField(max_length=150, verbose_name="intitulé du poste"),
                ),
                ("last_name", models.CharField(max_length=100, verbose_name="nom")),
                (
                    "first_name",
                    models.CharField(blank=True, max_length=100, verbose_name="prénom"),
                ),
                (
                    "phone",
                    models.CharField(blank=True, max_length=50, verbose_name="téléphone"),
                ),
                (
                    "ordering",
                    models.PositiveSmallIntegerField(default=0, verbose_name="ordre"),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="officers",
                        to="tenants.tenant",
                        verbose_name="filiale",
                    ),
                ),
            ],
            options={
                "verbose_name": "responsable de filiale",
                "verbose_name_plural": "responsables de filiale",
                "ordering": ["ordering", "created_at"],
            },
        ),
    ]
