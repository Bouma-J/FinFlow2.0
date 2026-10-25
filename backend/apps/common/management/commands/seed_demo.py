"""
Jeu de données de démonstration FIN_FLOW.

Crée : un administrateur Groupe, une filiale de démonstration avec son
administrateur, des rôles, un produit de crédit, un circuit d'approbation
à deux niveaux, un connecteur Core Banking et un client.

Avec --rich (défaut) : clients, dossiers, garanties, formalisations,
mains levées, dations et dossiers de recouvrement pour usage local.

Avec --volume : dizaines d'enregistrements liés (préfixe BULK-) pour tester
les listes et le scroll.

Usage :
    python manage.py seed_demo
    python manage.py seed_demo --no-rich
    python manage.py seed_demo --volume
    python manage.py seed_demo --volume --count 50
    python manage.py seed_demo --full
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import User
from apps.catalog.models import CreditProduct, ProductCategory
from apps.clients.models import Client
from apps.accounts.services import get_or_create_tenant_role
from apps.common.demo_bulk import seed_bulk_operational_data
from apps.common.demo_params import seed_demo_parametrage
from apps.common.demo_rich import seed_rich_operational_data
from apps.common.tenancy import tenant_context
from apps.corebanking.models import CoreBankingConnector
from apps.corebanking.perfect_defaults import ensure_perfect_connector, perfect_connector_defaults
from apps.tenants.models import Agency, Tenant
from apps.workflow.models import ApprovalStep, WorkflowDefinition


class Command(BaseCommand):
    help = "Crée un jeu de données de démonstration."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-rich",
            action="store_true",
            help="Ne crée que le socle minimal (sans dossiers / garanties).",
        )
        parser.add_argument(
            "--volume",
            action="store_true",
            help=(
                "Ajoute un volume bulk lié (clients, dossiers, analyses, "
                "garanties, cautions, prêts, recouvrement, GED)."
            ),
        )
        parser.add_argument(
            "--full",
            action="store_true",
            help=(
                "Jeu complet : paramétrage (circuits multi-critères, catalogue) "
                "+ rich + volume (défaut 80 / module)."
            ),
        )
        parser.add_argument(
            "--count",
            type=int,
            default=40,
            help="Nombre d'enregistrements par module pour --volume (défaut: 40).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        # --- Administrateur Groupe ---
        group_admin, created = User.objects.get_or_create(
            username="group_admin",
            defaults={
                "email": "group.admin@finflow.local",
                "is_group_level": True,
                "is_staff": True,
                "is_superuser": True,
                "first_name": "Admin",
                "last_name": "Groupe",
                "must_change_password": False,
            },
        )
        if created:
            group_admin.set_password("FinFlow2026!")
            group_admin.save()
            self.stdout.write(self.style.SUCCESS("Administrateur Groupe créé."))
        else:
            if group_admin.must_change_password:
                group_admin.must_change_password = False
                group_admin.save(update_fields=["must_change_password"])

        # --- Filiale de démonstration ---
        tenant, _ = Tenant.objects.get_or_create(
            code="FIL01",
            defaults={
                "name": "Filiale Démo Crédit",
                "country": "Côte d'Ivoire",
                "zone": "UEMOA",
                "currency": "XOF",
            },
        )

        # --- Rôles filiale (packs bootstrap) ---
        from apps.accounts.services import (
            ANALYSTE_CREDIT_RISQUE_ROLE_NAME,
            CHEF_AGENCE_ROLE_NAME,
            CREDIT_COMMITTEE_FILIALE_ROLE_NAME,
            CREDIT_COMMITTEE_GROUP_ROLE_NAME,
            ensure_filiale_admin_role,
            ensure_group_credit_committee_role,
            provision_filiale_admin,
        )
        from apps.tenants.services import bootstrap_tenant

        bootstrap_tenant(tenant)

        with tenant_context(tenant.id):
            analyst_role, _ = get_or_create_tenant_role(
                tenant, ANALYSTE_CREDIT_RISQUE_ROLE_NAME
            )
            manager_role, _ = get_or_create_tenant_role(
                tenant, CHEF_AGENCE_ROLE_NAME
            )
            committee_role, _ = get_or_create_tenant_role(
                tenant, CREDIT_COMMITTEE_FILIALE_ROLE_NAME
            )
            committee_group_role, _ = get_or_create_tenant_role(
                tenant, CREDIT_COMMITTEE_GROUP_ROLE_NAME
            )
            ensure_filiale_admin_role(tenant)
            ensure_group_credit_committee_role()

        # --- Administrateur filiale ---
        with tenant_context(tenant.id):
            agency, _ = Agency.objects.get_or_create(
                tenant=tenant, code="AG01",
                defaults={"name": "Agence Centrale", "region": "Abidjan"},
            )

        # Ne réapplique le mot de passe que si le compte n'existe pas encore
        # (évite UserAttributeSimilarityValidator vs email contenant « finflow »).
        fil_admin_exists = User.objects.filter(username="fil01_admin").exists()
        fil_admin, created = provision_filiale_admin(
            tenant=tenant,
            agency=agency,
            username="fil01_admin",
            password=None if fil_admin_exists else "FinFlow2026!",
            email="admin@fil01.demo.local",
            first_name="Admin",
            last_name="Filiale01",
            send_credentials=False,
            must_change_password=False,
        )
        if fil_admin_exists and fil_admin.must_change_password:
            fil_admin.must_change_password = False
            fil_admin.save(update_fields=["must_change_password"])
        from apps.common.demo_users import ensure_demo_business_users

        ensure_demo_business_users(tenant, agency)
        if created:
            self.stdout.write(self.style.SUCCESS("Administrateur filiale créé."))

        # Les objets scopés sont créés dans le contexte de la filiale
        run_volume = False
        volume_count = options["count"]
        with tenant_context(tenant.id):

            category, _ = ProductCategory.objects.get_or_create(
                tenant=tenant, code="TRESO",
                defaults={"label": "Crédit de trésorerie"},
            )
            product, _ = CreditProduct.objects.get_or_create(
                tenant=tenant, code="TRESO-STD",
                defaults={
                    "label": "Trésorerie standard",
                    "category": category,
                    "currency": "XOF",
                    "amount_min": Decimal("100000"),
                    "amount_max": Decimal("50000000"),
                    "duration_min_months": 3,
                    "duration_max_months": 36,
                    "interest_rate": Decimal("12.5"),
                    "cbs_product_code": "CRED-TRESO",
                    "cbs_repayment_product_code": "COMPTE-COURANT",
                },
            )
            if not product.cbs_product_code:
                product.cbs_product_code = "CRED-TRESO"
                product.cbs_repayment_product_code = (
                    product.cbs_repayment_product_code or "COMPTE-COURANT"
                )
                product.save(
                    update_fields=[
                        "cbs_product_code",
                        "cbs_repayment_product_code",
                        "updated_at",
                    ]
                )

            definition, created_def = WorkflowDefinition.objects.get_or_create(
                tenant=tenant, code="CIRCUIT-STD", version=1,
                defaults={"name": "Circuit standard crédit", "is_active": True},
            )
            if created_def:
                ApprovalStep.objects.create(
                    tenant=tenant, definition=definition,
                    name="Analyse crédit", order=1,
                    required_group=analyst_role, sla_hours=48,
                    step_kind=ApprovalStep.StepKind.CONSULTATIVE,
                )
                # Décisionnelle : agence sous 10 M ; comité filiale dès 10 M ;
                # comité groupe dès 50 M (en plus du comité filiale).
                ApprovalStep.objects.create(
                    tenant=tenant, definition=definition, name="Validation agence",
                    order=2, required_group=manager_role, sla_hours=24,
                    max_amount=Decimal("10000000"),
                    step_kind=ApprovalStep.StepKind.DECISIONAL,
                )
                ApprovalStep.objects.create(
                    tenant=tenant,
                    definition=definition,
                    name="Comité de crédit filiale",
                    order=3,
                    required_group=committee_role,
                    sla_hours=72,
                    min_amount=Decimal("10000000"),
                    step_kind=ApprovalStep.StepKind.DECISIONAL,
                )
                ApprovalStep.objects.create(
                    tenant=tenant,
                    definition=definition,
                    name="Comité de crédit groupe",
                    order=4,
                    required_group=committee_group_role,
                    sla_hours=96,
                    min_amount=Decimal("50000000"),
                    step_kind=ApprovalStep.StepKind.DECISIONAL,
                )
            else:
                # Reprise des bases de démonstration créées avant la correction
                # du type de l'étape agence.
                ApprovalStep.objects.filter(
                    definition=definition,
                    name="Validation agence",
                    step_kind=ApprovalStep.StepKind.CONSULTATIVE,
                ).update(step_kind=ApprovalStep.StepKind.DECISIONAL)

            dation_def, created_dation = WorkflowDefinition.objects.get_or_create(
                tenant=tenant,
                code="CIRCUIT-DATION",
                version=1,
                defaults={
                    "name": "Circuit dation en paiement",
                    "target_type": WorkflowDefinition.TargetType.DATION,
                    "is_active": True,
                },
            )
            if created_dation:
                ApprovalStep.objects.create(
                    tenant=tenant,
                    definition=dation_def,
                    name="Validation dation",
                    order=1,
                    required_group=manager_role,
                    sla_hours=48,
                    step_kind=ApprovalStep.StepKind.DECISIONAL,
                )
            elif dation_def.target_type != WorkflowDefinition.TargetType.DATION:
                dation_def.target_type = WorkflowDefinition.TargetType.DATION
                dation_def.is_active = True
                dation_def.save(update_fields=["target_type", "is_active", "updated_at"])

            release_def, created_release = WorkflowDefinition.objects.get_or_create(
                tenant=tenant,
                code="CIRCUIT-MAIN-LEVEE",
                version=1,
                defaults={
                    "name": "Circuit main levée",
                    "target_type": WorkflowDefinition.TargetType.MAIN_LEVEE,
                    "is_active": True,
                },
            )
            if created_release:
                ApprovalStep.objects.create(
                    tenant=tenant,
                    definition=release_def,
                    name="Validation main levée",
                    order=1,
                    required_group=manager_role,
                    sla_hours=48,
                    step_kind=ApprovalStep.StepKind.DECISIONAL,
                )

            defaults = perfect_connector_defaults(
                demo=True, base_url="https://cbs.fil01.local/api"
            )
            demo_connector, _ = CoreBankingConnector.objects.get_or_create(
                tenant=tenant,
                name="CBS Filiale 01",
                defaults=defaults,
            )
            # Le bootstrap a pu créer le connecteur technique par défaut.
            # La démo doit utiliser un seul connecteur actif explicitement simulé.
            from apps.corebanking.perfect_defaults import DEFAULT_CONNECTOR_NAME

            for placeholder in CoreBankingConnector.objects.filter(name=DEFAULT_CONNECTOR_NAME, is_active=True).exclude(pk=demo_connector.pk):
                placeholder.is_active = False
                placeholder.save(update_fields=["is_active", "updated_at"])
            # Complète endpoints Perfect si le connecteur existait déjà.
            ensure_perfect_connector(tenant, demo=True, name="CBS Filiale 01")

            # Paramétrage : produits, motifs, parties, circuits multi-critères
            seed_demo_parametrage(tenant=tenant, stdout=self.stdout)

            Client.objects.get_or_create(
                tenant=tenant, reference="CLI-0001",
                defaults={
                    "client_type": Client.ClientType.INDIVIDUAL,
                    "first_name": "Awa", "last_name": "Koné",
                    "phone": "+22500000000", "agency": agency,
                    "kyc_status": Client.KycStatus.VALIDATED,
                },
            )

            run_rich = not options["no_rich"]
            run_volume = options["volume"] or options["full"]
            volume_count = options["count"]
            if options["full"] and volume_count == 40:
                volume_count = 80
            if run_volume:
                volume_count = max(20, min(int(volume_count), 120))

            if run_rich:
                seed_rich_operational_data(
                    tenant=tenant,
                    agency=agency,
                    product=product,
                    user=fil_admin,
                    stdout=self.stdout,
                )

            if run_volume:
                seed_bulk_operational_data(
                    tenant=tenant,
                    agency=agency,
                    product=product,
                    user=fil_admin,
                    count=volume_count,
                    stdout=self.stdout,
                )

            if run_rich or run_volume:
                # Les widgets dépendent des dossiers et prêts des deux seeds.
                # Les générer une seule fois, une fois le portefeuille complet.
                from apps.common.demo_bulk import seed_collection_list_widgets

                seed_collection_list_widgets(
                    tenant=tenant, user=fil_admin, stdout=self.stdout, limit=20
                )

        self.stdout.write(self.style.SUCCESS(
            "Données de démonstration créées.\n"
            "  - Admin Groupe : group_admin / FinFlow2026!\n"
            "  - Admin Filiale : fil01_admin / FinFlow2026!"
            + (
                f"\n  - Volume bulk : ~{volume_count if run_volume else 0} "
                f"enregistrements / module"
                if run_volume
                else ""
            )
            + (
                "\n  - Circuits crédit multi-critères + catalogue enrichi"
                if True
                else ""
            )
        ))
