"""Référentiels catalogue par défaut (périodicités, remboursements, devises)."""
from __future__ import annotations

DEFAULT_PERIODICITIES = (
    ("DAILY", "Journalier", "JOURNALIER", 360, 10),
    ("WEEKLY", "Hebdomadaire", "HEBDOMADAIRE", 52, 20),
    ("BIMONTHLY", "Bimensuelle", "BIMENSUEL", 24, 25),
    ("MONTHLY", "Mensuelle", "MENSUEL", 12, 30),
    ("QUARTERLY", "Trimestrielle", "TRIMESTRIEL", 4, 40),
    ("SEMIANNUAL", "Semestrielle", "SEMESTRIEL", 2, 50),
    ("ANNUAL", "Annuelle", "ANNUEL", 1, 60),
)

DEFAULT_REPAYMENT_METHODS = (
    ("DEGRESSIVE", "Amortissement dégressif", "COMPTE-COURANT", 10),
    ("IN_FINE", "In fine (capital à terme)", "COMPTE-COURANT", 20),
    ("BULLET", "Remboursement unique (bullet)", "COMPTE-COURANT", 30),
)

DEFAULT_CURRENCIES = (
    ("XOF", "Franc CFA BCEAO (XOF)", "XOF", 10),
    ("XAF", "Franc CFA BEAC (XAF)", "XAF", 20),
    ("EUR", "Euro (EUR)", "EUR", 30),
    ("USD", "Dollar US (USD)", "USD", 40),
    ("GNF", "Franc guinéen (GNF)", "GNF", 50),
    ("MAD", "Dirham marocain (MAD)", "MAD", 60),
)


def ensure_catalog_defaults(tenant) -> dict:
    """Crée les référentiels CBS manquants pour une filiale (idempotent)."""
    from .models import Currency, LoanPeriodicity, RepaymentMethod

    created = {"periodicities": 0, "repayment_methods": 0, "currencies": 0}

    for code, label, cbs_code, periods, order in DEFAULT_PERIODICITIES:
        _, was_created = LoanPeriodicity.all_tenants.get_or_create(
            tenant=tenant,
            code=code,
            defaults={
                "label": label,
                "cbs_code": cbs_code,
                "periods_per_year": periods,
                "sort_order": order,
                "is_active": True,
            },
        )
        if was_created:
            created["periodicities"] += 1

    for code, label, cbs_code, order in DEFAULT_REPAYMENT_METHODS:
        _, was_created = RepaymentMethod.all_tenants.get_or_create(
            tenant=tenant,
            code=code,
            defaults={
                "label": label,
                "cbs_code": cbs_code,
                "sort_order": order,
                "is_active": True,
            },
        )
        if was_created:
            created["repayment_methods"] += 1

    for code, label, cbs_code, order in DEFAULT_CURRENCIES:
        _, was_created = Currency.all_tenants.get_or_create(
            tenant=tenant,
            code=code,
            defaults={
                "label": label,
                "cbs_code": cbs_code,
                "sort_order": order,
                "is_active": True,
            },
        )
        if was_created:
            created["currencies"] += 1

    return created
