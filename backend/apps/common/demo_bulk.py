"""Volume de données liées pour tests UI (idempotent, préfixe BULK-)."""
from __future__ import annotations

from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.utils import timezone

from apps.catalog.models import CreditProduct, ProductCategory
from apps.clients.models import Client, IdDocumentType, LegalForm
from apps.collections.models import (
    CollectionAction,
    CollectionActionType,
    CollectionCase,
    LegalParty,
    LitigationFile,
)
from apps.collections.services import refresh_loan_overdue
from apps.credits.models import (
    ActivitySector,
    CreditApplication,
    FieldVisit,
    FinancialAnalysis,
    Installment,
    Loan,
    Periodicity,
    PurposeType,
)
from apps.documents.models import Document, DocumentCategory
from apps.guarantees.formalization_services import (
    advance_legal_stage,
    initiate_formalization_request,
)
from apps.guarantees.models import (
    DationRequest,
    FinancialType,
    Guarantee,
    GuaranteeFormalizationRequest,
    GuaranteeReleaseRequest,
    PledgeCategory,
)
from apps.sureties.models import Surety, SuretyEngagement, SuretyPhone
from apps.tenants.models import Agency

FIRST_NAMES = [
    "Awa", "Ibrahim", "Fatou", "Moussa", "Aminata", "Koffi", "Adjoua", "Sekou",
    "Yves", "Claire", "Marie", "Jean", "Binta", "Oumar", "Nadia", "Serge",
    "Patricia", "Henri", "Salimata", "David", "Esther", "Alain", "Rokia", "Paul",
    "Sophie", "Bruno", "Inès", "Marc", "Aïcha", "Luc", "Grace", "Eric",
    "Chantal", "Félix", "Diana", "Hugo", "Lara", "Noah", "Maya", "Tom",
]
LAST_NAMES = [
    "Koné", "Traoré", "Diallo", "Bamba", "Soro", "Yao", "Brou", "Camara",
    "Koffi", "Ouattara", "N'Guessan", "Kouassi", "Touré", "Coulibaly", "Aka",
    "Gbagbo", "Doh", "Zongo", "Sawadogo", "Keita",
]
COMPANIES = [
    "Négoce Horizon", "Transilog Express", "Agro Verde", "BTP Sahel",
    "Pharma Plus", "Retail Market", "LogiWest", "Tech Services CI",
    "Energie Pro", "Habitat Design",
]

_FOLLOWUP_OFFSETS = (-7, -3, -1, 0, 0, 1, 2, 4, 6, 9)
_FOLLOWUP_TYPES = (
    CollectionActionType.CALL,
    CollectionActionType.SMS,
    CollectionActionType.VISIT,
    CollectionActionType.LETTER,
    CollectionActionType.EMAIL,
    CollectionActionType.LEGAL,
)
_FOLLOWUP_NOTES = (
    "Relance téléphone — promesse de paiement",
    "SMS de rappel échéance",
    "Visite terrain planifiée",
    "Courrier de mise en demeure",
    "Mail au garant / caution",
    "Préparation assignation",
)
_COURTS = (
    "Tribunal de commerce d'Abidjan",
    "Tribunal de première instance de Plateau",
    "Tribunal de commerce de Bouaké",
    "Cour d'appel d'Abidjan",
)


