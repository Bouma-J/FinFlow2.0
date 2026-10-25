"""Paramétrage démo : circuits, catalogue, intervenants juridiques."""
from __future__ import annotations

from decimal import Decimal

from apps.accounts.services import (
    ANALYSTE_CREDIT_RISQUE_ROLE_NAME,
    CHEF_AGENCE_ROLE_NAME,
    CREDIT_COMMITTEE_FILIALE_ROLE_NAME,
    CREDIT_COMMITTEE_GROUP_ROLE_NAME,
    RESP_JURIDIQUE_ROLE_NAME,
)
from apps.accounts.services import get_or_create_tenant_role
from apps.catalog.models import (
    ChecklistItem,
    CreditProduct,
    ProductCategory,
    RejectReason,
)
from apps.collections.models import LegalParty
from apps.workflow.models import ApprovalStep, WorkflowDefinition


def _role(tenant, name):
    role, _ = get_or_create_tenant_role(tenant, name)
    return role


def _ensure_credit_circuit(
    *,
    tenant,
    code: str,
    name: str,
    analyst,
    manager,
    committee,
    committee_group=None,
    min_amount=None,
    max_amount=None,
    product=None,
    product_category=None,
    decisional_split: bool = True,
):
    """Crée ou met à jour un circuit crédit avec critères de sélection."""
    definition, created = WorkflowDefinition.objects.get_or_create(
        tenant=tenant,
        code=code,
        version=1,
        defaults={
            "name": name,
            "target_type": WorkflowDefinition.TargetType.CREDIT,
            "is_active": True,
            "min_amount": min_amount,
            "max_amount": max_amount,
            "product": product,
            "product_category": product_category,
        },
    )
    updated = False
    for field, value in (
        ("name", name),
        ("is_active", True),
        ("target_type", WorkflowDefinition.TargetType.CREDIT),
        ("min_amount", min_amount),
        ("max_amount", max_amount),
        ("product", product),
        ("product_category", product_category),
    ):
        if getattr(definition, field) != value:
            setattr(definition, field, value)
            updated = True
    if updated:
        definition.save()

    if created or not definition.steps.exists():
        definition.steps.all().delete()
        ApprovalStep.objects.create(
            tenant=tenant,
            definition=definition,
            name="Analyse crédit",
            order=1,
            required_group=analyst,
            sla_hours=48,
            step_kind=ApprovalStep.StepKind.CONSULTATIVE,
        )
        if decisional_split and max_amount is None and min_amount and min_amount >= Decimal(
            "1000000"
        ):
            ApprovalStep.objects.create(
                tenant=tenant,
                definition=definition,
                name="Comité de crédit filiale",
                order=2,
                required_group=committee,
                sla_hours=72,
                step_kind=ApprovalStep.StepKind.DECISIONAL,
            )
            if committee_group is not None:
                ApprovalStep.objects.create(
                    tenant=tenant,
                    definition=definition,
                    name="Comité de crédit groupe",
                    order=3,
                    required_group=committee_group,
                    sla_hours=96,
                    min_amount=Decimal("50000000"),
                    step_kind=ApprovalStep.StepKind.DECISIONAL,
                )
        else:
            ApprovalStep.objects.create(
                tenant=tenant,
                definition=definition,
                name="Validation agence",
                order=2,
                required_group=manager,
                sla_hours=24,
                step_kind=ApprovalStep.StepKind.DECISIONAL,
            )
            if max_amount is None or (
                max_amount is not None and max_amount >= Decimal("10000000")
            ):
                ApprovalStep.objects.create(
                    tenant=tenant,
                    definition=definition,
                    name="Comité de crédit filiale",
                    order=3,
                    required_group=committee,
                    sla_hours=72,
                    min_amount=Decimal("10000000"),
                    step_kind=ApprovalStep.StepKind.DECISIONAL,
                )
                if committee_group is not None and (
                    max_amount is None
                    or max_amount >= Decimal("50000000")
                ):
                    ApprovalStep.objects.create(
                        tenant=tenant,
                        definition=definition,
                        name="Comité de crédit groupe",
                        order=4,
                        required_group=committee_group,
                        sla_hours=96,
                        min_amount=Decimal("50000000"),
                        step_kind=ApprovalStep.StepKind.DECISIONAL,
                    )
    return definition


