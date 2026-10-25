"""Jeu de données opérationnel riche pour la démo locale (idempotent)."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.catalog.models import CreditProduct, ProductCategory
from apps.clients.models import Client, IdDocumentType, LegalForm
from apps.collections.models import CollectionAction, CollectionActionType, CollectionCase
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
    RiskLevel,
)
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


def seed_rich_operational_data(*, tenant, agency, product, user, stdout=None):
    """
    Peuple FIL01 avec assez de données pour tester les écrans métier.
    Idempotent via références DEMO-*.
    """
    def log(msg):
        if stdout:
            stdout.write(msg)

    agency2, _ = Agency.objects.get_or_create(
        tenant=tenant,
        code="AG02",
        defaults={"name": "Agence Cocody", "region": "Abidjan"},
    )

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

    clients_spec = [
        ("DEMO-CLI-01", Client.ClientType.INDIVIDUAL, "Awa", "Koné", "VALIDATED", agency, "CBS-1001"),
        ("DEMO-CLI-02", Client.ClientType.INDIVIDUAL, "Ibrahim", "Traoré", "VALIDATED", agency, "CBS-1002"),
        ("DEMO-CLI-03", Client.ClientType.INDIVIDUAL, "Fatou", "Diallo", "VALIDATED", agency2, "CBS-1003"),
        ("DEMO-CLI-04", Client.ClientType.INDIVIDUAL, "Moussa", "Bamba", "PENDING", agency, ""),
        ("DEMO-CLI-05", Client.ClientType.INDIVIDUAL, "Aminata", "Soro", "VALIDATED", agency2, "CBS-1005"),
        ("DEMO-CLI-06", Client.ClientType.INDIVIDUAL, "Koffi", "Yao", "REJECTED", agency, ""),
        ("DEMO-CLI-07", Client.ClientType.CORPORATE, "", "", "VALIDATED", agency, "CBS-2001"),
        ("DEMO-CLI-08", Client.ClientType.CORPORATE, "", "", "VALIDATED", agency2, "CBS-2002"),
        ("DEMO-CLI-09", Client.ClientType.PROFESSIONAL, "Marie", "N'Guessan", "VALIDATED", agency, "CBS-1009"),
        ("DEMO-CLI-10", Client.ClientType.INDIVIDUAL, "Jean", "Kouassi", "PENDING", agency2, ""),
    ]
    clients = {}
    for ref, ctype, first, last, kyc, ag, cbs in clients_spec:
        defaults = {
            "client_type": ctype,
            "agency": ag,
            "kyc_status": kyc,
            "phone": f"+22507{ref[-2:]}00000",
            "cbs_client_id": cbs,
        }
        if ctype == Client.ClientType.CORPORATE:
            defaults["company_name"] = (
                "Négoce Abidjan SA" if ref.endswith("07") else "Transilog SARL"
            )
        elif ctype == Client.ClientType.PROFESSIONAL:
            defaults["company_name"] = "GIE Marie N'Guessan"
        else:
            defaults["first_name"] = first
            defaults["last_name"] = last
        # CLI-0001 historique → alias DEMO-CLI-01 si déjà présent
        if ref == "DEMO-CLI-01":
            legacy = Client.objects.filter(reference="CLI-0001").first()
            if legacy:
                clients[ref] = legacy
                if not legacy.cbs_client_id and cbs:
                    legacy.cbs_client_id = cbs
                    legacy.save(update_fields=["cbs_client_id", "updated_at"])
                continue
        obj, _ = Client.objects.get_or_create(
            tenant=tenant, reference=ref, defaults=defaults
        )
        if (
            obj.client_type == Client.ClientType.PROFESSIONAL
            and not (obj.company_name or "").strip()
        ):
            obj.company_name = defaults.get("company_name") or "GIE Marie N'Guessan"
            obj.save(update_fields=["company_name", "updated_at"])
        clients[ref] = obj

    sureties = {}
    surety_specs = [
        {
            "key": "DEMO-CAU-01",
            "surety_type": Surety.SuretyType.PHYSICAL,
            "first_name": "Paul",
            "last_name": "Aka",
            "phone": "+22507000091",
            "activity": "Commerçant",
            "estimated_income": Decimal("450000"),
            "commitment_ceiling": Decimal("20000000"),
            "agency": agency,
            "id_document_type": IdDocumentType.CNI,
            "national_id": "CI-91-0001",
            "address": "Cocody Angré, Abidjan",
        },
        {
            "key": "DEMO-CAU-02",
            "surety_type": Surety.SuretyType.PHYSICAL,
            "first_name": "Adjoua",
            "last_name": "Brou",
            "phone": "+22507000092",
            "activity": "Fonctionnaire",
            "estimated_income": Decimal("320000"),
            "commitment_ceiling": Decimal("10000000"),
            "agency": agency2,
            "id_document_type": IdDocumentType.CNI,
            "national_id": "CI-92-0002",
            "address": "Yopougon Sicogi, Abidjan",
        },
        {
            "key": "DEMO-CAU-03",
            "surety_type": Surety.SuretyType.PHYSICAL,
            "first_name": "Sekou",
            "last_name": "Camara",
            "phone": "+22507000093",
            "activity": "Transporteur",
            "estimated_income": Decimal("280000"),
            "commitment_ceiling": Decimal("8000000"),
            "agency": agency,
            "id_document_type": IdDocumentType.DRIVING_LICENSE,
            "national_id": "PERM-93-0003",
            "address": "Marcory Zone 4",
        },
        {
            "key": "DEMO-CAU-04",
            "surety_type": Surety.SuretyType.MORAL,
            "company_name": "Caution Plus SARL",
            "legal_form": LegalForm.SARL,
            "phone": "+22527220094",
            "commitment_ceiling": Decimal("50000000"),
            "agency": agency,
            "ifu": "IFU-DEMO-004",
            "rccm": "CI-ABJ-2020-B-1234",
            "city": "Abidjan",
            "manager_first_name": "Yves",
            "manager_last_name": "Koffi",
            "manager_phone": "+22507000094",
            "address": "Plateau, Avenue 7",
        },
        {
            "key": "DEMO-CAU-05",
            "surety_type": Surety.SuretyType.MORAL,
            "company_name": "Garant Mutual SA",
            "legal_form": LegalForm.SA,
            "phone": "+22527220095",
            "commitment_ceiling": Decimal("100000000"),
            "agency": agency2,
            "ifu": "IFU-DEMO-005",
            "rccm": "CI-ABJ-2018-A-7788",
            "city": "Abidjan",
            "manager_first_name": "Claire",
            "manager_last_name": "Ouattara",
            "manager_phone": "+22507000095",
            "address": "Riviera 3",
        },
    ]
    for spec in surety_specs:
        key = spec.pop("key")
        lookup = {
            "tenant": tenant,
            "surety_type": spec["surety_type"],
        }
        if spec["surety_type"] == Surety.SuretyType.PHYSICAL:
            lookup["first_name"] = spec["first_name"]
            lookup["last_name"] = spec["last_name"]
        else:
            lookup["company_name"] = spec["company_name"]
        obj, created = Surety.objects.get_or_create(**lookup, defaults=spec)
        if not created:
            for field, value in spec.items():
                if getattr(obj, field, None) in (None, "", 0) and value not in (
                    None,
                    "",
                ):
                    setattr(obj, field, value)
            obj.save()
        sureties[key] = obj
        SuretyPhone.objects.get_or_create(
            tenant=tenant,
            surety=obj,
            number=spec.get("phone") or obj.phone or f"+2250700{key[-2:]}",
            defaults={"label": "Principal"},
        )

    S = CreditApplication.Status
    apps_spec = [
        ("DEMO-CR-DRAFT", "DEMO-CLI-04", product, S.DRAFT, "1500000", 12, agency),
        ("DEMO-CR-SUBMIT", "DEMO-CLI-02", product, S.SUBMITTED, "2500000", 18, agency),
        ("DEMO-CR-APPROVAL", "DEMO-CLI-03", product_immo, S.IN_APPROVAL, "15000000", 36, agency2),
        ("DEMO-CR-RETURN", "DEMO-CLI-05", product, S.RETURNED, "800000", 9, agency2),
        ("DEMO-CR-REJECT", "DEMO-CLI-06", product_conso, S.REJECTED, "300000", 6, agency),
        ("DEMO-CR-OK", "DEMO-CLI-09", product, S.APPROVED, "5000000", 24, agency),
        ("DEMO-CR-CONTRACT", "DEMO-CLI-02", product, S.CONTRACT_GENERATED, "1200000", 12, agency),
        ("DEMO-CR-PENDING", "DEMO-CLI-03", product_conso, S.DISBURSEMENT_PENDING, "600000", 8, agency2),
        ("DEMO-CR-DISB-1", "DEMO-CLI-01", product, S.DISBURSED, "3000000", 18, agency),
        ("DEMO-CR-DISB-2", "DEMO-CLI-05", product_immo, S.DISBURSED, "25000000", 48, agency2),
        ("DEMO-CR-DISB-3", "DEMO-CLI-07", product, S.DISBURSED, "8000000", 24, agency),
        ("DEMO-CR-CLOSED", "DEMO-CLI-08", product, S.CLOSED, "2000000", 12, agency2),
        ("DEMO-CR-CANCEL", "DEMO-CLI-10", product_conso, S.CANCELLED, "400000", 6, agency2),
    ]
    apps = {}
    for ref, cli_ref, prod, status, amount, months, ag in apps_spec:
        app, created = CreditApplication.objects.get_or_create(
            tenant=tenant,
            reference=ref,
            defaults={
                "client": clients[cli_ref],
                "product": prod,
                "agency": ag,
                "amount_requested": Decimal(amount),
                "amount_proposed": Decimal(amount),
                "duration_months": months,
                "status": status,
                "periodicity": Periodicity.MONTHLY,
                "purpose_type": PurposeType.TREASURY,
                "interest_rate": prod.interest_rate or Decimal("12.5"),
                "currency": "XOF",
                "created_by": user,
                "risk_level": 2,
            },
        )
        if not created and app.status != status:
            # ne force pas les statuts déjà avancés manuellement
            pass
        apps[ref] = app

    for ref in ("DEMO-CR-SUBMIT", "DEMO-CR-APPROVAL", "DEMO-CR-OK"):
        app = apps[ref]
        FieldVisit.objects.get_or_create(
            tenant=tenant,
            application=app,
            visit_date=date.today() - timedelta(days=5),
            defaults={
                "visited_by": user,
                "report": f"Visite terrain démo — {ref}",
                "geo_coordinates": "5.3600,-4.0083",
            },
        )

    g_specs = [
        (
            "DEMO-GAR-HYP-1",
            "DEMO-CLI-01",
            "DEMO-CR-DISB-1",
            Guarantee.GuaranteeType.MORTGAGE,
            "",
            "25000000",
            Guarantee.Status.ACTIVE,
            agency,
        ),
        (
            "DEMO-GAR-GAGE-1",
            "DEMO-CLI-05",
            "DEMO-CR-DISB-2",
            Guarantee.GuaranteeType.PLEDGE,
            PledgeCategory.VEHICLE,
            "8000000",
            Guarantee.Status.ACTIVE,
            agency2,
        ),
        (
            "DEMO-GAR-FIN-1",
            "DEMO-CLI-07",
            "DEMO-CR-DISB-3",
            Guarantee.GuaranteeType.FINANCIAL,
            "",
            "5000000",
            Guarantee.Status.ACTIVE,
            agency,
        ),
        (
            "DEMO-GAR-HYP-2",
            "DEMO-CLI-03",
            "DEMO-CR-APPROVAL",
            Guarantee.GuaranteeType.MORTGAGE,
            "",
            "40000000",
            Guarantee.Status.ACTIVE,
            agency2,
        ),
        (
            "DEMO-GAR-FORM",
            "DEMO-CLI-02",
            "DEMO-CR-CONTRACT",
            Guarantee.GuaranteeType.MORTGAGE,
            "",
            "18000000",
            Guarantee.Status.ACTIVE,
            agency,
        ),
        (
            "DEMO-GAR-ML",
            "DEMO-CLI-08",
            "DEMO-CR-CLOSED",
            Guarantee.GuaranteeType.PLEDGE,
            PledgeCategory.VEHICLE,
            "3500000",
            Guarantee.Status.ACTIVE,
            agency2,
        ),
        (
            "DEMO-GAR-REL",
            "DEMO-CLI-09",
            "DEMO-CR-OK",
            Guarantee.GuaranteeType.FINANCIAL,
            "",
            "2000000",
            Guarantee.Status.RELEASED,
            agency,
        ),
        (
            "DEMO-GAR-REAL",
            "DEMO-CLI-01",
            None,
            Guarantee.GuaranteeType.OTHER,
            "",
            "1000000",
            Guarantee.Status.REALIZED,
            agency,
        ),
        (
            "DEMO-GAR-DEP-1",
            "DEMO-CLI-02",
            "DEMO-CR-SUBMIT",
            Guarantee.GuaranteeType.DEPOSIT,
            "",
            "500000",
            Guarantee.Status.ACTIVE,
            agency,
        ),
        (
            "DEMO-GAR-BANK-1",
            "DEMO-CLI-07",
            "DEMO-CR-DISB-3",
            Guarantee.GuaranteeType.BANK_GUARANTEE,
            "",
            "3000000",
            Guarantee.Status.ACTIVE,
            agency,
        ),
        (
            "DEMO-GAR-LIEN-1",
            "DEMO-CLI-09",
            "DEMO-CR-OK",
            Guarantee.GuaranteeType.LIEN,
            "",
            "1500000",
            Guarantee.Status.ACTIVE,
            agency,
        ),
        (
            "DEMO-GAR-JOY-1",
            "DEMO-CLI-05",
            "DEMO-CR-RETURN",
            Guarantee.GuaranteeType.PLEDGE,
            PledgeCategory.VALUABLE,
            "1200000",
            Guarantee.Status.ACTIVE,
            agency2,
        ),
        (
            "DEMO-GAR-DAT-1",
            "DEMO-CLI-03",
            "DEMO-CR-PENDING",
            Guarantee.GuaranteeType.FINANCIAL,
            "",
            "900000",
            Guarantee.Status.ACTIVE,
            agency2,
        ),
    ]
    guarantees = {}
    for ref, cli, app_ref, gtype, pledge, value, status, ag in g_specs:
        defaults = {
            "client": clients[cli],
            "guarantee_type": gtype,
            "pledge_category": pledge,
            "description": f"Garantie démo {ref}",
            "expertise_value": Decimal(value),
            "current_value": Decimal(value),
            "status": status,
            "agency": ag,
            "belongs_to_applicant": True,
            "created_by": user,
        }
        if app_ref:
            defaults["application"] = apps[app_ref]
        if ref == "DEMO-GAR-HYP-2":
            defaults["belongs_to_applicant"] = False
            defaults["surety"] = sureties["DEMO-CAU-01"]
        if ref == "DEMO-GAR-GAGE-1":
            defaults["brand"] = "Toyota"
            defaults["model_name"] = "Hilux"
            defaults["registration"] = "1234-AB-01"
            defaults["chassis_number"] = "DEMOCHASSIS001"
        if ref == "DEMO-GAR-DAT-1":
            defaults["financial_type"] = FinancialType.DAT
        if ref == "DEMO-GAR-FIN-1":
            defaults["financial_type"] = FinancialType.SAVINGS
        if ref == "DEMO-GAR-HYP-1":
            defaults["address"] = "Lot 45, Riviera Palmeraie"
            defaults["document_number"] = "TF-8841"
            defaults["owner_last_name"] = "Koné"
            defaults["owner_first_name"] = "Awa"
        g, _ = Guarantee.objects.get_or_create(
            tenant=tenant, reference=ref, defaults=defaults
        )
        guarantees[ref] = g

    # --- Analyses financières (référence) ---
    analysis_by_app = {
        "DEMO-CR-DRAFT": {
            "kind": "individual",
            "recommendation": FinancialAnalysis.Recommendation.CONDITIONAL,
            "salary": "180000",
            "comment": "Dossier encore en instruction — capacité à confirmer.",
        },
        "DEMO-CR-SUBMIT": {
            "kind": "individual",
            "recommendation": FinancialAnalysis.Recommendation.FAVORABLE,
            "salary": "420000",
            "spouse": "150000",
            "comment": "Revenus stables, endettement maîtrisé.",
        },
        "DEMO-CR-APPROVAL": {
            "kind": "individual",
            "recommendation": FinancialAnalysis.Recommendation.FAVORABLE,
            "salary": "550000",
            "rental": "200000",
            "comment": "Bon profil ; hypothèque en cours de formalisation.",
        },
        "DEMO-CR-RETURN": {
            "kind": "individual",
            "recommendation": FinancialAnalysis.Recommendation.CONDITIONAL,
            "salary": "250000",
            "comment": "Retour pour pièces manquantes — avis conditionnel.",
        },
        "DEMO-CR-REJECT": {
            "kind": "individual",
            "recommendation": FinancialAnalysis.Recommendation.UNFAVORABLE,
            "salary": "90000",
            "comment": "Capacité insuffisante au regard du montant demandé.",
        },
        "DEMO-CR-OK": {
            "kind": "individual",
            "recommendation": FinancialAnalysis.Recommendation.FAVORABLE,
            "salary": "380000",
            "other_act": "80000",
            "profile": "MIXTE",
            "side_turnover": "180000",
            "side_expenses": "60000",
            "comment": "Profil mixte salarié + activité génératrice de revenus.",
        },
        "DEMO-CR-CONTRACT": {
            "kind": "individual",
            "recommendation": FinancialAnalysis.Recommendation.FAVORABLE,
            "salary": "310000",
            "profile": "SALARIE",
            "comment": "Analyse validée — passage contrat.",
        },
        "DEMO-CR-PENDING": {
            "kind": "individual",
            "recommendation": FinancialAnalysis.Recommendation.FAVORABLE,
            "salary": "290000",
            "profile": "INDEPENDANT",
            "side_turnover": "420000",
            "side_expenses": "160000",
            "comment": "Indépendant — prêt pour mise en place.",
        },
        "DEMO-CR-DISB-1": {
            "kind": "individual",
            "recommendation": FinancialAnalysis.Recommendation.FAVORABLE,
            "salary": "350000",
            "profile": "SALARIE",
            "comment": "Analyse historique du prêt mis en place.",
        },
        "DEMO-CR-DISB-2": {
            "kind": "individual",
            "recommendation": FinancialAnalysis.Recommendation.FAVORABLE,
            "salary": "600000",
            "spouse": "250000",
            "profile": "SALARIE",
            "comment": "Investissement immobilier — couverture hypothécaire.",
        },
        "DEMO-CR-DISB-3": {
            "kind": "corporate",
            "recommendation": FinancialAnalysis.Recommendation.FAVORABLE,
            "turnover": "45000000",
            "comment": "PME négoce — CA régulier, trésorerie correcte.",
        },
        "DEMO-CR-CLOSED": {
            "kind": "corporate",
            "recommendation": FinancialAnalysis.Recommendation.FAVORABLE,
            "turnover": "28000000",
            "comment": "Analyse du crédit soldé.",
        },
    }
    for app_ref, spec in analysis_by_app.items():
        app = apps[app_ref]
        if FinancialAnalysis.objects.filter(
            application=app, is_reference=True
        ).exists():
            continue
        client_type = app.client.client_type
        base = {
            "tenant": tenant,
            "application": app,
            "is_reference": True,
            "client_type": client_type,
            "analysis_date": date.today() - timedelta(days=10),
            "author_role": "Analyste crédit / risque",
            "created_by": user,
            "recommendation": spec["recommendation"],
            "comment": spec["comment"],
            "strengths": "Historique client connu · Dossier documenté",
            "weaknesses": "Sensibilité au chiffre d'affaires saisonnier",
            "recommended_conditions": "Maintenir épargne obligatoire · Suivi trimestriel",
            "credit_bureau_checked": True,
            "credit_bureau_date": date.today() - timedelta(days=12),
            "internal_score": Decimal("72.50"),
            "sector": ActivitySector.COMMERCE,
            "seasonality_level": RiskLevel.MEDIUM,
        }
        if spec["kind"] == "corporate":
            turnover = Decimal(spec["turnover"])
            base.update(
                {
                    "reference_period": FinancialAnalysis.ReferencePeriod.ANNUAL,
                    "turnover": turnover,
                    "cogs": (turnover * Decimal("0.55")).quantize(Decimal("1")),
                    "op_rent": Decimal("1200000"),
                    "op_salaries": Decimal("4800000"),
                    "op_utilities": Decimal("600000"),
                    "op_transport": Decimal("900000"),
                    "op_taxes": Decimal("800000"),
                    "op_other": Decimal("500000"),
                    "depreciation": Decimal("700000"),
                    "financial_charges": Decimal("350000"),
                    "stock_value": Decimal("6000000"),
                    "receivables": Decimal("3500000"),
                    "cash_available": Decimal("2200000"),
                    "fixed_assets": Decimal("15000000"),
                    "supplier_debt": Decimal("2800000"),
                    "ongoing_credit_balance": Decimal("1500000"),
                    "turnover_prev": (turnover * Decimal("0.9")).quantize(
                        Decimal("1")
                    ),
                    "net_result_prev": Decimal("2500000"),
                    "projected_monthly_inflows": (turnover / 12).quantize(
                        Decimal("1")
                    ),
                    "projected_monthly_outflows": (turnover / 14).quantize(
                        Decimal("1")
                    ),
                }
            )
        else:
            salary = Decimal(spec.get("salary", "0"))
            profile = spec.get("profile", "SALARIE")
            base.update(
                {
                    "reference_period": FinancialAnalysis.ReferencePeriod.MONTHLY,
                    "individual_profile": profile,
                    "salary_income": salary,
                    "net_salary": salary,
                    "spouse_income": Decimal(spec.get("spouse", "0")),
                    "rental_income": Decimal(spec.get("rental", "0")),
                    "other_activity_income": Decimal(spec.get("other_act", "0")),
                    "rent_expense": Decimal("80000"),
                    "food_expense": Decimal("120000"),
                    "utilities_expense": Decimal("35000"),
                    "transport_expense": Decimal("40000"),
                    "education_expense": Decimal("50000"),
                    "health_expense": Decimal("20000"),
                    "other_household_expenses": Decimal("30000"),
                    "tontine_expense": Decimal("25000"),
                    "employment_seniority_months": 48,
                    "existing_debt_monthly": Decimal("45000"),
                    "projected_monthly_inflows": salary
                    + Decimal(spec.get("spouse", "0")),
                    "projected_monthly_outflows": Decimal("350000"),
                }
            )
            if profile in ("INDEPENDANT", "MIXTE") or spec.get("side_turnover"):
                base["has_side_activity"] = True
                base["activity_turnover"] = Decimal(
                    spec.get("side_turnover", "200000")
                )
                base["activity_expenses"] = Decimal(
                    spec.get("side_expenses", "70000")
                )
                base["activity_comment"] = "Activité génératrice de revenus (démo)"
            if profile == "INDEPENDANT":
                base["salary_income"] = Decimal("0")
                base["net_salary"] = Decimal("0")
                base["projected_monthly_inflows"] = base["activity_turnover"]
        # Deuxième analyse non-référence sur quelques dossiers
        FinancialAnalysis.objects.create(**base)
        if app_ref in ("DEMO-CR-APPROVAL", "DEMO-CR-DISB-3"):
            side = dict(base)
            side["is_reference"] = False
            side["author_role"] = "Chef d'agence"
            side["recommendation"] = FinancialAnalysis.Recommendation.CONDITIONAL
            side["comment"] = "Contre-analyse agence — conditions de suivi renforcées."
            side["internal_score"] = Decimal("68.00")
            FinancialAnalysis.objects.create(**side)

    # --- Engagements de caution ---
    engagement_specs = [
        ("DEMO-CAU-01", "DEMO-CR-APPROVAL", "15000000"),
        ("DEMO-CAU-02", "DEMO-CR-DISB-1", "2000000"),
        ("DEMO-CAU-03", "DEMO-CR-SUBMIT", "1000000"),
        ("DEMO-CAU-04", "DEMO-CR-DISB-3", "5000000"),
        ("DEMO-CAU-05", "DEMO-CR-DISB-2", "10000000"),
        ("DEMO-CAU-01", "DEMO-CR-OK", "1500000"),
        ("DEMO-CAU-02", "DEMO-CR-CONTRACT", "800000"),
    ]
    for cau_key, app_ref, amount in engagement_specs:
        SuretyEngagement.objects.get_or_create(
            tenant=tenant,
            surety=sureties[cau_key],
            application=apps[app_ref],
            defaults={
                "amount": Decimal(amount),
                "engagement_type": SuretyEngagement.EngagementType.SOLIDAIRE,
                "signed_date": date.today() - timedelta(days=15),
                "status": SuretyEngagement.Status.ACTIVE,
            },
        )
    # Un engagement libéré (historique)
    SuretyEngagement.objects.get_or_create(
        tenant=tenant,
        surety=sureties["DEMO-CAU-03"],
        application=apps["DEMO-CR-CLOSED"],
        defaults={
            "amount": Decimal("500000"),
            "engagement_type": SuretyEngagement.EngagementType.SIMPLE,
            "signed_date": date.today() - timedelta(days=400),
            "status": SuretyEngagement.Status.RELEASED,
        },
    )

    # Formalisation en cours (non bloquante)
    if not GuaranteeFormalizationRequest.objects.filter(
        guarantee=guarantees["DEMO-GAR-FORM"],
        status__in=[
            GuaranteeFormalizationRequest.Status.DRAFT,
            GuaranteeFormalizationRequest.Status.IN_PROGRESS,
            GuaranteeFormalizationRequest.Status.IN_APPROVAL,
        ],
    ).exists():
        form_req = initiate_formalization_request(
            guarantee=guarantees["DEMO-GAR-FORM"],
            user=user,
            comment="Dossier formalisation démo",
            notary_name="Me Kouassi",
            fees=[
                {
                    "fee_type": "NOTARY",
                    "amount": "75000",
                    "payer": "CLIENT",
                    "label": "Honoraires notaire",
                }
            ],
            as_draft=True,
        )
        advance_legal_stage(
            form_req,
            GuaranteeFormalizationRequest.LegalStage.AT_NOTARY,
            user=user,
            notary_name="Me Kouassi",
            notary_reference="NOT-DEMO-01",
        )

    # Formalisation clôturée sur une autre garantie
    g_done = guarantees["DEMO-GAR-HYP-1"]
    if not g_done.formalized_at:
        g_done.registration_number = "TF-ABJ-2024-8841"
        g_done.registration_date = date.today() - timedelta(days=120)
        g_done.registration_authority = "Conservation foncière Abidjan"
        g_done.formalized_at = timezone.now() - timedelta(days=100)
        g_done.save(
            update_fields=[
                "registration_number",
                "registration_date",
                "registration_authority",
                "formalized_at",
                "updated_at",
            ]
        )

    GuaranteeReleaseRequest.objects.get_or_create(
        tenant=tenant,
        reference="DEMO-ML-001",
        defaults={
            "guarantee": guarantees["DEMO-GAR-ML"],
            "application": apps["DEMO-CR-CLOSED"],
            "agency": agency2,
            "cbs_loan_reference": "REF-CBS-CLOSED-01",
            "cbs_client_id": clients["DEMO-CLI-08"].cbs_client_id,
            "cbs_settled": True,
            "cbs_outstanding": Decimal("0"),
            "cbs_currency": "XOF",
            "status": GuaranteeReleaseRequest.Status.DRAFT,
            "comment": "Main levée démo — prêt soldé",
            "created_by": user,
        },
    )
    GuaranteeReleaseRequest.objects.get_or_create(
        tenant=tenant,
        reference="DEMO-ML-002",
        defaults={
            "guarantee": guarantees["DEMO-GAR-REL"],
            "application": apps["DEMO-CR-OK"],
            "agency": agency,
            "cbs_loan_reference": "REF-CBS-REL-01",
            "cbs_settled": True,
            "cbs_outstanding": Decimal("0"),
            "cbs_currency": "XOF",
            "status": GuaranteeReleaseRequest.Status.COMPLETED,
            "completed_at": timezone.now() - timedelta(days=30),
            "comment": "Main levée clôturée (historique)",
            "created_by": user,
        },
    )

    DationRequest.objects.get_or_create(
        tenant=tenant,
        reference="DEMO-DAT-001",
        defaults={
            "client": clients["DEMO-CLI-07"],
            "application": apps["DEMO-CR-DISB-3"],
            "agency": agency,
            "asset_description": "Terrain Zone 4 — dation démo",
            "asset_value": Decimal("9000000"),
            "cbs_client_id": clients["DEMO-CLI-07"].cbs_client_id,
            "cbs_total_outstanding": Decimal("7500000"),
            "cbs_currency": "XOF",
            "status": DationRequest.Status.DRAFT,
            "comment": "Dation démo en brouillon",
            "created_by": user,
        },
    )

    # Prêts + échéances + recouvrement
    loan_specs = [
        ("DEMO-CR-DISB-1", 20, "3000000", False),
        ("DEMO-CR-DISB-2", 45, "25000000", True),
        ("DEMO-CR-DISB-3", 100, "8000000", True),
        ("DEMO-CR-CLOSED", 0, "2000000", False),
    ]
    for app_ref, days_overdue, principal, make_overdue in loan_specs:
        app = apps[app_ref]
        loan, created = Loan.objects.get_or_create(
            application=app,
            defaults={
                "tenant": tenant,
                "principal": Decimal(principal),
                "interest_rate": Decimal("12.5"),
                "duration_months": app.duration_months,
                "disbursed_at": date.today() - timedelta(days=max(days_overdue, 1) + 40),
                "first_due_date": date.today() - timedelta(days=max(days_overdue, 1)),
                "status": (
                    Loan.Status.CLOSED
                    if app.status == CreditApplication.Status.CLOSED
                    else Loan.Status.ACTIVE
                ),
                "core_banking_reference": f"CBS-LOAN-{app_ref[-1]}",
            },
        )
        if created or not loan.installments.exists():
            for n in range(1, 4):
                due = loan.first_due_date + timedelta(days=30 * (n - 1))
                part = (Decimal(principal) / 3).quantize(Decimal("1"))
                status = Installment.Status.PENDING
                if make_overdue and n == 1:
                    status = Installment.Status.OVERDUE
                elif app.status == CreditApplication.Status.CLOSED:
                    status = Installment.Status.PAID
                elif not make_overdue and n == 1 and days_overdue < 30:
                    status = Installment.Status.PENDING
                Installment.objects.get_or_create(
                    tenant=tenant,
                    loan=loan,
                    number=n,
                    defaults={
                        "due_date": due,
                        "principal_due": part,
                        "interest_due": Decimal("25000"),
                        "total_due": part + Decimal("25000"),
                        "amount_paid": part + Decimal("25000")
                        if status == Installment.Status.PAID
                        else Decimal("0"),
                        "status": status,
                    },
                )
        if make_overdue and loan.status == Loan.Status.ACTIVE:
            case = refresh_loan_overdue(
                loan,
                cbs_status={
                    "settled": False,
                    "days_overdue": days_overdue,
                    "overdue_amount": Decimal(principal),
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
                case.next_action_date = date.today() + timedelta(days=-1 if days_overdue >= 30 else 2)
                case.next_action_type = CollectionActionType.CALL
                case.next_action_note = "Relance démo — promesse à confirmer"
                case.save()
                CollectionAction.objects.get_or_create(
                    tenant=tenant,
                    case=case,
                    action_type=CollectionActionType.CALL,
                    action_date=date.today() - timedelta(days=2),
                    defaults={"comment": "Relance téléphonique démo"},
                )

    log(
        "Données riches : "
        f"{Client.objects.filter(tenant=tenant).count()} clients, "
        f"{CreditApplication.objects.filter(tenant=tenant).count()} dossiers, "
        f"{FinancialAnalysis.objects.filter(tenant=tenant).count()} analyses, "
        f"{Guarantee.objects.filter(tenant=tenant).count()} garanties, "
        f"{Surety.objects.filter(tenant=tenant).count()} cautions, "
        f"{SuretyEngagement.objects.filter(tenant=tenant).count()} engagements, "
        f"{Loan.objects.filter(tenant=tenant).count()} prêts."
    )
