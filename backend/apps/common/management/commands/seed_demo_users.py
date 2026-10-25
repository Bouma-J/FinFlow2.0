from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.common.demo_users import ensure_demo_business_users
from apps.common.tenancy import tenant_context
from apps.tenants.models import Agency, Tenant


class Command(BaseCommand):
    help = (
        "Crée les acteurs de recette distincts dans la filiale FIL01 de démonstration."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(code="FIL01").first()
        if not tenant:
            raise CommandError(
                "Initialisez d'abord la filiale de démonstration avec seed_demo."
            )
        agency = Agency.objects.filter(tenant=tenant, code="AG01").first()
        if not agency:
            raise CommandError("Agence de démonstration AG01 absente.")
        with tenant_context(tenant.pk):
            created = ensure_demo_business_users(tenant, agency)
        self.stdout.write(
            f"Acteurs de recette créés : {', '.join(created) or 'déjà présents'}. Aucun mot de passe existant modifié."
        )