def seed_demo_catalog(*, tenant, stdout=None):
    """Familles, produits, motifs de rejet, checklist."""
    def log(msg: str):
        if stdout:
            stdout.write(msg)

    cats = {}
    for code, label in (
        ("TRESO", "Crédit de trésorerie"),
        ("IMMO", "Crédit immobilier / investissement"),
        ("CONSO", "Crédit à la consommation"),
        ("EQUIP", "Crédit équipement"),
        ("AGRO", "Crédit agricole"),
    ):
        cat, _ = ProductCategory.objects.get_or_create(
            tenant=tenant, code=code, defaults={"label": label, "is_active": True}
        )
        if not cat.is_active:
            cat.is_active = True
            cat.save(update_fields=["is_active", "updated_at"])
        cats[code] = cat

    products_spec = [
        ("TRESO-STD", "Trésorerie standard", "TRESO", "100000", "50000000", "12.5", "CRED-TRESO"),
        ("TRESO-PRO", "Trésorerie professionnelle", "TRESO", "500000", "100000000", "11.5", "CRED-TRESO-PRO"),
        ("IMMO-STD", "Investissement garantie", "IMMO", "1000000", "200000000", "10.5", "CRED-IMMO"),
        ("IMMO-PROMO", "Promotion immobilière", "IMMO", "5000000", "500000000", "9.5", "CRED-IMMO-PROMO"),
        ("CONSO-STD", "Consommation standard", "CONSO", "50000", "5000000", "14.0", "CRED-CONSO"),
        ("EQUIP-STD", "Équipement PME", "EQUIP", "500000", "80000000", "11.0", "CRED-EQUIP"),
        ("AGRO-CAMP", "Campagne agricole", "AGRO", "200000", "30000000", "10.0", "CRED-AGRO"),
    ]
    products = []
    for code, label, cat_code, amin, amax, rate, cbs in products_spec:
        p, _ = CreditProduct.objects.get_or_create(
            tenant=tenant,
            code=code,
            defaults={
                "label": label,
                "category": cats[cat_code],
                "currency": "XOF",
                "amount_min": Decimal(amin),
                "amount_max": Decimal(amax),
                "duration_min_months": 3,
                "duration_max_months": 84,
                "interest_rate": Decimal(rate),
                "requires_guarantee": cat_code in ("IMMO", "EQUIP"),
                "cbs_product_code": cbs,
                "cbs_repayment_product_code": "COMPTE-COURANT",
                "is_active": True,
            },
        )
        products.append(p)

    for code, label in (
        ("REVENU", "Revenus insuffisants"),
        ("GARANTIE", "Garanties insuffisantes"),
        ("KYC", "KYC / conformité non satisfaisante"),
        ("HISTORIQUE", "Mauvais historique de crédit"),
        ("DOSSIER", "Dossier incomplet"),
        ("AUTRE", "Autre motif"),
    ):
        RejectReason.objects.get_or_create(
            tenant=tenant,
            code=code,
            defaults={"label": label, "is_active": True},
        )

    for product in products:
        for i, label in enumerate(
            (
                "Pièce d'identité",
                "Justificatif de domicile",
                "Bulletins de salaire (3 mois)",
                "Relevé bancaire (3 mois)",
                "Attestation d'emploi",
                "Plan de financement",
            ),
            start=1,
        ):
            ChecklistItem.objects.get_or_create(
                tenant=tenant,
                product=product,
                label=label,
                defaults={"is_mandatory": i <= 4, "order": i},
            )

    log(f"Catalogue : {len(cats)} familles, {len(products)} produits, motifs & checklist.")
    return {"categories": cats, "products": products}


