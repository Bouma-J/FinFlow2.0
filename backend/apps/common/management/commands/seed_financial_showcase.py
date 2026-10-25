"""Jeu financier local, fictif, reproductible et isolé sous le préfixe VISU-."""
from collections import Counter
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import CreditProduct
from apps.clients.models import Client
from apps.common.tenancy import tenant_context
from apps.credits.analysis_details import validate_details
from apps.credits.analytics import compute_metrics
from apps.credits.models import AnalysisThreshold, CreditApplication, FieldVisit, FinancialAnalysis
from apps.guarantees.models import Guarantee
from apps.sureties.models import Surety, SuretyEngagement
from apps.tenants.models import Agency, Tenant

D = Decimal
MARKER = "VISU — données financières fictives"
PROFILES = [("ENT", "Entreprise", "CORPORATE", ""), ("SAL", "Salarié", "INDIVIDUAL", "SALARIE"),
            ("IND", "Indépendant", "INDIVIDUAL", "INDEPENDANT"), ("MIX", "Mixte", "INDIVIDUAL", "MIXTE"),
            ("GRP", "Groupement", "PROFESSIONAL", "")]
SCENARIOS = ["Équilibré", "Saisonnalité", "Trésorerie tendue", "Capacité insuffisante", "Écarts à rapprocher",
             "Patrimoine peu liquide", "Croissance", "Hausse des achats", "Dettes multiples", "In fine",
             "Période trimestrielle", "Informations partielles"]
SEASON = [D(value) for value in ("0.60", "0.65", "0.70", "0.80", "0.90", "1.05", "1.30", "1.50", "1.60", "1.25", "1.00", "0.65")]


def amount(value):
    return D(str(value)).quantize(D("0.01"))


def text_amount(value):
    return str(amount(value))


def products(factor, divisor=1, cost_ratio=D("0.50")):
    names = ["Riz conditionné", "Huile alimentaire", "Farine", "Sucre", "Produits d'entretien", "Services de livraison"]
    quantities = [1200, 1000, 800, 600, 500, 400]
    prices = [10000, 8000, 12500, 10000, 16000, 10000]
    return [{"name": name, "unit": "lot" if index < 5 else "prestation",
             "quantity": str(int(D(quantity) * factor / divisor)), "sale_price": str(price),
             "unit_cost": text_amount(D(price) * cost_ratio),
             "comment": "Fiche fictive ; ventes et coûts sur la période de référence."}
            for index, (name, quantity, price) in enumerate(zip(names, quantities, prices))]


def total_products(rows, column):
    return sum((D(row["quantity"]) * D(row[column]) for row in rows), D("0"))


def inventory(target, as_of):
    # Une ligne finale absorbe les centimes pour rapprocher exactement l'agrégat.
    remaining, rows = amount(target), []
    for index, name in enumerate(["Marchandises A", "Marchandises B", "Conditionnement", "Pièces détachées", "Produits saisonniers", "Lot à rotation lente"]):
        net = amount(target / 6) if index < 5 else remaining
        remaining -= net
        impairment = D("15000") if index == 5 else D("0")
        rows.append({"name": name, "quantity": "1", "unit_cost": text_amount(net + impairment),
                     "impaired_value": str(impairment), "count_date": as_of.isoformat(),
                     "comment": "Lot fictif valorisé au coût ; dernière ligne dépréciée."})
    return rows