def seed_collection_list_widgets(*, tenant, user, stdout=None, limit: int = 12):
    """
    Peuple les widgets de la liste Recouvrement :
    - Prochaines actions (next_action_*)
    - Agenda audiences (LitigationFile.hearing_date dans les 30 j)
    Idempotent : met à jour les dossiers ouverts existants et en crée
    depuis les prêts actifs si le portefeuille est trop mince.
    """
    def log(msg: str):
        if stdout:
            stdout.write(msg)

    today = date.today()

    # Garantir un volume minimal de dossiers ouverts pour la liste.
    open_count = (
        CollectionCase.objects.filter(tenant=tenant)
        .exclude(stage=CollectionCase.Stage.CLOSED)
        .count()
    )
    needed = max(15 - open_count, 0)
    if open_count < 15:
        existing_untracked_loans = Loan.objects.filter(
            tenant=tenant,
            status=Loan.Status.ACTIVE,
            collection_case__isnull=True,
        ).count()
        loans_to_create = max(needed - existing_untracked_loans, 0)
        # Créer uniquement les prêts nécessaires pour atteindre le minimum.
        borrow_apps = list(
            CreditApplication.objects.filter(
                tenant=tenant,
                status__in=[
                    CreditApplication.Status.DISBURSED,
                    CreditApplication.Status.APPROVED,
                    CreditApplication.Status.CONTRACT_GENERATED,
                    CreditApplication.Status.DISBURSEMENT_PENDING,
                ],
            )
            .exclude(loan__isnull=False)
            .order_by("created_at")[: min(20, loans_to_create)]
        )
        for i, app in enumerate(borrow_apps):
            principal = app.amount_approved or app.amount_requested or Decimal("1500000")
            days = 25 + (i * 17) % 120
            loan = Loan.objects.create(
                tenant=tenant,
                application=app,
                principal=principal,
                interest_rate=app.interest_rate or Decimal("12.5"),
                duration_months=app.duration_months or 12,
                disbursed_at=today - timedelta(days=days + 40),
                first_due_date=today - timedelta(days=days),
                status=Loan.Status.ACTIVE,
                core_banking_reference=f"CBS-UI-{str(app.id)[:8]}",
            )
            installment_principal = (principal / 3).quantize(Decimal("1"))
            for number in range(1, 4):
                installment_status = (
                    Installment.Status.OVERDUE
                    if number == 1
                    else Installment.Status.PENDING
                )
                interest_due = Decimal("20000")
                Installment.objects.get_or_create(
                    tenant=tenant,
                    loan=loan,
                    number=number,
                    defaults={
                        "due_date": loan.first_due_date
                        + timedelta(days=30 * (number - 1)),
                        "principal_due": installment_principal,
                        "interest_due": interest_due,
                        "total_due": installment_principal + interest_due,
                        "status": installment_status,
                    },
                )
            if app.status != CreditApplication.Status.DISBURSED:
                app.status = CreditApplication.Status.DISBURSED
                app.save(update_fields=["status"])

        active_loans = (
            Loan.objects.filter(tenant=tenant, status=Loan.Status.ACTIVE)
            .select_related("application")
            .order_by("created_at")
        )
        created_cases = 0
        for i, loan in enumerate(active_loans):
            if created_cases >= needed:
                break
            if CollectionCase.objects.filter(tenant=tenant, loan=loan).exists():
                continue
            days = 20 + (i * 13) % 140
            case = refresh_loan_overdue(
                loan,
                cbs_status={
                    "settled": False,
                    "days_overdue": days,
                    "overdue_amount": (loan.principal or Decimal("500000")) / 4,
                },
            )
            if not case:
                continue
            case_updates = []
            if days >= 90:
                stage = CollectionCase.Stage.LITIGATION
            elif days >= 30:
                stage = CollectionCase.Stage.PRECONTENTIOUS
            else:
                stage = CollectionCase.Stage.AMICABLE
            if case.stage != stage:
                case.stage = stage
                case_updates.append("stage")
            if case.assigned_to_id != getattr(user, "pk", None):
                case.assigned_to = user
                case_updates.append("assigned_to")
            if case_updates:
                case.save(update_fields=[*case_updates, "updated_at"])
            CollectionAction.objects.get_or_create(
                tenant=tenant,
                case=case,
                action_type=CollectionActionType.CALL,
                action_date=today - timedelta(days=2),
                defaults={"comment": "Relance démo liste recouvrement"},
            )
            created_cases += 1

    open_cases = list(
        CollectionCase.objects.filter(tenant=tenant)
        .exclude(stage=CollectionCase.Stage.CLOSED)
        .select_related("loan__application")
        .order_by("-days_overdue", "created_at")[: max(limit * 2, 24)]
    )
    if not open_cases:
        log("Widgets recouvrement : aucun dossier ouvert à enrichir.")
        return {"followups": 0, "hearings": 0}

    followups_n = 0
    for i, case in enumerate(open_cases):
        offset = _FOLLOWUP_OFFSETS[i % len(_FOLLOWUP_OFFSETS)]
        action_type = _FOLLOWUP_TYPES[i % len(_FOLLOWUP_TYPES)]
        note = _FOLLOWUP_NOTES[i % len(_FOLLOWUP_NOTES)]
        changed_fields = []
        next_action_date = today + timedelta(days=offset)
        if case.next_action_date != next_action_date:
            case.next_action_date = next_action_date
            changed_fields.append("next_action_date")
        if case.next_action_type != action_type:
            case.next_action_type = action_type
            changed_fields.append("next_action_type")
        if case.next_action_note != note:
            case.next_action_note = note
            changed_fields.append("next_action_note")
        if not case.assigned_to_id and user is not None:
            case.assigned_to = user
            changed_fields.append("assigned_to")
        if changed_fields:
            case.save(update_fields=[*changed_fields, "updated_at"])
        followups_n += 1

    firm, _ = LegalParty.objects.get_or_create(
        tenant=tenant,
        party_type=LegalParty.PartyType.LAW_FIRM,
        name="Cabinet Koné & Associés",
        defaults={
            "contact_name": "Me Awa Koné",
            "phone": "+225 07 00 00 11",
            "email": "contact@kone-associes.demo",
            "address": "Plateau, Abidjan",
            "is_active": True,
        },
    )
    if not firm.contact_name:
        firm.contact_name = "Me Awa Koné"
        firm.phone = firm.phone or "+225 07 00 00 11"
        firm.email = firm.email or "contact@kone-associes.demo"
        firm.address = firm.address or "Plateau, Abidjan"
        firm.save(
            update_fields=["contact_name", "phone", "email", "address"]
        )

    litigation_candidates = [
        c
        for c in open_cases
        if c.stage == CollectionCase.Stage.LITIGATION or c.days_overdue >= 60
    ]
    if len(litigation_candidates) < 6:
        # Pousse quelques dossiers plus anciens en contentieux pour l'agenda.
        extras = [
            c
            for c in open_cases
            if c not in litigation_candidates
        ][: 6 - len(litigation_candidates)]
        for c in extras:
            c.stage = CollectionCase.Stage.LITIGATION
            c.save(update_fields=["stage", "updated_at"])
            litigation_candidates.append(c)

    hearings_n = 0
    hearing_slots = (3, 7, 10, 14, 18, 21, 25, 28)
    hearing_hours = (
        time(9, 0),
        time(10, 30),
        time(11, 0),
        time(14, 0),
        time(15, 30),
    )
    for i, case in enumerate(litigation_candidates[: max(limit, 8)]):
        app = getattr(case.loan, "application", None)
        ref = (app.reference if app else "") or str(case.id)[:8]
        title = f"Assignation — {ref}"
        lit = (
            LitigationFile.objects.filter(tenant=tenant, case=case)
            .exclude(
                status__in=[
                    LitigationFile.Status.CLOSED,
                    LitigationFile.Status.ABANDONED,
                    LitigationFile.Status.SETTLED,
                ]
            )
            .order_by("-created_at")
            .first()
        )
        if lit is None:
            lit = LitigationFile.objects.create(
                tenant=tenant,
                case=case,
                title=title,
                status=LitigationFile.Status.IN_PROGRESS,
                action_type=LitigationFile.ActionType.SUMMONS,
            )
        litigation_updates = {
            "title": lit.title or title,
            "status": LitigationFile.Status.IN_PROGRESS,
            "action_type": lit.action_type or LitigationFile.ActionType.SUMMONS,
            "court_name": _COURTS[i % len(_COURTS)],
            "case_reference": lit.case_reference or f"RG-{2026}-{1000 + i}",
            "law_firm_id": firm.pk,
            "hearing_date": today + timedelta(days=hearing_slots[i % len(hearing_slots)]),
            "hearing_time": hearing_hours[i % len(hearing_hours)],
            "hearing_location": "Salle des audiences civiles",
        }
        changed_fields = []
        for field, value in litigation_updates.items():
            if getattr(lit, field) != value:
                setattr(lit, field, value)
                changed_fields.append(field)
        if not lit.first_hearing_date:
            lit.first_hearing_date = litigation_updates["hearing_date"]
            changed_fields.append("first_hearing_date")
        if changed_fields:
            lit.save(update_fields=[*changed_fields, "updated_at"])
        if case.stage != CollectionCase.Stage.LITIGATION:
            case.stage = CollectionCase.Stage.LITIGATION
            case.save(update_fields=["stage"])
        hearings_n += 1

    log(
        "Widgets recouvrement : "
        f"{followups_n} prochaines actions, {hearings_n} audiences planifiées."
    )
    return {"followups": followups_n, "hearings": hearings_n}


