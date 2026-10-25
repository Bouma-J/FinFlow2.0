import uuid

import django.db.models.deletion
from django.db import migrations, models


DEFAULT_TRANCHES = (
    (1, "Gestionnaire", 1, 30, "GESTIONNAIRE"),
    (2, "Service recouvrement", 31, 90, "COLLECTION"),
    (3, "Juridique", 91, None, "LEGAL"),
)


def seed_default_tranches(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    CollectionTranche = apps.get_model("collections", "CollectionTranche")
    CollectionCase = apps.get_model("collections", "CollectionCase")
    for tenant in Tenant.objects.all():
        if CollectionTranche.objects.filter(tenant=tenant).exists():
            continue
        created = []
        for position, name, min_days, max_days, owner in DEFAULT_TRANCHES:
            created.append(
                CollectionTranche.objects.create(
                    tenant=tenant,
                    position=position,
                    name=name,
                    min_days_overdue=min_days,
                    max_days_overdue=max_days,
                    owner_kind=owner,
                    is_active=True,
                )
            )
        cases = CollectionCase.objects.filter(tenant=tenant).exclude(stage="CLOSED")
        for case in cases:
            days = case.days_overdue or 0
            match = None
            for tranche in reversed(created):
                if days < tranche.min_days_overdue:
                    continue
                if (
                    tranche.max_days_overdue is not None
                    and days > tranche.max_days_overdue
                ):
                    continue
                match = tranche
                break
            if match is not None:
                case.tranche = match
                case.save(update_fields=["tranche"])


def unseed_tranches(apps, schema_editor):
    CollectionTranche = apps.get_model("collections", "CollectionTranche")
    CollectionTranche.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("collections", "0007_alter_litigationfile_options_and_more"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CollectionTranche",
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
                ("position", models.PositiveSmallIntegerField(verbose_name="n° de tranche")),
                ("name", models.CharField(max_length=100, verbose_name="libellé")),
                (
                    "min_days_overdue",
                    models.PositiveIntegerField(verbose_name="retard minimum (jours)"),
                ),
                (
                    "max_days_overdue",
                    models.PositiveIntegerField(
                        blank=True,
                        help_text="Laisser vide pour la dernière tranche (sans plafond).",
                        null=True,
                        verbose_name="retard maximum (jours)",
                    ),
                ),
                (
                    "owner_kind",
                    models.CharField(
                        choices=[
                            ("GESTIONNAIRE", "Gestionnaire"),
                            ("COLLECTION", "Service recouvrement"),
                            ("LEGAL", "Juridique"),
                        ],
                        default="GESTIONNAIRE",
                        max_length=20,
                        verbose_name="responsable",
                    ),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="active")),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(app_label)s_%(class)s_set",
                        to="tenants.tenant",
                        verbose_name="filiale",
                    ),
                ),
            ],
            options={
                "verbose_name": "tranche de recouvrement",
                "verbose_name_plural": "tranches de recouvrement",
                "ordering": ["position", "min_days_overdue"],
            },
        ),
        migrations.AddConstraint(
            model_name="collectiontranche",
            constraint=models.UniqueConstraint(
                fields=("tenant", "position"),
                name="unique_collection_tranche_position",
            ),
        ),
        migrations.AddConstraint(
            model_name="collectiontranche",
            constraint=models.UniqueConstraint(
                fields=("tenant", "min_days_overdue"),
                name="unique_collection_tranche_min_days",
            ),
        ),
        migrations.AddField(
            model_name="collectioncase",
            name="tranche",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="cases",
                to="collections.collectiontranche",
                verbose_name="tranche de recouvrement",
            ),
        ),
        migrations.RunPython(seed_default_tranches, unseed_tranches),
    ]
