"""Crée uniquement des exemples en brouillon, sans changer la politique active."""
from django.core.management.base import BaseCommand, CommandError

from apps.configuration.models import ConfigurationProfile
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Prépare deux profils salarié et AGR en brouillon pour une filiale."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="Code de la filiale")

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(code=options["tenant"]).first()
        if not tenant:
            raise CommandError("Filiale introuvable.")
        presets = [
            ("salarie", "Crédit salarié — exemple", "SALARIE", {
                "policy": {"match_product_client_type": True, "risk_mode": "CONSERVATIVE"},
                "thresholds": {},
                "analysis": {"required_fields": ["salary_verified", "analysis_date"],
                             "minimum_bank_statement_months": 3},
            }),
            ("agr", "Crédit AGR — exemple", "INDEPENDANT", {
                "policy": {"require_field_visit": True, "risk_mode": "CONSERVATIVE"},
                "thresholds": {},
                "analysis": {"required_fields": ["field_visit_confirmed", "analysis_date"],
                             "required_detail_tables": ["products", "stocks", "debts", "cashflow"]},
            }),
        ]
        from apps.configuration.catalog import validate_overrides

        for code, name, profile, overrides in presets:
            # Une série déjà présente n'est jamais écrasée.
            if ConfigurationProfile.all_tenants.filter(tenant=tenant, code=code).exists():
                self.stdout.write(f"Conservé : {code}")
                continue
            ConfigurationProfile.all_tenants.create(
                tenant=tenant, code=code, name=name, client_type="INDIVIDUAL",
                individual_profile=profile, overrides=validate_overrides(overrides),
                reason="Exemple à adapter et à valider par l'établissement avant publication.",
            )
            self.stdout.write(f"Brouillon créé : {code}")
