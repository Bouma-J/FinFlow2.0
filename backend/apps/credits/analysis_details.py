"""Données structurées de reconstitution, communes à la banque et au SFD.

Les tableaux complètent les agrégats ; les écarts sont signalés et restent
explicitement à rapprocher par l'analyste, sans écrasement de sa saisie.
"""
from datetime import date
from decimal import Decimal, InvalidOperation

from rest_framework.exceptions import ValidationError


DETAIL_SCHEMAS = {
    "products": {
        "name": "text", "unit": "text", "quantity": "amount",
        "sale_price": "amount", "unit_cost": "amount", "comment": "text",
    },
    "stocks": {
        "name": "text", "quantity": "amount", "unit_cost": "amount",
        "impaired_value": "amount", "count_date": "date", "comment": "text",
    },
    "debts": {
        "lender": "text", "kind": "text", "outstanding": "amount",
        "monthly_payment": "amount", "arrears": "amount", "maturity": "date",
        "comment": "text",
    },
    "cashflow": {
        "month": "month", "inflows": "amount", "outflows": "amount",
        "existing_service": "amount", "new_service": "amount",
        "investment": "amount", "comment": "text",
    },
    "history": {
        "period": "text", "turnover": "amount", "net_result": "signed",
        "cashflow": "signed", "equity": "signed", "comment": "text",
    },
}
DETAIL_TEXTS = {
    "business_model", "seasonality", "sales_verification", "stock_risks",
    "receivables_quality", "asset_ownership", "household_income_evidence",
    "employment_outlook", "project_cost", "own_contribution",
    "financing_plan", "stress_assumptions", "monitoring_plan",
    "bureau_reference", "bureau_discrepancies", "banking_behavior",
}

# Compléments facultatifs : l'absence reste distincte d'un zéro renseigné.
DETAIL_AMOUNTS = {
    "opening_cash_balance": "signed", "declared_equity": "signed",
    "bfr_change": "signed", "maintenance_investment": "amount",
    "income_tax_expense": "amount", "provision_expense": "amount",
    "provision_reversal": "amount", "exceptional_income": "amount",
    "exceptional_expense": "amount", "fixed_operating_costs": "amount",
    "variable_operating_costs": "amount", "period_purchases": "amount",
    "opening_stock": "amount", "opening_receivables": "amount",
    "opening_supplier_debt": "amount", "purchase_stress_pct": "percent",
    "receivable_delay_days": "amount",
}


def detail_amount(analysis, key, default=Decimal("0")):
    value = (analysis.analysis_details or {}).get(key)
    return default if value in (None, "") else Decimal(str(value))


def validate_details(value):
    if not isinstance(value, dict):
        raise ValidationError("Le détail de l'analyse doit être un objet.")
    unknown = set(value) - set(DETAIL_SCHEMAS) - DETAIL_TEXTS - set(DETAIL_AMOUNTS) - {"cash_detail_mode", "fixed_assets_detail_mode"}
    if unknown:
        raise ValidationError(f"Rubriques inconnues : {', '.join(sorted(unknown))}.")
    for key, text in value.items():
        if key in {"cash_detail_mode", "fixed_assets_detail_mode"}:
            if text not in ("", "DETAIL", "LEGACY"):
                raise ValidationError({key: "Choisissez DETAIL ou LEGACY."})
            continue
        if key in DETAIL_AMOUNTS:
            if text in (None, ""):
                continue
            try:
                number = Decimal(str(text))
                valid = number.is_finite() and abs(number) < Decimal("1e16")
                valid = valid and (DETAIL_AMOUNTS[key] == "signed" or number >= 0)
                valid = valid and (DETAIL_AMOUNTS[key] != "percent" or number <= 100)
            except (InvalidOperation, TypeError, ValueError):
                valid = False
            if not valid:
                raise ValidationError({key: "Montant invalide."})
            continue
        if key in DETAIL_TEXTS:
            if not isinstance(text, str) or len(text) > 10000:
                raise ValidationError({key: "Texte attendu, limité à 10 000 caractères."})
            continue
        rows = text
        if not isinstance(rows, list) or len(rows) > 120:
            raise ValidationError({key: "Tableau attendu, limité à 120 lignes."})
        months = set()
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or set(row) - set(DETAIL_SCHEMAS[key]):
                raise ValidationError({key: f"Ligne {index + 1} : colonnes invalides."})
            for field, content in row.items():
                if content in ("", None):
                    continue
                kind = DETAIL_SCHEMAS[key][field]
                valid = True
                if kind in ("amount", "signed"):
                    try:
                        number = Decimal(str(content))
                        valid = number.is_finite() and abs(number) < Decimal("1e16")
                        valid = valid and (kind == "signed" or number >= 0)
                    except (InvalidOperation, ValueError):
                        valid = False
                elif kind in ("date", "month"):
                    try:
                        date.fromisoformat(str(content) + ("-01" if kind == "month" else ""))
                        if kind == "month":
                            valid = str(content) not in months
                            months.add(str(content))
                    except ValueError:
                        valid = False
                else:
                    valid = isinstance(content, str) and len(content) <= 1000
                if not valid:
                    raise ValidationError({key: f"Ligne {index + 1}, {field} : valeur invalide."})
            if key == "stocks":
                total = Decimal(str(row.get("quantity") or 0)) * Decimal(str(row.get("unit_cost") or 0))
                if Decimal(str(row.get("impaired_value") or 0)) > total:
                    raise ValidationError({key: f"Ligne {index + 1} : dépréciation supérieure au stock brut."})
    return value


