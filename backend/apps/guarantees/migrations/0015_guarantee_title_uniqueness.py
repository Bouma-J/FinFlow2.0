from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("guarantees", "0014_guarantee_formalized_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="guarantee",
            name="document_validity_date",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="date de validité du document",
            ),
        ),
        migrations.AddField(
            model_name="guarantee",
            name="expertise_reference",
            field=models.CharField(
                blank=True,
                max_length=100,
                verbose_name="référence du rapport d'expertise",
            ),
        ),
        migrations.AlterField(
            model_name="guarantee",
            name="document_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("LAND_TITLE", "Titre foncier"),
                    ("ATTRIBUTION_CERT", "Attestation d'attribution"),
                    ("EXPLOITATION_PERMIT", "Permis d'exploiter"),
                    ("BUILDING_PERMIT", "Permis de construire"),
                    ("OCCUPANCY_PERMIT", "Permis d'habiter"),
                    ("LEASEHOLD", "Bail emphytéotique"),
                    ("SURFACE_RIGHT", "Droit de superficie"),
                    ("SALES_DEED", "Acte de vente / compromis"),
                    ("CADASTRAL_EXTRACT", "Extrait cadastral"),
                    ("CUSTOMARY_TITLE", "Titre / certificat coutumier"),
                    ("URBAN_CERT", "Certificat d'urbanisme"),
                    ("OTHER_REAL_ESTATE", "Autre titre immobilier"),
                    ("REGISTRATION_CARD", "Carte grise"),
                    ("PURCHASE_INVOICE", "Facture d'achat"),
                    ("CUSTOMS_CLEARANCE", "Déclaration en douane"),
                    ("TRANSFER_CERT", "Certificat de cession"),
                    ("INSURANCE_CERT", "Attestation d'assurance"),
                    ("TECH_INSPECTION", "Visite technique"),
                    ("OTHER_VEHICLE", "Autre document véhicule"),
                ],
                max_length=20,
                verbose_name="type de document",
            ),
        ),
    ]
