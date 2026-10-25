from django.db import migrations


def grant_permissions(apps, schema_editor):
    db = schema_editor.connection.alias
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    TenantRole = apps.get_model("accounts", "TenantRole")
    ct, _ = ContentType.objects.using(db).get_or_create(app_label="configuration", model="configurationprofile")
    specifications = {
        "view_configurationprofile": "Can view configuration profile",
        "add_configurationprofile": "Can add configuration profile",
        "change_configurationprofile": "Can change configuration profile",
        "delete_configurationprofile": "Can delete configuration profile",
        "publish_configurationprofile": "Peut publier et retirer une configuration métier",
        "preview_configurationprofile": "Peut simuler une configuration métier",
    }
    permissions = []
    for codename, name in specifications.items():
        permission, _ = Permission.objects.using(db).get_or_create(
            content_type=ct, codename=codename, defaults={"name": name})
        permissions.append(permission)
    for role in TenantRole.objects.using(db).filter(name="Administrateur filiale").select_related("group"):
        role.group.permissions.add(*permissions)


class Migration(migrations.Migration):
    dependencies = [("configuration", "0001_initial"), ("accounts", "0009_credit_setup_roles")]
    operations = [migrations.RunPython(grant_permissions, migrations.RunPython.noop)]