def build_analysis(app, profile, scenario, factor, as_of):
    corporate, group = profile == "ENT", profile == "GRP"
    activity = profile in {"IND", "MIX"}
    period = "ANNUAL" if corporate else "QUARTERLY" if scenario == 10 else "MONTHLY"
    periods_months = D("12") if corporate else D("3") if period == "QUARTERLY" else D("1")
    defaults = {
        "reference_period": period, "analysis_date": as_of, "financial_statement_date": as_of,
        "information_quality": "PARTIALLY_VERIFIED" if scenario in {4, 11} else "VERIFIED",
        "bank_statement_months": 3 if scenario == 11 else 12,
        "financial_documents_verified": scenario != 11, "field_visit_confirmed": True,
        "stock_count_verified": corporate or activity, "cash_position_verified": scenario != 11,
        "primary_repayment_source": "Revenus et flux d'exploitation simulés — aucun justificatif réel.",
        "verification_comment": f"{MARKER}. Vérifications fictives à des fins de lecture et de démonstration uniquement.",
        "credit_bureau_checked": scenario != 11, "credit_bureau_date": as_of - timedelta(days=3) if scenario != 11 else None,
        "has_payment_incidents": scenario in {2, 3, 8}, "max_days_late": 45 if scenario == 3 else 12 if scenario in {2, 8} else 0,
        "incidents_comment": "Incidents simulés : échéances irrégulières à examiner." if scenario in {2, 3, 8} else "Aucun incident dans ce scénario fictif.",
        "prior_loans_count": 4, "prior_repayment_rate": D("92") if scenario in {2, 3, 8} else D("100"),
        "prior_max_delay_days": 30 if scenario == 3 else 0,
        "strengths": "Données détaillées, inventaire, budget du ménage et plan de trésorerie rapprochables (simulation).",
        "weaknesses": f"Scénario de démonstration : {SCENARIOS[scenario]}. Lire les alertes, le stress et les mois creux.",
        "recommended_conditions": "Simulation : documenter les écarts, suivre mensuellement les flux, vérifier l'épargne et les engagements avant toute décision réelle.",
        "comment": f"{MARKER} — {SCENARIOS[scenario]}. Les indicateurs sont calculés par le moteur réel de FIN_FLOW.",
        "sector": "COMMERCE" if corporate or activity else "SERVICES", "sub_sector": "Commerce et services fictifs",
        "value_chain_position": "DISTRIBUTION" if corporate or activity else "SERVICES", "market_dynamic": "GROWTH" if scenario == 6 else "MATURE",
        "seasonality_level": "HIGH" if scenario == 1 else "MEDIUM", "competition_intensity": "MEDIUM",
        "supplier_dependency": "HIGH" if scenario == 7 else "LOW", "client_concentration": "MEDIUM",
        "input_price_sensitivity": "HIGH" if scenario == 7 else "MEDIUM", "fx_exposure": "LOW",
        "regulatory_sensitivity": "LOW", "climate_sensitivity": "MEDIUM", "sector_risk_level": "HIGH" if scenario in {3, 7} else "MEDIUM",
        "sector_outlook": "Perspectives fictives : hausse saisonnière des volumes et suivi des prix d'achat.",
        "sector_comment": "Données simulées : aucune étude externe ni consultation automatique du BIC.",
        "es_category": "C", "es_risk_level": "LOW", "exclusion_list_ok": True,
        "es_regulatory_compliance": True, "waste_management": "GOOD", "resource_use": "IMPROVE",
        "working_conditions": "GOOD", "occupational_safety": "IMPROVE", "community_impact": "GOOD",
        "child_forced_labor_risk": "LOW", "land_resettlement_risk": "LOW",
        "jobs_created": 3 if corporate else 1, "jobs_maintained": 12 if corporate else 2,
        "jobs_women": 2 if corporate else 1, "jobs_youth": 1, "workforce_count": 15 if corporate else 3,
        "es_comment": "Appréciation E&S fictive ; suivi des déchets et des conditions de travail à illustrer.",
        "cashflow_comment": "Prévisions fictives hors nouveau financement : exploitation, investissement et dettes distingués. Les échéances du crédit proviennent du simulateur FIN_FLOW.",
    }
    details = {
        "business_model": "Vente de lots et prestations de livraison simulées ; recettes comptant et créances clients séparées.",
        "seasonality": "Mois creux puis reprise saisonnière ; les coefficients du scénario saisonnier ont une moyenne annuelle égale à un.",
        "sales_verification": "Reconstitution fictive par quantités et prix ; aucun document de tiers utilisé.",
        "stock_risks": "Rotation lente et dépréciation du dernier lot ; inventaire fictif à la date d'arrêté.",
        "receivables_quality": "Créances simulées : contrôle de l'ancienneté, des retards et de la concentration.",
        "asset_ownership": "Patrimoine fictif, distinct des garanties effectivement rattachées dans le jeu de démonstration.",
        "household_income_evidence": "Salaire, revenus du conjoint et revenus d'activité simulés, sans double comptage.",
        "employment_outlook": "Contrat et ancienneté fictifs ; variations de primes illustrées dans le prévisionnel.",
        "bureau_reference": f"SIMULATION-{app.reference}", "bureau_discrepancies": "Écart volontaire dans le scénario de rapprochement." if scenario == 4 else "Engagements fictifs rapprochés.",
        "banking_behavior": "Flux bancaires et mobile money fictifs sur douze mois.",
        "project_cost": f"Coût fictif du projet : {app.project_total_cost} XOF.",
        "own_contribution": f"Apport simulé : {app.personal_contribution} XOF.",
        "financing_plan": "Demande en brouillon : apport + concours demandé. Aucun fonds reçu ni transmis au CBS.",
        "stress_assumptions": "Baisse des ventes/revenus selon le seuil configuré ; hausse des achats et décalage clients lorsque renseignés.",
        "monitoring_plan": "Suivi mensuel du budget, de l'inventaire, du service des dettes et des soldes de clôture.",
        "purchase_stress_pct": "15" if scenario == 7 else "5", "receivable_delay_days": "20" if scenario in {2, 7} and corporate else "0",
        "opening_cash_balance": "150000" if scenario in {2, 3} else "1500000" if corporate else "500000",
    }
    if corporate:
        product_rows = products(factor, cost_ratio=D("1.05") if scenario == 3 else D("0.72") if scenario == 7 else D("0.50"))
        turnover, cogs = total_products(product_rows, "sale_price"), total_products(product_rows, "unit_cost")
        op_weights = {"op_rent": ".025", "op_salaries": ".070", "op_utilities": ".014", "op_transport": ".018",
                      "op_telecom": ".006", "op_taxes": ".012", "op_maintenance": ".008", "op_other": ".027"}
        defaults.update({key: amount(turnover * D(weight)) for key, weight in op_weights.items()})
        opex = sum((defaults[key] for key in op_weights), D("0"))
        defaults.update(turnover=turnover, cogs=cogs, depreciation=amount(turnover * D(".02")), financial_charges=amount(turnover * D(".006")),
            stock_value=amount(D("6000000") * factor), receivables=amount(D("3500000") * factor),
            cash_in_hand=D("200000"), bank_balance=D("1800000") if scenario != 5 else D("50000"), other_current_assets=D("400000"),
            land_building_value=D("8000000") if scenario != 5 else D("45000000"), equipment_value=D("3500000"), vehicle_value=D("2000000"), other_fixed_assets=D("500000"),
            supplier_debt=D("2200000"), tax_social_debt=D("450000"), other_current_debt=D("200000"), short_term_debt=D("300000"), shareholder_debt=D("1000000"),
            turnover_prev=amount(turnover * (D(".72") if scenario == 6 else D(".92"))), net_result_prev=D("-1200000") if scenario == 6 else D("5500000"))
        taxable = max(D("0"), turnover - cogs - opex - defaults["depreciation"] - defaults["financial_charges"])
        details.update(products=product_rows, stocks=inventory(defaults["stock_value"], as_of), cash_detail_mode="DETAIL", fixed_assets_detail_mode="DETAIL",
            income_tax_expense=text_amount(taxable * D(".18")), provision_expense="120000", provision_reversal="30000", exceptional_income="180000", exceptional_expense="60000",
            fixed_operating_costs=text_amount(opex * D(".7")), variable_operating_costs=text_amount(opex * D(".3")), bfr_change="240000", maintenance_investment="180000",
            opening_stock=text_amount(defaults["stock_value"] * D(".85")), opening_receivables=text_amount(defaults["receivables"] * D(".9")),
            opening_supplier_debt="1800000", period_purchases=text_amount(cogs + defaults["stock_value"] * D(".15")))
        monthly_in = turnover / 12
        monthly_out = (cogs + opex + D(details["income_tax_expense"])) / 12
    elif group:
        members = 36 + int(factor * 4)
        defaults.update(members_count=members, active_contributing_members=members - (15 if scenario in {3, 8} else 3),
            members_with_arrears=12 if scenario in {3, 8} else 2, solidarity_commitment=scenario != 3,
            group_age_months=72, group_records_verified=scenario != 11, collective_savings_locked=True,
            collective_contributions=amount(D("650000") * factor * periods_months), collective_other_income=D("50000") * periods_months,
            collective_operating_expenses=D("120000") * periods_months, group_activity_turnover=D("1200000") * factor * periods_months,
            group_activity_expenses=D("2100000") * periods_months if scenario == 3 else D("700000") * factor * periods_months,
            collective_savings=D("3500000"), group_comment="Simulation : cotisations, activité commune et épargne sont distinctes.")
        details["products"] = [{"name": "Prestations collectives", "unit": "ensemble de la période", "quantity": "1",
                                "sale_price": str(defaults["group_activity_turnover"]), "unit_cost": str(defaults["group_activity_expenses"]), "comment": "Activité collective fictive."}]
        monthly_in = (defaults["collective_contributions"] + defaults["collective_other_income"] + defaults["group_activity_turnover"]) / periods_months
        monthly_out = (defaults["collective_operating_expenses"] + defaults["group_activity_expenses"]) / periods_months
    else:
        defaults.update(individual_profile={"SAL": "SALARIE", "IND": "INDEPENDANT", "MIX": "MIXTE"}[profile],
            salary_income=(D("140000") if scenario == 3 else D("480000") * factor) * periods_months if profile != "IND" else D("0"),
            spouse_income=D("70000") * periods_months if profile != "IND" and scenario != 3 else D("0"),
            rental_income=D("40000") * periods_months if scenario == 5 else D("0"), variable_income=D("30000") * periods_months if profile != "IND" else D("0"),
            employer_name="Employeur fictif — Services Démo" if profile != "IND" else "", employer_sector="Services fictifs",
            employment_type="FIXED_TERM" if scenario == 3 else "PERMANENT" if profile != "IND" else "OTHER",
            employment_seniority_months=8 if scenario == 3 else 60, salary_deductions=D("10000") * periods_months if profile != "IND" else D("0"),
            salary_paid_through_bank=profile != "IND", salary_verified=profile != "IND" and scenario != 11,
            personal_savings=D("600000"), personal_real_estate_value=D("35000000") if scenario == 5 else D("5000000"),
            personal_vehicle_value=D("4500000"), personal_productive_assets=D("1800000"), informal_income_weight=D("70"), has_side_activity=activity)
        charges = {"rent_expense": 60000, "food_expense": 70000, "utilities_expense": 18000, "transport_expense": 20000,
                   "education_expense": 20000, "health_expense": 10000, "other_household_expenses": 5000,
                   "tontine_expense": 5000, "social_contributions": 2000, "family_support_expense": 5000, "other_monthly_obligations": 3000}
        defaults.update({key: D(value) * periods_months for key, value in charges.items()})
        monthly_in = (defaults["salary_income"] + defaults["spouse_income"] + defaults["rental_income"] + defaults["variable_income"]) / periods_months
        monthly_out = sum((D(value) for value in charges.values()), D("0"))
        if activity:
            product_rows = products(factor * periods_months, divisor=20 if profile == "IND" else 40,
                                    cost_ratio=D("1.05") if scenario == 3 else D(".55"))
            turnover, purchases = total_products(product_rows, "sale_price"), total_products(product_rows, "unit_cost")
            expenses = purchases + amount(turnover * D(".18"))
            defaults.update(activity_name="Boutique et livraison fictives", activity_business_age_months=48, activity_sales_days=26 * int(periods_months),
                activity_turnover=turnover, activity_purchases=purchases, activity_expenses=expenses,
                activity_stock_value=D("1200000"), activity_receivables=D("350000"), activity_cash_available=D("250000"),
                activity_fixed_assets=D("2000000"), activity_supplier_debt=D("400000"), activity_is_formal=True, activity_records_available=scenario != 11,
                activity_comment="Activité fictive. Les achats sont inclus dans les charges ; les bénéfices ne sont pas ajoutés une seconde fois aux autres revenus.")
            details.update(products=product_rows, stocks=inventory(defaults["activity_stock_value"], as_of))
            monthly_in += turnover / periods_months
            monthly_out += expenses / periods_months
    defaults["projected_monthly_inflows"] = amount(monthly_in)
    defaults["projected_monthly_outflows"] = amount(monthly_out)
    return defaults, details, monthly_in, monthly_out, periods_months


