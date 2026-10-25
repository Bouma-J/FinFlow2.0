"""Audit des circuits d'approbation : montants sans étape décisionnelle.

Un circuit dont une tranche de montant ne comporte aucune étape décisionnelle
approuve malgré tout les dossiers concernés, sur les seuls avis consultatifs.
Le dossier avance donc normalement, mais personne ne décide formellement.

À exécuter avant toute mise en production :
    python manage.py audit_decision_coverage

Code de sortie 1 dès qu'un circuit est troué, pour usage en garde-fou CI.
"""
from django.core.management.base import BaseCommand

from apps.tenants.models import Tenant
from apps.workflow.models import ApprovalStep, WorkflowDefinition
from apps.workflow.services import compute_decision_gaps, format_decision_gaps


class Command(BaseCommand):
    help = "Liste les circuits laissant des montants sans étape décisionnelle."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant",
            dest="tenant_code",
            help="Restreindre à une filiale (code).",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Auditer aussi les circuits inactifs (en construction).",
        )

    def handle(self, *args, **options):
        tenants = Tenant.objects.all().order_by("code")
        if options.get("tenant_code"):
            tenants = tenants.filter(code=options["tenant_code"])

        total_checked = 0
        flagged = []

        for tenant in tenants:
            definitions = WorkflowDefinition.all_tenants.filter(
                tenant=tenant
            ).order_by("target_type", "code", "-version")
            if not options.get("include_inactive"):
                definitions = definitions.filter(is_active=True)

            for definition in definitions:
                # Les étapes sont passées explicitement : hors contexte tenant,
                # le manager par défaut ne renverrait rien et l'audit
                # conclurait à tort que le circuit est sain.
                steps = list(
                    ApprovalStep.all_tenants.filter(definition=definition)
                )
                total_checked += 1
                gaps = compute_decision_gaps(definition, steps=steps)
                if gaps:
                    flagged.append((tenant, definition, steps, gaps))

        for tenant, definition, steps, gaps in flagged:
            self.stdout.write(
                self.style.ERROR(
                    f"[{tenant.code}] {definition.code} v{definition.version} "
                    f"({definition.get_target_type_display()})"
                )
            )
            self.stdout.write(f"    montants sans décideur : {format_decision_gaps(gaps)}")
            for step in sorted(steps, key=lambda s: s.order):
                bounds = "toutes tranches"
                if step.min_amount is not None or step.max_amount is not None:
                    low = step.min_amount if step.min_amount is not None else "0"
                    high = step.max_amount if step.max_amount is not None else "∞"
                    bounds = f"{low} → {high}"
                self.stdout.write(
                    f"    {step.order}. {step.name} [{step.step_kind}] {bounds}"
                )

        self.stdout.write("")
        if flagged:
            self.stdout.write(
                self.style.ERROR(
                    f"{len(flagged)} circuit(s) troué(s) sur {total_checked} audité(s)."
                )
            )
            raise SystemExit(1)

        self.stdout.write(
            self.style.SUCCESS(
                f"{total_checked} circuit(s) audité(s) : tous les montants "
                "disposent d'une étape décisionnelle."
            )
        )
