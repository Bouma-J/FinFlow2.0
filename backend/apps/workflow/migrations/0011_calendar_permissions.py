from django.db import migrations


def grant_permissions(apps, schema_editor):
    db = schema_editor.connection.alias
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    TenantRole = apps.get_model("accounts", "TenantRole")
    ct, _ = ContentType.objects.using(db).get_or_create(app_label="workflow", model="businesscalendar")
    permissions = []
    for action in ("view", "add", "change", "delete"):
        permission, _ = Permission.objects.using(db).get_or_create(
            content_type=ct, codename=f"{action}_businesscalendar",
            defaults={"name": f"Can {action} business calendar"},
        )
        permissions.append(permission)
    for role in TenantRole.objects.using(db).filter(name="Administrateur filiale").select_related("group"):
        role.group.permissions.add(*permissions)


class Migration(migrations.Migration):
    dependencies = [("workflow", "0010_configurable_committees_and_calendars"), ("accounts", "0009_credit_setup_roles")]
    operations = [migrations.RunPython(grant_permissions, migrations.RunPython.noop)]
