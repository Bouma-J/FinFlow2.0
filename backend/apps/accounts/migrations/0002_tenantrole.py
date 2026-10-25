import uuid

import django.db.models.deletion
from django.db import migrations, models


def link_existing_roles(apps, schema_editor):
    """Rattache les rôles globaux existants à la filiale démo."""
    Tenant = apps.get_model("tenants", "Tenant")
    Group = apps.get_model("auth", "Group")
    TenantRole = apps.get_model("accounts", "TenantRole")

    tenant = Tenant.objects.filter(code="FIL01").first()
    if tenant is None:
        return

    role_names = ["Analyste crédit", "Responsable agence", "Comité de crédit"]
    for name in role_names:
        if TenantRole.objects.filter(tenant=tenant, name=name).exists():
            continue
        group = Group.objects.filter(name=name).first()
        if group is None:
            internal = f"__ff_{tenant.id}__{uuid.uuid4().hex[:12]}"
            group = Group.objects.create(name=internal)
        TenantRole.objects.create(tenant=tenant, name=name, group=group)


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("tenants", "0001_initial"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenantRole",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=150, verbose_name="nom du rôle")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "group",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tenant_role",
                        to="auth.group",
                        verbose_name="groupe Django",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="roles",
                        to="tenants.tenant",
                        verbose_name="filiale",
                    ),
                ),
            ],
            options={
                "verbose_name": "rôle filiale",
                "verbose_name_plural": "rôles filiale",
                "ordering": ["tenant", "name"],
            },
        ),
        migrations.AddConstraint(
            model_name="tenantrole",
            constraint=models.UniqueConstraint(
                fields=("tenant", "name"), name="unique_role_name_per_tenant"
            ),
        ),
        migrations.RunPython(link_existing_roles, migrations.RunPython.noop),
    ]
