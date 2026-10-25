"""Crée le réseau d'agences standard pour une (ou toutes les) filiale(s)."""
from django.core.management.base import BaseCommand

from apps.common.tenancy import tenant_context
from apps.tenants.models import Agency, Tenant

AGENCIES = [
    ("PTE", "Agence Point E", "Dakar"),
    ("VDN", "Agence VDN", "Dakar"),
    ("LMG", "Agence Lamine Gueye", "Dakar"),
    ("KMR", "Agence Keur Massar", "Dakar"),
    ("KLK", "Agence KAOLACK", "Kaolack"),
    ("TBA", "Agence Touba", "Diourbel"),
]


class Command(BaseCommand):
    help = "Crée les agences standard (Point E, VDN, Lamine Gueye, Keur Massar, Kaolack, Touba)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant",
            dest="tenant_code",
            help="Code de la filiale ciblée. Par défaut : toutes les filiales actives.",
        )

    def handle(self, *args, **options):
        code = options.get("tenant_code")
        tenants = (
            Tenant.objects.filter(code=code)
            if code
            else Tenant.objects.filter(is_active=True)
        )
        if not tenants:
            self.stdout.write(self.style.WARNING("Aucune filiale trouvée."))
            return

        for tenant in tenants:
            with tenant_context(tenant.id):
                for ag_code, name, region in AGENCIES:
                    _, created = Agency.objects.get_or_create(
                        tenant=tenant,
                        code=ag_code,
                        defaults={"name": name, "region": region},
                    )
                    tag = "créée" if created else "existe déjà"
                    self.stdout.write(f"  [{tenant.code}] {name} — {tag}")

        self.stdout.write(self.style.SUCCESS("Agences standard synchronisées."))