def seed_bulk_operational_data(
    *,
    tenant,
    agency,
    product,
    user,
    count: int = 40,
    stdout=None,
):
    """
    Crée ~`count` enregistrements par module, reliés entre eux.
    Préfixe BULK- pour rester idempotent et ne pas écraser DEMO-*.
    """
    def log(msg: str):
        if stdout:
            stdout.write(msg)

    count = max(20, min(int(count), 120))

    agency2, _ = Agency.objects.get_or_create(
        tenant=tenant,
        code="AG02",
        defaults={"name": "Agence Cocody", "region": "Abidjan"},
    )
    agencies = [agency, agency2]

    cat_immo, _ = ProductCategory.objects.get_or_create(
        tenant=tenant,
        code="IMMO",
        defaults={"label": "Crédit immobilier / investissement"},
    )
    cat_conso, _ = ProductCategory.objects.get_or_create(
        tenant=tenant,
        code="CONSO",
        defaults={"label": "Crédit à la consommation"},
    )
    product_immo, _ = CreditProduct.objects.get_or_create(
        tenant=tenant,
        code="IMMO-STD",
        defaults={
            "label": "Investissement garantie",
            "category": cat_immo,
            "currency": "XOF",
            "amount_min": Decimal("1000000"),
            "amount_max": Decimal("200000000"),
            "duration_min_months": 12,
            "duration_max_months": 84,
            "interest_rate": Decimal("10.5"),
            "requires_guarantee": True,
            "cbs_product_code": "CRED-IMMO",
            "cbs_repayment_product_code": "COMPTE-COURANT",
        },
    )
    product_conso, _ = CreditProduct.objects.get_or_create(
        tenant=tenant,
        code="CONSO-STD",
        defaults={
            "label": "Consommation standard",
            "category": cat_conso,
            "currency": "XOF",
            "amount_min": Decimal("50000"),
            "amount_max": Decimal("5000000"),
            "duration_min_months": 3,
            "duration_max_months": 24,
            "interest_rate": Decimal("14.0"),
            "cbs_product_code": "CRED-CONSO",
            "cbs_repayment_product_code": "COMPTE-COURANT",
        },
    )
    products = [product, product_immo, product_conso]

    # --- Clients ---
    clients: list[Client] = []
    kyc_cycle = [
        Client.KycStatus.VALIDATED,
        Client.KycStatus.VALIDATED,
        Client.KycStatus.VALIDATED,
        Client.KycStatus.PENDING,
        Client.KycStatus.REJECTED,
    ]
    for i in range(1, count + 1):
        ag = agencies[i % 2]
        kyc = kyc_cycle[i % len(kyc_cycle)]
        ref = f"BULK-CLI-{i:03d}"
        if i % 10 == 0:
            ctype = Client.ClientType.CORPORATE
            defaults = {
                "client_type": ctype,
                "company_name": f"{COMPANIES[i % len(COMPANIES)]} {i}",
                "agency": ag,
                "kyc_status": Client.KycStatus.VALIDATED,
                "phone": f"+2250701{i:04d}",
                "cbs_client_id": f"CBS-C-{i:04d}",
            }
        elif i % 8 == 0:
            ctype = Client.ClientType.PROFESSIONAL
            defaults = {
                "client_type": ctype,
                "company_name": f"GIE {LAST_NAMES[i % len(LAST_NAMES)]} {i}",
                "first_name": FIRST_NAMES[i % len(FIRST_NAMES)],
                "last_name": LAST_NAMES[i % len(LAST_NAMES)],
                "agency": ag,
                "kyc_status": Client.KycStatus.VALIDATED,
                "phone": f"+2250702{i:04d}",
                "cbs_client_id": f"CBS-G-{i:04d}",
            }
        else:
            defaults = {
                "client_type": Client.ClientType.INDIVIDUAL,
                "first_name": FIRST_NAMES[i % len(FIRST_NAMES)],
                "last_name": LAST_NAMES[i % len(LAST_NAMES)],
                "agency": ag,
                "kyc_status": kyc,
                "phone": f"+2250703{i:04d}",
                "cbs_client_id": f"CBS-I-{i:04d}" if kyc == Client.KycStatus.VALIDATED else "",
            }
        obj, _ = Client.objects.get_or_create(
            tenant=tenant, reference=ref, defaults=defaults
        )
        clients.append(obj)

    # --- Cautions ---
    sureties: list[Surety] = []
    for i in range(1, count + 1):
        ag = agencies[i % 2]
        if i % 5 == 0:
            lookup = {
                "tenant": tenant,
                "surety_type": Surety.SuretyType.MORAL,
                "company_name": f"Caution Bulk SARL {i}",
            }
            defaults = {
                "legal_form": LegalForm.SARL,
                "phone": f"+2252722{i:04d}",
                "commitment_ceiling": Decimal(str(20_000_000 + i * 100_000)),
                "agency": ag,
                "ifu": f"IFU-BULK-{i:03d}",
                "rccm": f"CI-ABJ-B-{i:04d}",
                "city": "Abidjan",
                "manager_first_name": FIRST_NAMES[i % len(FIRST_NAMES)],
                "manager_last_name": LAST_NAMES[i % len(LAST_NAMES)],
                "manager_phone": f"+2250704{i:04d}",
                "address": f"Quartier Bulk {i}",
            }
        else:
            lookup = {
                "tenant": tenant,
                "surety_type": Surety.SuretyType.PHYSICAL,
                "first_name": FIRST_NAMES[(i + 3) % len(FIRST_NAMES)],
                "last_name": LAST_NAMES[(i + 5) % len(LAST_NAMES)],
            }
            defaults = {
                "phone": f"+2250705{i:04d}",
                "activity": ["Commerçant", "Fonctionnaire", "Transporteur", "Artisan"][i % 4],
                "estimated_income": Decimal(str(200_000 + i * 5_000)),
                "commitment_ceiling": Decimal(str(5_000_000 + i * 50_000)),
                "agency": ag,
                "id_document_type": IdDocumentType.CNI,
                "national_id": f"CI-BULK-{i:04d}",
                "address": f"Adresse caution {i}",
            }
        obj, created = Surety.objects.get_or_create(**lookup, defaults=defaults)
        if not created:
            for field, value in defaults.items():
                if getattr(obj, field, None) in (None, "", 0) and value not in (None, ""):
                    setattr(obj, field, value)
            obj.save()
        SuretyPhone.objects.get_or_create(
            tenant=tenant,
            surety=obj,
            number=defaults.get("phone") or obj.phone or f"+2250705{i:04d}",
            defaults={"label": "Principal"},
        )
        sureties.append(obj)

    # --- Dossiers de crédit ---
    status_cycle = [
        CreditApplication.Status.DRAFT,
        CreditApplication.Status.SUBMITTED,
        CreditApplication.Status.IN_APPROVAL,
        CreditApplication.Status.RETURNED,
        CreditApplication.Status.APPROVED,
        CreditApplication.Status.CONTRACT_GENERATED,
        CreditApplication.Status.DISBURSEMENT_PENDING,
        CreditApplication.Status.DISBURSED,
        CreditApplication.Status.DISBURSED,
        CreditApplication.Status.DISBURSED,
        CreditApplication.Status.DISBURSED,
        CreditApplication.Status.CLOSED,
        CreditApplication.Status.REJECTED,
        CreditApplication.Status.CANCELLED,
    ]
    apps: list[CreditApplication] = []
    for i in range(1, count + 1):
        client = clients[i - 1]
        prod = products[i % len(products)]
        ag = agencies[i % 2]
        status = status_cycle[i % len(status_cycle)]
        amount = Decimal(str(500_000 + (i % 40) * 250_000))
        months = 6 + (i % 30)
        ref = f"BULK-CR-{i:03d}"
        app, _ = CreditApplication.objects.get_or_create(
            tenant=tenant,
            reference=ref,
            defaults={
                "client": client,
                "product": prod,
                "agency": ag,
                "amount_requested": amount,
                "amount_proposed": amount,
                "amount_approved": amount
                if status
                in (
                    CreditApplication.Status.APPROVED,
                    CreditApplication.Status.CONTRACT_GENERATED,
                    CreditApplication.Status.DISBURSEMENT_PENDING,
                    CreditApplication.Status.DISBURSED,
                    CreditApplication.Status.CLOSED,
                )
                else None,
                "duration_months": months,
                "status": status,
                "periodicity": Periodicity.MONTHLY,
                "purpose_type": PurposeType.TREASURY,
                "interest_rate": prod.interest_rate or Decimal("12.5"),
                "currency": "XOF",
                "created_by": user,
                "submitted_by": user
                if status != CreditApplication.Status.DRAFT
                else None,
                "submitted_at": timezone.now() - timedelta(days=i)
                if status != CreditApplication.Status.DRAFT
                else None,
                "risk_level": 1 + (i % 4),
                "employer_name": f"Employeur Bulk {i}" if i % 3 else "",
                "contract_type": "CDI" if i % 3 == 0 else "",
            },
        )
        apps.append(app)
        if i % 4 == 0:
            FieldVisit.objects.get_or_create(
                tenant=tenant,
                application=app,
                visit_date=date.today() - timedelta(days=3 + (i % 20)),
                defaults={
                    "visited_by": user,
                    "report": f"Visite bulk {ref}",
                    "geo_coordinates": "5.3600,-4.0083",
                },
            )

    # --- Analyses financières (avec profils particuliers) ---
    profiles = [
        FinancialAnalysis.IndividualProfile.SALARIE,
        FinancialAnalysis.IndividualProfile.INDEPENDANT,
        FinancialAnalysis.IndividualProfile.MIXTE,
    ]
    for i, app in enumerate(apps, start=1):
        if FinancialAnalysis.objects.filter(
            application=app, is_reference=True
        ).exists():
            continue
        ctype = app.client.client_type
        base = {
            "tenant": tenant,
            "application": app,
            "is_reference": True,
            "client_type": ctype,
            "analysis_date": date.today() - timedelta(days=5 + (i % 10)),
            "author_role": "Analyste crédit / risque",
            "created_by": user,
            "recommendation": FinancialAnalysis.Recommendation.FAVORABLE
            if i % 5
            else FinancialAnalysis.Recommendation.CONDITIONAL,
            "comment": f"Analyse bulk {app.reference}",
            "strengths": "Profil documenté · Capacité à confirmer",
            "weaknesses": "Sensibilité saisonnière",
            "recommended_conditions": "Suivi trimestriel",
            "credit_bureau_checked": True,
            "credit_bureau_date": date.today() - timedelta(days=8),
            "internal_score": Decimal(str(55 + (i % 40))),
            "sector": ActivitySector.COMMERCE,
        }
        if ctype == Client.ClientType.CORPORATE:
            turnover = Decimal(str(10_000_000 + i * 500_000))
            base.update(
                {
                    "reference_period": FinancialAnalysis.ReferencePeriod.ANNUAL,
                    "turnover": turnover,
                    "cogs": (turnover * Decimal("0.55")).quantize(Decimal("1")),
                    "op_rent": Decimal("800000"),
                    "op_salaries": Decimal("2400000"),
                    "op_utilities": Decimal("400000"),
                    "op_other": Decimal("300000"),
                    "stock_value": Decimal("2000000"),
                    "receivables": Decimal("1500000"),
                    "cash_available": Decimal("900000"),
                    "fixed_assets": Decimal("5000000"),
                    "supplier_debt": Decimal("1000000"),
                }
            )
        elif ctype == Client.ClientType.PROFESSIONAL:
            base.update(
                {
                    "reference_period": FinancialAnalysis.ReferencePeriod.MONTHLY,
                    "members_count": 8 + (i % 12),
                    "active_contributing_members": 5 + (i % 8),
                    "solidarity_commitment": True,
                    "collective_contributions": Decimal(str(800_000 + i * 10_000)),
                    "collective_operating_expenses": Decimal("200000"),
                    "group_activity_turnover": Decimal(str(500_000 + i * 5_000)),
                }
            )
        else:
            profile = profiles[i % 3]
            salary = Decimal(str(180_000 + (i % 20) * 15_000))
            base.update(
                {
                    "reference_period": FinancialAnalysis.ReferencePeriod.MONTHLY,
                    "individual_profile": profile,
                    "rent_expense": Decimal("75000"),
                    "food_expense": Decimal("100000"),
                    "utilities_expense": Decimal("30000"),
                    "transport_expense": Decimal("35000"),
                    "education_expense": Decimal("40000"),
                    "health_expense": Decimal("20000"),
                    "other_household_expenses": Decimal("25000"),
                    "employment_seniority_months": 12 + (i % 60),
                    "existing_debt_monthly": Decimal("30000"),
                }
            )
            if profile in (
                FinancialAnalysis.IndividualProfile.SALARIE,
                FinancialAnalysis.IndividualProfile.MIXTE,
            ):
                base["salary_income"] = salary
                base["net_salary"] = salary
                base["spouse_income"] = Decimal("80000") if i % 2 else Decimal("0")
            if profile in (
                FinancialAnalysis.IndividualProfile.INDEPENDANT,
                FinancialAnalysis.IndividualProfile.MIXTE,
            ):
                base["has_side_activity"] = True
                base["activity_turnover"] = Decimal(str(400_000 + i * 8_000))
                base["activity_expenses"] = Decimal(str(150_000 + i * 2_000))
                base["activity_comment"] = "Activité génératrice de revenus (bulk)"
            if profile == FinancialAnalysis.IndividualProfile.SALARIE and i % 7 == 0:
                base["has_side_activity"] = True
                base["activity_turnover"] = Decimal("120000")
                base["activity_expenses"] = Decimal("40000")
                base["individual_profile"] = (
                    FinancialAnalysis.IndividualProfile.MIXTE
                )
        FinancialAnalysis.objects.create(**base)

    # --- Garanties liées aux dossiers ---
    gtypes = [
        (Guarantee.GuaranteeType.MORTGAGE, ""),
        (Guarantee.GuaranteeType.PLEDGE, PledgeCategory.VEHICLE),
        (Guarantee.GuaranteeType.FINANCIAL, ""),
        (Guarantee.GuaranteeType.DEPOSIT, ""),
        (Guarantee.GuaranteeType.LIEN, ""),
        (Guarantee.GuaranteeType.BANK_GUARANTEE, ""),
    ]
    guarantees: list[Guarantee] = []
    for i in range(1, count + 1):
        app = apps[i - 1]
        gtype, pledge = gtypes[i % len(gtypes)]
        ref = f"BULK-GAR-{i:03d}"
        defaults = {
            "client": app.client,
            "application": app,
            "guarantee_type": gtype,
            "pledge_category": pledge,
            "description": f"Garantie bulk {ref}",
            "expertise_value": Decimal(str(1_000_000 + i * 100_000)),
            "current_value": Decimal(str(1_000_000 + i * 100_000)),
            "status": Guarantee.Status.ACTIVE,
            "agency": app.agency,
            "belongs_to_applicant": True,
            "created_by": user,
        }
        if gtype == Guarantee.GuaranteeType.FINANCIAL:
            defaults["financial_type"] = FinancialType.SAVINGS
        if gtype == Guarantee.GuaranteeType.PLEDGE:
            defaults["brand"] = "Toyota"
            defaults["model_name"] = "Corolla"
            defaults["registration"] = f"{1000 + i}-AB-01"
        if gtype == Guarantee.GuaranteeType.MORTGAGE:
            defaults["address"] = f"Lot bulk {i}, Abidjan"
            defaults["document_number"] = f"TF-BULK-{i:04d}"
        g, _ = Guarantee.objects.get_or_create(
            tenant=tenant, reference=ref, defaults=defaults
        )
        guarantees.append(g)

    # --- Engagements de caution (lien caution ↔ dossier) ---
    for i in range(1, count + 1):
        SuretyEngagement.objects.get_or_create(
            tenant=tenant,
            surety=sureties[i - 1],
            application=apps[i - 1],
            defaults={
                "amount": Decimal(str(500_000 + i * 25_000)),
                "engagement_type": SuretyEngagement.EngagementType.SOLIDAIRE
                if i % 2
                else SuretyEngagement.EngagementType.SIMPLE,
                "signed_date": date.today() - timedelta(days=10 + (i % 30)),
                "status": SuretyEngagement.Status.ACTIVE
                if apps[i - 1].status
                != CreditApplication.Status.CLOSED
                else SuretyEngagement.Status.RELEASED,
            },
        )

    # --- Formalisations (sous-ensemble) ---
    formalized = 0
    for i, g in enumerate(guarantees, start=1):
        if i % 2 != 0:
            continue
        if GuaranteeFormalizationRequest.objects.filter(guarantee=g).exists():
            formalized += 1
            continue
        try:
            form_req = initiate_formalization_request(
                guarantee=g,
                user=user,
                comment=f"Formalisation bulk {g.reference}",
                notary_name="Me Bulk",
                fees=[
                    {
                        "fee_type": "NOTARY",
                        "amount": "50000",
                        "payer": "CLIENT",
                        "label": "Honoraires",
                    }
                ],
                as_draft=True,
            )
            if i % 6 == 0:
                advance_legal_stage(
                    form_req,
                    GuaranteeFormalizationRequest.LegalStage.AT_NOTARY,
                    user=user,
                    notary_name="Me Bulk",
                    notary_reference=f"NOT-BULK-{i:03d}",
                )
            formalized += 1
        except Exception as exc:  # noqa: BLE001 — seed best-effort
            log(f"  Formalisation ignorée {g.reference}: {exc}")

    # --- Mains levées (sur dossiers closed / approved) ---
    releases = 0
    for i, app in enumerate(apps, start=1):
        if app.status not in (
            CreditApplication.Status.CLOSED,
            CreditApplication.Status.APPROVED,
            CreditApplication.Status.CONTRACT_GENERATED,
            CreditApplication.Status.DISBURSEMENT_PENDING,
            CreditApplication.Status.DISBURSED,
        ):
            continue
        if i % 2:
            continue
        g = guarantees[i - 1]
        ref = f"BULK-ML-{i:03d}"
        _, created = GuaranteeReleaseRequest.objects.get_or_create(
            tenant=tenant,
            reference=ref,
            defaults={
                "guarantee": g,
                "application": app,
                "agency": app.agency,
                "cbs_loan_reference": f"CBS-ML-{i:03d}",
                "cbs_client_id": getattr(app.client, "cbs_client_id", "") or "",
                "cbs_settled": app.status == CreditApplication.Status.CLOSED,
                "cbs_outstanding": Decimal("0")
                if app.status == CreditApplication.Status.CLOSED
                else Decimal(str(200_000 + i * 1_000)),
                "cbs_currency": "XOF",
                "status": GuaranteeReleaseRequest.Status.COMPLETED
                if app.status == CreditApplication.Status.CLOSED
                else GuaranteeReleaseRequest.Status.DRAFT,
                "comment": f"Main levée bulk {ref}",
                "created_by": user,
            },
        )
        if created:
            releases += 1

    # --- Dations ---
    dations = 0
    for i, app in enumerate(apps, start=1):
        if i % 3 != 0:
            continue
        if app.status not in (
            CreditApplication.Status.DISBURSED,
            CreditApplication.Status.APPROVED,
            CreditApplication.Status.IN_APPROVAL,
            CreditApplication.Status.CONTRACT_GENERATED,
            CreditApplication.Status.DISBURSEMENT_PENDING,
        ):
            continue
        ref = f"BULK-DAT-{i:03d}"
        _, created = DationRequest.objects.get_or_create(
            tenant=tenant,
            reference=ref,
            defaults={
                "client": app.client,
                "application": app,
                "agency": app.agency,
                "asset_description": f"Bien dation bulk {i}",
                "asset_value": Decimal(str(2_000_000 + i * 50_000)),
                "cbs_client_id": getattr(app.client, "cbs_client_id", "") or "",
                "cbs_total_outstanding": Decimal(str(1_500_000 + i * 40_000)),
                "cbs_currency": "XOF",
                "status": DationRequest.Status.DRAFT,
                "comment": f"Dation bulk {ref}",
                "created_by": user,
            },
        )
        if created:
            dations += 1

    # --- Prêts + recouvrement ---
    loans_n = 0
    collections_n = 0
    for i, app in enumerate(apps, start=1):
        if app.status not in (
            CreditApplication.Status.DISBURSED,
            CreditApplication.Status.CLOSED,
        ):
            continue
        days_overdue = 18 + (i * 11) % 140
        make_overdue = app.status == CreditApplication.Status.DISBURSED
        principal = app.amount_approved or app.amount_requested
        loan, created = Loan.objects.get_or_create(
            application=app,
            defaults={
                "tenant": tenant,
                "principal": principal,
                "interest_rate": app.interest_rate or Decimal("12.5"),
                "duration_months": app.duration_months,
                "disbursed_at": date.today() - timedelta(days=max(days_overdue, 1) + 40),
                "first_due_date": date.today() - timedelta(days=max(days_overdue, 1)),
                "status": (
                    Loan.Status.CLOSED
                    if app.status == CreditApplication.Status.CLOSED
                    else Loan.Status.ACTIVE
                ),
                "core_banking_reference": f"CBS-BULK-{i:03d}",
            },
        )
        loans_n += 1
        if created or not loan.installments.exists():
            for n in range(1, 4):
                due = loan.first_due_date + timedelta(days=30 * (n - 1))
                part = (principal / 3).quantize(Decimal("1"))
                status = Installment.Status.PENDING
                if make_overdue and n == 1:
                    status = Installment.Status.OVERDUE
                elif app.status == CreditApplication.Status.CLOSED:
                    status = Installment.Status.PAID
                Installment.objects.get_or_create(
                    tenant=tenant,
                    loan=loan,
                    number=n,
                    defaults={
                        "due_date": due,
                        "principal_due": part,
                        "interest_due": Decimal("20000"),
                        "total_due": part + Decimal("20000"),
                        "amount_paid": part + Decimal("20000")
                        if status == Installment.Status.PAID
                        else Decimal("0"),
                        "status": status,
                    },
                )
        is_collection_widget_loan = loan.core_banking_reference.startswith("CBS-UI-")
        if (
            make_overdue
            and loan.status == Loan.Status.ACTIVE
            and not is_collection_widget_loan
        ):
            case = refresh_loan_overdue(
                loan,
                cbs_status={
                    "settled": False,
                    "days_overdue": days_overdue,
                    "overdue_amount": principal / 3,
                },
            )
            if case:
                if days_overdue >= 90:
                    case.stage = CollectionCase.Stage.LITIGATION
                elif days_overdue >= 30:
                    case.stage = CollectionCase.Stage.PRECONTENTIOUS
                else:
                    case.stage = CollectionCase.Stage.AMICABLE
                case.assigned_to = user
                case.next_action_date = date.today() + timedelta(
                    days=_FOLLOWUP_OFFSETS[collections_n % len(_FOLLOWUP_OFFSETS)]
                )
                case.next_action_type = _FOLLOWUP_TYPES[
                    collections_n % len(_FOLLOWUP_TYPES)
                ]
                case.next_action_note = _FOLLOWUP_NOTES[
                    collections_n % len(_FOLLOWUP_NOTES)
                ]
                case.save()
                CollectionAction.objects.get_or_create(
                    tenant=tenant,
                    case=case,
                    action_type=CollectionActionType.CALL,
                    action_date=date.today() - timedelta(days=1),
                    defaults={"comment": f"Relance bulk {app.reference}"},
                )
                collections_n += 1

    # --- GED (documents liés) ---
    cat_doc, _ = DocumentCategory.objects.get_or_create(
        tenant=tenant,
        code="BULK-ID",
        defaults={"label": "Pièce d'identité (bulk)", "tracks_expiry": True},
    )
    docs_n = 0
    ct_client = ContentType.objects.get_for_model(Client)
    ct_app = ContentType.objects.get_for_model(CreditApplication)
    for i, client in enumerate(clients[: min(count, len(clients))], start=1):
        name = f"CNI-BULK-{i:03d}.txt"
        if Document.objects.filter(
            tenant=tenant, name=name, content_type=ct_client, object_id=client.id
        ).exists():
            continue
        doc = Document(
            tenant=tenant,
            category=cat_doc,
            name=name,
            mime_type="text/plain",
            size_bytes=32,
            content_type=ct_client,
            object_id=client.id,
            uploaded_by=user,
            issue_date=date.today() - timedelta(days=365),
            expiry_date=date.today() + timedelta(days=365 * 2),
        )
        doc.file.save(name, ContentFile(b"document identite bulk demo\n"), save=False)
        doc.save()
        docs_n += 1
    for i, app in enumerate(apps[::2], start=1):
        name = f"DOSSIER-BULK-{i:03d}.txt"
        if Document.objects.filter(
            tenant=tenant, name=name, content_type=ct_app, object_id=app.id
        ).exists():
            continue
        doc = Document(
            tenant=tenant,
            category=cat_doc,
            name=name,
            mime_type="text/plain",
            size_bytes=48,
            content_type=ct_app,
            object_id=app.id,
            uploaded_by=user,
        )
        doc.file.save(name, ContentFile(b"piece dossier credit bulk\n"), save=False)
        doc.save()
        docs_n += 1

    log(
        "Volume bulk : "
        f"{len(clients)} clients, {len(apps)} dossiers, "
        f"{FinancialAnalysis.objects.filter(tenant=tenant, application__reference__startswith='BULK-').count()} analyses, "
        f"{len(guarantees)} garanties, {len(sureties)} cautions, "
        f"{SuretyEngagement.objects.filter(tenant=tenant, application__reference__startswith='BULK-').count()} engagements, "
        f"{formalized} formalisations, {releases} mains levées, {dations} dations, "
        f"{loans_n} prêts, {collections_n} dossiers recouvrement, {docs_n} documents GED."
    )
    return {
        "clients": len(clients),
        "applications": len(apps),
        "guarantees": len(guarantees),
        "sureties": len(sureties),
        "loans": loans_n,
        "documents": docs_n,
    }