def detail_metrics(analysis):
    details = analysis.analysis_details or {}

    def number(row, key):
        return Decimal(str(row.get(key) or 0))

    metrics = {}
    if details.get("products"):
        sales_complete = all(all(row.get(key) not in (None, "") for key in ("quantity", "sale_price")) for row in details["products"])
        costs_complete = all(all(row.get(key) not in (None, "") for key in ("quantity", "unit_cost")) for row in details["products"])
        metrics["product_details_complete"] = sales_complete and costs_complete
        metrics["reconstituted_sales"] = sum(
            (number(row, "quantity") * number(row, "sale_price")
             for row in details["products"]), Decimal("0")
        ) if sales_complete else None
        metrics["reconstituted_cost"] = sum(
            (number(row, "quantity") * number(row, "unit_cost") for row in details["products"]), Decimal("0")
        ) if costs_complete else None
        metrics["reconstituted_margin"] = metrics["reconstituted_sales"] - metrics["reconstituted_cost"] if sales_complete and costs_complete else None
        declared = analysis.turnover if analysis.is_corporate else analysis.activity_turnover if analysis.is_individual else analysis.group_activity_turnover
        metrics["sales_gap"] = metrics["reconstituted_sales"] - Decimal(str(declared or 0)) if sales_complete else None
        metrics["sales_reconciled"] = abs(metrics["sales_gap"]) <= Decimal("0.01") if sales_complete else None
    if details.get("stocks"):
        complete = all(all(row.get(key) not in (None, "") for key in ("quantity", "unit_cost")) for row in details["stocks"])
        metrics["stock_details_complete"] = complete
        metrics["inventory_net_value"] = sum(
            (number(row, "quantity") * number(row, "unit_cost")
             - number(row, "impaired_value") for row in details["stocks"]),
            Decimal("0"),
        ) if complete else None
        declared = analysis.stock_value if analysis.is_corporate else analysis.activity_stock_value if analysis.is_individual else None
        metrics["stock_gap"] = metrics["inventory_net_value"] - Decimal(str(declared)) if declared is not None and complete else None
        metrics["stock_reconciled"] = abs(metrics["stock_gap"]) <= Decimal("0.01") if metrics["stock_gap"] is not None else None
    if details.get("debts"):
        metrics["debt_details_complete"] = all(all(row.get(key) not in (None, "") for key in ("outstanding", "monthly_payment")) for row in details["debts"])
        for target, column in (
            ("detailed_debt_outstanding", "outstanding"),
            ("detailed_debt_monthly", "monthly_payment"),
            ("detailed_debt_arrears", "arrears"),
        ):
            complete = all(row.get(column) not in (None, "") for row in details["debts"])
            metrics[target] = sum(
                (number(row, column) for row in details["debts"]), Decimal("0")
            ) if complete else None
        metrics["debt_service_reconciled"] = (
            metrics["detailed_debt_monthly"] is not None and abs(metrics["detailed_debt_monthly"] - analysis.existing_debt_monthly) <= Decimal("0.01")
        )
        metrics["outstanding_gap"] = metrics["detailed_debt_outstanding"] - analysis.ongoing_credit_balance if metrics["detailed_debt_outstanding"] is not None else None
        metrics["outstanding_reconciled"] = abs(metrics["outstanding_gap"]) <= Decimal("0.01") if metrics["outstanding_gap"] is not None else None
    if details.get("cashflow"):
        rows = sorted(details["cashflow"], key=lambda row: row.get("month") or "")
        months = [row.get("month") for row in rows]
        complete = all(months) and len(set(months)) == len(months)
        if complete:
            ordinals = [int(month[:4]) * 12 + int(month[5:7]) for month in months]
            complete = all(right - left == 1 for left, right in zip(ordinals, ordinals[1:]))
        balance = detail_amount(analysis, "opening_cash_balance", None) if complete else None
        opening = balance
        forecast, flows, closings = [], [], []
        for row in rows:
            flow = (number(row, "inflows") - number(row, "outflows") - number(row, "investment")
                    - number(row, "existing_service") - number(row, "new_service"))
            start = balance
            balance = balance + flow if balance is not None else None
            forecast.append({"month": row.get("month"), "opening": start, "net_flow": flow, "closing": balance,
                             "existing_service": number(row, "existing_service"), "new_service": number(row, "new_service")})
            flows.append(flow)
            if balance is not None:
                closings.append(balance)
        metrics.update({
            "forecast_rows": forecast, "forecast_complete": bool(complete),
            "forecast_opening_balance": opening, "forecast_lowest_flow": min(flows),
            "forecast_lowest_balance": min(closings) if closings else None,
            "forecast_closing_balance": balance,
            "forecast_negative_flow_months": sum(flow < 0 for flow in flows),
            "forecast_cash_deficit_months": sum(item < 0 for item in closings) if closings else None,
            # Compatibilité du contrôle de soumission : préférer la trésorerie
            # cumulée lorsqu'elle est connue, sinon conserver l'alerte sur flux.
            "forecast_deficit_months": sum(item < 0 for item in closings) if closings else sum(flow < 0 for flow in flows),
        })
    return metrics
