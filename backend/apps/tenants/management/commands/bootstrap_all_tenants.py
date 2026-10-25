"""Bootstrap post-déploiement : rôles, catalogue, Perfect, circuits (dont formalisation)."""
from django.core.management.base import BaseCommand

from apps.tenants.models import Tenant
from apps.tenants.services import bootstrap_tenant


class Command(BaseCommand):
    help = (
        "Applique bootstrap_tenant sur toutes les filiales "
        "(packs RBAC, catalogue, connecteur Perfect, circuits ML/Dation/Formalisation)."
    )

    def handle(self, *args, **options):
        tenants = Tenant.objects.order_by("code")
        if not tenants.exists():
            self.stdout.write(
                self.style.WARNING("Aucune filiale — rien à bootstrapper.")
            )
            return
        for tenant in tenants:
            bootstrap_tenant(tenant)
            self.stdout.write(self.style.SUCCESS(f"  {tenant.code} — bootstrap OK"))
        self.stdout.write(
            self.style.SUCCESS(f"{tenants.count()} filiale(s) synchronisée(s).")
        )
