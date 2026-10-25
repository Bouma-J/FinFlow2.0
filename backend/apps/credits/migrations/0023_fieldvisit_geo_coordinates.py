from django.db import migrations, models


def forwards_merge_coords(apps, schema_editor):
    FieldVisit = apps.get_model("credits", "FieldVisit")
    for visit in FieldVisit.objects.all().iterator():
        lat = visit.latitude
        lng = visit.longitude
        if lat is None and lng is None:
            continue
        parts = []
        if lat is not None:
            parts.append(str(lat))
        if lng is not None:
            parts.append(str(lng))
        visit.geo_coordinates = ", ".join(parts)
        visit.save(update_fields=["geo_coordinates"])


def backwards_split_coords(apps, schema_editor):
    FieldVisit = apps.get_model("credits", "FieldVisit")
    for visit in FieldVisit.objects.all().iterator():
        raw = (visit.geo_coordinates or "").strip()
        if not raw:
            continue
        parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
        if len(parts) >= 2:
            try:
                visit.latitude = parts[0]
                visit.longitude = parts[1]
                visit.save(update_fields=["latitude", "longitude"])
            except Exception:  # noqa: BLE001
                continue


class Migration(migrations.Migration):

    dependencies = [
        ("credits", "0022_analysis_groupement_activity_haircuts"),
    ]

    operations = [
        migrations.AddField(
            model_name="fieldvisit",
            name="geo_coordinates",
            field=models.CharField(
                blank=True,
                help_text="Ex. 5.359952, -4.008256 (collé depuis Maps).",
                max_length=120,
                verbose_name="coordonnées géographiques",
            ),
        ),
        migrations.RunPython(forwards_merge_coords, backwards_split_coords),
        migrations.RemoveField(
            model_name="fieldvisit",
            name="latitude",
        ),
        migrations.RemoveField(
            model_name="fieldvisit",
            name="longitude",
        ),
    ]
