from django.db import migrations


def provision(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    TenantRole = apps.get_model("accounts", "TenantRole")
    permissions = {}
    for model in ("borrowergroup", "creditexposureobservation"):
        ct, _ = ContentType.objects.get_or_create(app_label="credits", model=model)
        actions = ["add", "view", "change", "delete"]
        if model == "creditexposureobservation":
            actions.append("verify")
        for action in actions:
            codename = f"{action}_{model}"
            permissions[codename], _ = Permission.objects.get_or_create(content_type=ct, codename=codename, defaults={"name": f"Can {action} {model}"})
    for role in TenantRole.objects.select_related("group"):
        selected = []
        if role.pack_code == "tenant_admin":
            selected = list(permissions)
        elif role.pack_code == "credit_admin":
            selected = ["view_borrowergroup", "view_creditexposureobservation", "verify_creditexposureobservation", "add_creditexposureobservation", "change_creditexposureobservation"]
        elif role.pack_code in {"relationship_manager", "credit_analyst", "credit_risk_manager"}:
            selected = ["view_creditexposureobservation", "add_creditexposureobservation", "change_creditexposureobservation", "view_borrowergroup"]
        role.group.permissions.add(*(permissions[code] for code in selected))


class Migration(migrations.Migration):
    dependencies = [("credits", "0036_financialanalysis_custom_fields_borrowergroup_and_more"), ("accounts", "0011_provision_business_capabilities")]
    operations = [migrations.RunPython(provision, migrations.RunPython.noop)]