class Command(BaseCommand):
    help = "Crée des dossiers financiers VISU- fictifs en brouillon, uniquement en développement local."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="FIL01")
        parser.add_argument("--author", default="fil01_admin")
        parser.add_argument("--count", type=int, default=60)
        parser.add_argument("--manifest", default="documentation/30-jeu-demonstration-financiere.md")

    def handle(self, *args, **options):
        if not settings.DEBUG or settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3":
            raise CommandError("Cette commande est réservée au développement local SQLite avec DEBUG=True.")
        count = options["count"]
        if not 5 <= count <= 200 or count % 5:
            raise CommandError("--count doit être un multiple de 5, entre 5 et 200.")
        try:
            tenant = Tenant.objects.get(code=options["tenant"])
            author = User.objects.get(username=options["author"], tenant=tenant, is_active=True)
        except (Tenant.DoesNotExist, User.DoesNotExist) as exc:
            raise CommandError("La filiale et son auteur actif doivent déjà exister.") from exc
        root = settings.BASE_DIR.parent.resolve()
        manifest = (root / options["manifest"]).resolve()
        if not manifest.is_relative_to(root) or manifest.suffix != ".md":
            raise CommandError("Le manifeste doit être un fichier .md dans ce projet.")
        as_of = timezone.localdate()
        first_month = as_of.replace(day=1) + relativedelta(months=1)
        created, skipped, rows = Counter(), 0, []
        with tenant_context(tenant.id), transaction.atomic():
            agencies = list(Agency.objects.filter(is_active=True).order_by("code"))
            if not agencies:
                raise CommandError("Une agence active est nécessaire.")
            catalogue = list(CreditProduct.objects.filter(is_active=True, currency="XOF").order_by("code"))
            if not catalogue:
                raise CommandError("Un produit XOF actif est nécessaire.")
            for index in range(count):
                code, label, client_type, individual_profile = PROFILES[index % 5]
                scenario = (index // 5) % len(SCENARIOS)
                factor = D("1") + D(index // 5 % 3) / 10
                reference = f"VISU-{code}-{index + 1:03d}"
                if CreditApplication.objects.filter(reference=reference).exists():
                    app = CreditApplication.objects.get(reference=reference)
                    skipped += 1
                    rows.append((app, label, SCENARIOS[scenario]))
                    continue
                agency = agencies[index % len(agencies)]
                client = Client.objects.create(tenant=tenant, reference=f"VISU-CLI-{code}-{index + 1:03d}", agency=agency,
                    client_type=client_type, first_name="Démo" if client_type == "INDIVIDUAL" else "",
                    last_name=f"{label} {index + 1:03d} — {SCENARIOS[scenario]}" if client_type == "INDIVIDUAL" else "",
                    company_name=f"DÉMO {label} {index + 1:03d} — {SCENARIOS[scenario]}" if client_type != "INDIVIDUAL" else "",
                    kyc_status="PENDING", created_by=author, updated_by=author)
                preferred = "TRESO-STD" if code == "ENT" else "TRESO-PRO" if code in {"IND", "MIX", "GRP"} else "CONSO-STD"
                compatible = [p for p in catalogue if p.client_type in {"ALL", client_type}]
                if not compatible:
                    raise CommandError(f"Aucun produit compatible avec {label}.")
                product = next((p for p in compatible if p.code == preferred), compatible[0])
                requested = D("3000000") if code == "ENT" else D("2400000") if code == "GRP" else D("1200000") if code in {"IND", "MIX"} else D("900000")
                requested = min(product.amount_max, max(product.amount_min, requested * factor))
                months = min(product.duration_max_months, max(product.duration_min_months, 24 if code in {"ENT", "GRP"} else 18))
                app = CreditApplication.objects.create(tenant=tenant, client=client, product=product, agency=agency,
                    reference=reference, status="DRAFT", amount_requested=requested, amount_proposed=requested,
                    duration_months=months, periodicity="QUARTERLY" if scenario == 10 else "MONTHLY",
                    repayment_mechanism="IN_FINE" if scenario == 9 else "DEGRESSIVE", first_due_date=first_month + relativedelta(months=2 if scenario == 10 else 0) + timedelta(days=14),
                    interest_rate=product.interest_rate, mandatory_savings_rate=D(".50") + D(index % 3) / 4,
                    currency="XOF", purpose_type="TREASURY", purpose=f"{MARKER} — {SCENARIOS[scenario]}. Brouillon pour lecture visuelle uniquement.",
                    project_total_cost=amount(requested * D("1.3")), personal_contribution=amount(requested * D(".3")),
                    dependents_count=index % 5, created_by=author, updated_by=author)
                # Garanties/cautions fictives : aucun acte ni contrat signé créé.
                value = requested * (D(".4") if scenario in {3, 8} else D("2"))
                Guarantee.objects.create(tenant=tenant, reference=f"VISU-GAR-{index + 1:03d}", application=app, client=client,
                    agency=agency, guarantee_type="MORTGAGE" if code == "ENT" else "DEPOSIT", current_value=value,
                    expertise_value=value, description=f"{MARKER} : valeur de garantie simulée, sans justificatif réel.",
                    status="ACTIVE", created_by=author, updated_by=author)
                created["guarantees"] += 1
                if index % 2 == 0:
                    surety = Surety.objects.create(tenant=tenant, agency=agency, first_name="Démo", last_name=f"Caution VISU {index + 1:03d}",
                        estimated_income=D("750000"), commitment_ceiling=requested * 3, created_by=author, updated_by=author)
                    SuretyEngagement.objects.create(tenant=tenant, application=app, surety=surety, amount=requested,
                        status="ACTIVE", notes=f"{MARKER} — engagement simulé non signé.")
                    created["sureties"] += 1
                defaults, details, monthly_in, monthly_out, period_months = build_analysis(app, code, scenario, factor, as_of)
                defaults.update(individual_profile=individual_profile, tenant=tenant, application=app, created_by=author, updated_by=author,
                    author_role=MARKER, is_reference=True)
                existing = D("240000") if scenario == 8 else D("90000") if code == "ENT" else D("45000") if code == "GRP" else D("30000")
                lenders = 4 if scenario == 8 else 2
                debt_rows = [{"lender": f"Prêteur fictif {i + 1}", "kind": "Crédit amortissable simulé", "outstanding": text_amount(D("400000") * (i + 1)),
                              "monthly_payment": text_amount(existing / lenders), "arrears": "15000" if scenario in {3, 8} and i == 0 else "0",
                              "maturity": (as_of + relativedelta(months=12 + i * 6)).isoformat(), "comment": "Source fictive, périodicité mensuelle, hors nouveau prêt."} for i in range(lenders)]
                defaults.update(existing_debt_monthly=existing, existing_debt_initial_amount=D("1500000"), existing_debt_institution="Prêteur fictif principal",
                    ongoing_credit_balance=sum((D(row["outstanding"]) for row in debt_rows), D("0")), active_loans_count=lenders)
                if code == "ENT":
                    defaults["long_term_debt"] = amount(defaults["ongoing_credit_balance"] * D(".6"))
                details["debts"] = debt_rows
                analysis = FinancialAnalysis(**defaults, analysis_details=details)
                schedule = analysis._compute_loan_schedule()
                if not schedule:
                    raise CommandError(f"Échéancier non calculable pour {reference}.")
                by_month = Counter()
                for installment in schedule:
                    by_month[installment["due_date"].isoformat()[:7]] += installment["total"]
                cashflow = []
                for offset in range(max(18, months)):
                    month = first_month + relativedelta(months=offset)
                    coefficient = SEASON[offset % 12] if scenario == 1 else D("1") + D((offset % 4) - 1) / 50
                    inflows = monthly_in * coefficient
                    if scenario == 6:
                        inflows *= 1 + D(offset) / 100
                    if scenario == 2 and offset < 4:
                        inflows *= D(".35")
                    outflows = monthly_out * (D("1.15") if scenario == 7 else D("1"))
                    cashflow.append({"month": month.strftime("%Y-%m"), "inflows": text_amount(inflows), "outflows": text_amount(outflows),
                        "investment": "300000" if offset in {2, 8} and code != "SAL" else "0",
                        "existing_service": text_amount(existing), "new_service": text_amount(by_month[month.strftime("%Y-%m")]),
                        "comment": "Mois creux fictif" if coefficient < 1 else "Reprise fictive" if coefficient > 1 else "Hypothèse stable fictive"})
                details["cashflow"] = cashflow
                if code != "SAL":
                    current_sales = defaults.get("turnover", defaults.get("activity_turnover", defaults.get("group_activity_turnover", D("0"))))
                    details["history"] = [{"period": f"Exercice {as_of.year - n} — annuel", "turnover": text_amount(current_sales / period_months * 12 * (1 - D(n) / 10)),
                        "net_result": text_amount(current_sales / period_months * 12 * (D(".12") - D(n) / 100)),
                        "cashflow": text_amount(current_sales / period_months * 12 * D(".15")), "equity": text_amount(D("2000000") * (4 - n)),
                        "comment": "Historique annuel fictif, à distinguer de la période courante."} for n in (3, 2, 1)]
                if code == "ENT":
                    details["declared_equity"] = text_amount(analysis.equity)
                if scenario == 4:
                    details["debts"][0]["outstanding"] = text_amount(D(details["debts"][0]["outstanding"]) + 150000)
                    details["debts"][0]["monthly_payment"] = text_amount(D(details["debts"][0]["monthly_payment"]) + 10000)
                    if details.get("products"):
                        details["products"][0]["sale_price"] = text_amount(D(details["products"][0]["sale_price"]) * D(".8"))
                    if details.get("stocks"):
                        details["stocks"][0]["unit_cost"] = text_amount(D(details["stocks"][0]["unit_cost"]) - 50000)
                    details["cashflow"][0]["new_service"] = "0"
                if scenario == 11:
                    details.pop("opening_cash_balance", None)
                    details["cashflow"] = [row for i, row in enumerate(cashflow) if i != 4]
                    if details.get("stocks"):
                        details["stocks"][0]["unit_cost"] = ""
                analysis.analysis_details = validate_details(details)
                analysis.recommendation = "UNFAVORABLE" if scenario == 3 else "CONDITIONAL" if scenario in {1, 2, 4, 5, 7, 8, 9, 11} else "FAVORABLE"
                analysis.save()
                created["analyses"] += 1
                FieldVisit.objects.create(tenant=tenant, application=app, visited_by=author, visit_date=as_of,
                    report=f"{MARKER}. Visite simulée : activité, inventaire, équipements et flux déclaratifs décrits dans l'analyse. Scénario : {SCENARIOS[scenario]}.")
                created["visits"] += 1
                if scenario in {0, 1, 4, 8}:
                    secondary = deepcopy(details)
                    secondary["monitoring_plan"] += " Contre-analyse fictive : rapprocher les hypothèses avec les informations du ménage et le plan d'échéances."
                    other = {**defaults, "is_reference": False, "author_role": "VISU — contre-analyse fictive",
                             "analysis_details": validate_details(secondary), "recommendation": "CONDITIONAL",
                             "comment": f"{MARKER}. Deuxième lecture de démonstration, distincte de l'analyse de référence."}
                    FinancialAnalysis.objects.create(**other)
                    created["analyses"] += 1
                created["clients"] += 1
                created["dossiers"] += 1
                rows.append((app, label, SCENARIOS[scenario]))
        # Manifeste après commit : liens directs et observations issues du moteur.
        lines = ["# Jeu de démonstration de l'analyse financière", "", f"Filiale : **{tenant.code} — {tenant.name}**. Données entièrement fictives, préfixe **VISU-**.", "",
                 "Tous les dossiers de ce jeu sont créés en brouillon, avec KYC à vérifier. Les recommandations et vérifications financières sont des simulations. Aucun workflow, contrat signé, prêt, décaissement ni appel CBS n'est créé.", "",
                 "Dans **Dossiers de crédit**, rechercher `VISU-`. Ouvrir **Analyse financière**, puis déplier les données, les prévisions, les rapprochements et les formules.", "",
                 "Chaque dossier comprend 18 à 24 mois de trésorerie (un mois retiré volontairement dans les cas partiels), des engagements détaillés, des garanties et une visite fictive. Les activités disposent de produits, stocks et historiques adaptés. Certains écarts ou manques sont intentionnels.", "",
                 "| Dossier | Profil | Scénario | Capacité / mois | Reste après crédit | Score courant |", "|---|---|---|---:|---:|---:|"]
        with tenant_context(tenant.id):
            selected_ids = [app.id for app, _, _ in rows]
            totals = {"dossiers": len(selected_ids), "analyses": FinancialAnalysis.objects.filter(application_id__in=selected_ids).count(),
                      "garanties": Guarantee.objects.filter(application_id__in=selected_ids).count(),
                      "cautions": SuretyEngagement.objects.filter(application_id__in=selected_ids).count()}
            lines[4:4] = [f"Contenu : **{totals['dossiers']} dossiers**, **{totals['analyses']} analyses**, **{totals['garanties']} garanties**, **{totals['cautions']} engagements de caution**.", ""]
            for app, label, scenario_label in rows:
                reference = app.financial_analyses.filter(is_reference=True).first()
                if reference:
                    metrics = compute_metrics(reference, AnalysisThreshold.for_application(app, individual_profile=reference.individual_profile), recalculate_installment=True)
                    capacity, residual = metrics.get("repayment_capacity"), metrics.get("safety_margin")
                    score = reference.internal_score
                else:
                    capacity = residual = score = None
                money = lambda value: f"{value:,.0f}".replace(",", " ") if value is not None else "—"
                lines.append(f"| [{app.reference}](http://127.0.0.1:5173/dossiers/{app.id}) | {label} | {scenario_label} | {money(capacity)} | {money(residual)} | {money(score)} |")
        lines.extend(["", "## Reproduire le jeu en local", "", "Depuis la racine du projet :", "", "```powershell",
                      f".\\.venv\\Scripts\\python.exe backend/manage.py seed_financial_showcase --tenant {tenant.code} --author {author.username} --count {count}",
                      "```", "", "La commande nécessite DEBUG=True et SQLite. Elle conserve les dossiers VISU- déjà présents, sans les réécrire, et n'altère ni les habilitations ni les configurations de la filiale.",
                      "Les capacités et scores restent calculés avec les règles configurées au moment de l'exécution : leur valeur peut évoluer si ces règles changent."])
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Créés : {dict(created)}. Dossiers déjà présents conservés : {skipped}."))
        self.stdout.write(f"Manifeste : {manifest}")
