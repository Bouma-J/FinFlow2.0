"""Synchronise les packs de permissions des rôles bootstrap sur toutes les filiales."""
from django.core.management.base import BaseCommand

from apps.accounts.services import ensure_default_role_packs
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = (
        "Applique les packs RBAC des rôles bootstrap (20 profils filiale) "
        "sur toutes les filiales existantes. Retire les anciens rôles "
        "inutilisés (Analyste crédit, Responsable agence)."
    )

    def handle(self, *args, **options):
        count = 0
        for tenant in Tenant.objects.all().order_by("code"):
            ensure_default_role_packs(tenant)
            count += 1
            self.stdout.write(self.style.SUCCESS(f"Packs synchronisés — {tenant.code}"))
        self.stdout.write(self.style.SUCCESS(f"{count} filiale(s) traitée(s)."))
