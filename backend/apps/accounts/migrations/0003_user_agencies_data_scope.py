import django.db.models.deletion
from django.db import migrations, models


def link_existing_agencies(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Agency = apps.get_model("tenants", "Agency")
    for user in User.objects.filter(is_group_level=False, tenant_id__isnull=False):
        if user.agency_id:
            user.agencies.add(user.agency_id)
        else:
            first = Agency.objects.filter(tenant_id=user.tenant_id).first()
            if first:
                user.agency_id = first.id
                user.save(update_fields=["agency_id"])
                user.agencies.add(first.id)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_tenantrole"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="data_scope",
            field=models.CharField(
                choices=[
                    ("OWN", "Ses propres dossiers"),
                    ("AGENCY", "Son agence"),
                    ("TENANT", "Toute la filiale"),
                ],
                default="AGENCY",
                max_length=10,
                verbose_name="périmètre de données",
            ),
        ),
        migrations.AlterField(
            model_name="user",
            name="agency",
            field=models.ForeignKey(
                blank=True,
                help_text="Agence par défaut pour la création des dossiers.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="primary_users",
                to="tenants.agency",
                verbose_name="agence principale",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="agencies",
            field=models.ManyToManyField(
                blank=True,
                related_name="members",
                to="tenants.agency",
                verbose_name="agences",
            ),
        ),
        migrations.RunPython(link_existing_agencies, migrations.RunPython.noop),
    ]
