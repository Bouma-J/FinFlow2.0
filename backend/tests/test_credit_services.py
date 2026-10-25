"""Tests des services de crédit (simulation d'amortissement)."""
from datetime import date
from decimal import Decimal

from apps.credits.services import compute_amortization_schedule


def test_amortization_schedule_totals():
    schedule = compute_amortization_schedule(
        Decimal("1200000"), Decimal("12"), 12, mechanism="DEGRESSIVE"
    )
    assert len(schedule) == 12
    total_principal = sum(row["principal"] for row in schedule)
    assert total_principal == Decimal("1200000")
    total_interest = sum(row["interest"] for row in schedule)
    assert total_interest > 0
    assert all(
        row["institution_due"] == row["principal"] + row["interest"]
        for row in schedule
    )


def test_amortization_zero_rate():
    schedule = compute_amortization_schedule(
        Decimal("1200"), Decimal("0"), 12, mechanism="DEGRESSIVE"
    )
    total_principal = sum(row["principal"] for row in schedule)
    assert total_principal == Decimal("1200")
    assert all(row["interest"] == Decimal("0") for row in schedule)


def test_amortization_degressive_constant_installment():
    """Dégressif : échéance constante, intérêts ↓, capital ↑."""
    schedule = compute_amortization_schedule(
        Decimal("1000000"),
        Decimal("12"),
        12,
        mechanism="DEGRESSIVE",
        start_date=date(2026, 1, 1),
        first_due_date=date(2026, 2, 1),
    )
    assert len(schedule) == 12
    assert sum(row["principal"] for row in schedule) == Decimal("1000000")

    dues = [row["institution_due"] for row in schedule[:-1]]
    assert len(set(dues)) == 1

    assert schedule[0]["interest"] > schedule[-2]["interest"]
    assert schedule[0]["principal"] < schedule[-2]["principal"]


def test_amortization_degressive_first_period_theoretical_month():
    """CBS : 1er intérêt = période théorique pleine depuis la date d'effet."""
    # Échéance anticipée (25 j calendaires) mais intérêts sur 31 j (11/10→11/11)
    schedule = compute_amortization_schedule(
        Decimal("100000000"),
        Decimal("17"),
        12,
        mechanism="DEGRESSIVE",
        start_date=date(2023, 10, 11),
        first_due_date=date(2023, 11, 5),
        savings_rate=Decimal("1"),
    )
    assert schedule[0]["interest"] == Decimal("1443840")
    assert schedule[0]["savings"] == Decimal("1000000")

    # Échéance reportée (50 j) : toujours 31 j d'intérêts au départ
    schedule2 = compute_amortization_schedule(
        Decimal("1000000"),
        Decimal("17"),
        12,
        mechanism="DEGRESSIVE",
        start_date=date(2023, 10, 16),
        first_due_date=date(2023, 12, 5),
        savings_rate=Decimal("1"),
    )
    assert schedule2[0]["interest"] == Decimal("14440")
    assert schedule2[0]["savings"] == Decimal("10000")


def test_amortization_degressive_cbs_fongip_first_interest():
    """Cas FONGIP 4M / 9 % : 1er intérêt sur 31 j théoriques (arrondi dizaine)."""
    schedule = compute_amortization_schedule(
        Decimal("4000000"),
        Decimal("9"),
        22,
        mechanism="DEGRESSIVE",
        start_date=date(2023, 10, 4),
        first_due_date=date(2023, 12, 5),
    )
    # CBS affiche parfois 30 575 (pas 5) ; FinFlow conserve l'arrondi à la dizaine.
    assert schedule[0]["interest"] == Decimal("30580")


def test_amortization_in_fine():
    schedule = compute_amortization_schedule(
        Decimal("1000000"), Decimal("12"), 12, mechanism="IN_FINE"
    )
    assert len(schedule) == 12
    assert all(row["principal"] == 0 for row in schedule[:-1])
    assert schedule[-1]["principal"] == Decimal("1000000")


def test_amortization_bullet():
    schedule = compute_amortization_schedule(
        Decimal("1000000"),
        Decimal("12"),
        12,
        mechanism="BULLET",
        start_date=date(2026, 1, 1),
        first_due_date=date(2026, 2, 1),
    )
    assert len(schedule) == 1
    assert schedule[0]["principal"] == Decimal("1000000")


def test_savings_excluded_from_institution_due():
    schedule = compute_amortization_schedule(
        Decimal("1000000"),
        Decimal("12"),
        12,
        savings_rate=Decimal("5"),
        mechanism="DEGRESSIVE",
    )
    assert schedule[0]["savings"] > 0
    assert schedule[0]["institution_due"] == (
        schedule[0]["principal"] + schedule[0]["interest"]
    )
    assert schedule[0]["total"] == (
        schedule[0]["institution_due"] + schedule[0]["savings"]
    )