def seed_demo_legal_parties(*, tenant, stdout=None):
    def log(msg: str):
        if stdout:
            stdout.write(msg)

    specs = [
        (LegalParty.PartyType.LAW_FIRM, "Cabinet Koné & Associés", "Me Awa Koné"),
        (LegalParty.PartyType.LAW_FIRM, "SCPA Droit & Affaires", "Me Yves Bamba"),
        (LegalParty.PartyType.LAWYER, "Me Fatou Diallo", "Me Fatou Diallo"),
        (LegalParty.PartyType.BAILIFF, "Étude Huissier N'Guessan", "Maître N'Guessan"),
        (LegalParty.PartyType.NOTARY, "Étude Me Traoré", "Me Ibrahim Traoré"),
        (LegalParty.PartyType.EXPERT, "Expertise Immobilière CI", "Serge Kouassi"),
    ]
    n = 0
    for ptype, name, contact in specs:
        _, created = LegalParty.objects.get_or_create(
            tenant=tenant,
            party_type=ptype,
            name=name,
            defaults={
                "contact_name": contact,
                "phone": "+22507000000",
                "email": f"{name.split()[0].lower()}@demo.local",
                "address": "Abidjan",
                "is_active": True,
            },
        )
        if created:
            n += 1
    log(f"Intervenants juridiques : +{n} (total {LegalParty.objects.filter(tenant=tenant).count()}).")


def seed_demo_circuits(*, tenant, stdout=None):
    """Circuits crédit (montant / produit / les deux) + formalisation / dation / ML."""
    def log(msg: str):
        if stdout:
            stdout.write(msg)

    analyst = _role(tenant, ANALYSTE_CREDIT_RISQUE_ROLE_NAME)
    manager = _role(tenant, CHEF_AGENCE_ROLE_NAME)
    committee = _role(tenant, CREDIT_COMMITTEE_FILIALE_ROLE_NAME)
    committee_group = _role(tenant, CREDIT_COMMITTEE_GROUP_ROLE_NAME)
    legal = _role(tenant, RESP_JURIDIQUE_ROLE_NAME)

    cats = {
        c.code: c
        for c in ProductCategory.objects.filter(tenant=tenant, code__in=["IMMO", "CONSO", "TRESO", "EQUIP", "AGRO"])
    }
    products = {
        p.code: p
        for p in CreditProduct.objects.filter(
            tenant=tenant,
            code__in=["TRESO-STD", "IMMO-STD", "CONSO-STD", "EQUIP-STD", "AGRO-CAMP"],
        )
    }

    # Fallback générique (spécificité 0) — filet de sécurité.
    _ensure_credit_circuit(
        tenant=tenant,
        code="CIRCUIT-STD",
        name="Circuit standard (tous montants / produits)",
        analyst=analyst,
        manager=manager,
        committee=committee,
        committee_group=committee_group,
    )

    # Montant seul
    _ensure_credit_circuit(
        tenant=tenant,
        code="CIRCUIT-0-100K",
        name="Petite tranche 0 – 100 000",
        analyst=analyst,
        manager=manager,
        committee=committee,
        committee_group=committee_group,
        min_amount=Decimal("0"),
        max_amount=Decimal("100000"),
        decisional_split=False,
    )
    _ensure_credit_circuit(
        tenant=tenant,
        code="CIRCUIT-100K-1M",
        name="Tranche 100 001 – 1 000 000",
        analyst=analyst,
        manager=manager,
        committee=committee,
        committee_group=committee_group,
        min_amount=Decimal("100000.01"),
        max_amount=Decimal("1000000"),
        decisional_split=False,
    )
    _ensure_credit_circuit(
        tenant=tenant,
        code="CIRCUIT-1M-PLUS",
        name="Grande tranche > 1 000 000",
        analyst=analyst,
        manager=manager,
        committee=committee,
        committee_group=committee_group,
        min_amount=Decimal("1000000.01"),
        max_amount=None,
    )

    # Famille / produit seul ou combiné
    if "IMMO" in cats:
        _ensure_credit_circuit(
            tenant=tenant,
            code="CIRCUIT-IMMO",
            name="Circuit famille immobilier",
            analyst=analyst,
            manager=manager,
            committee=committee,
        committee_group=committee_group,
            product_category=cats["IMMO"],
        )
    if "CONSO-STD" in products:
        _ensure_credit_circuit(
            tenant=tenant,
            code="CIRCUIT-CONSO",
            name="Circuit produit consommation",
            analyst=analyst,
            manager=manager,
            committee=committee,
        committee_group=committee_group,
            product=products["CONSO-STD"],
            min_amount=Decimal("0"),
            max_amount=Decimal("5000000"),
            decisional_split=False,
        )
    if "IMMO-STD" in products:
        _ensure_credit_circuit(
            tenant=tenant,
            code="CIRCUIT-IMMO-GROS",
            name="Immobilier + montant élevé",
            analyst=analyst,
            manager=manager,
            committee=committee,
        committee_group=committee_group,
            product=products["IMMO-STD"],
            min_amount=Decimal("5000000"),
            max_amount=None,
        )
    if "TRESO-STD" in products:
        _ensure_credit_circuit(
            tenant=tenant,
            code="CIRCUIT-TRESO",
            name="Trésorerie standard (produit + tranche)",
            analyst=analyst,
            manager=manager,
            committee=committee,
        committee_group=committee_group,
            product=products["TRESO-STD"],
            min_amount=Decimal("0"),
            max_amount=Decimal("20000000"),
        )
    if "AGRO-CAMP" in products:
        _ensure_credit_circuit(
            tenant=tenant,
            code="CIRCUIT-AGRO",
            name="Campagne agricole",
            analyst=analyst,
            manager=manager,
            committee=committee,
        committee_group=committee_group,
            product=products["AGRO-CAMP"],
            decisional_split=False,
        )

    # Autres processus
    for code, name, target, step_name, group in (
        (
            "CIRCUIT-DATION",
            "Circuit dation en paiement",
            WorkflowDefinition.TargetType.DATION,
            "Validation dation",
            manager,
        ),
        (
            "CIRCUIT-MAIN-LEVEE",
            "Circuit main levée",
            WorkflowDefinition.TargetType.MAIN_LEVEE,
            "Validation main levée",
            manager,
        ),
        (
            "CIRCUIT-FORMALISATION",
            "Circuit formalisation de garantie",
            WorkflowDefinition.TargetType.FORMALISATION,
            "Validation formalisation",
            legal,
        ),
    ):
        d, created = WorkflowDefinition.objects.get_or_create(
            tenant=tenant,
            code=code,
            version=1,
            defaults={
                "name": name,
                "target_type": target,
                "is_active": True,
            },
        )
        if d.target_type != target or not d.is_active:
            d.target_type = target
            d.is_active = True
            d.name = name
            d.save()
        if created or not d.steps.exists():
            d.steps.all().delete()
            ApprovalStep.objects.create(
                tenant=tenant,
                definition=d,
                name=step_name,
                order=1,
                required_group=group,
                sla_hours=48,
                step_kind=ApprovalStep.StepKind.DECISIONAL,
            )

    credit_n = WorkflowDefinition.objects.filter(
        tenant=tenant,
        target_type=WorkflowDefinition.TargetType.CREDIT,
        is_active=True,
    ).count()
    log(f"Circuits actifs : {credit_n} crédit + processus annexes.")


def seed_demo_parametrage(*, tenant, stdout=None):
    """Point d'entrée paramétrage démo (catalogue + parties + circuits)."""
    seed_demo_catalog(tenant=tenant, stdout=stdout)
    seed_demo_legal_parties(tenant=tenant, stdout=stdout)
    seed_demo_circuits(tenant=tenant, stdout=stdout)
