"""Montant de référence d'un dossier selon son statut."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation


def _dec(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


# Statuts où le montant accordé est la source de vérité contractuelle.
_APPROVED_LIKE = frozenset({
    "APPROVED",
    "CONTRACT_GENERATED",
    "DISBURSEMENT_PENDING",
    "DISBURSED",
    "CLOSED",
})


def reference_amount(application) -> Decimal | None:
    """
    Montant de travail / contractuel unique pour frais, garanties, analyse,
    quotité et échéanciers.

    - Dès APPROVED (et suivants) : amount_approved, sinon proposed, sinon requested
    - Avant : amount_proposed, sinon amount_requested
    """
    status = getattr(application, "status", None)
    if status in _APPROVED_LIKE:
        return (
            _dec(getattr(application, "amount_approved", None))
            or _dec(getattr(application, "amount_proposed", None))
            or _dec(getattr(application, "amount_requested", None))
        )
    return (
        _dec(getattr(application, "amount_proposed", None))
        or _dec(getattr(application, "amount_requested", None))
    )


def reference_amount_label(application) -> str:
    """Libellé d'affichage du montant de référence."""
    status = getattr(application, "status", None)
    if status in _APPROVED_LIKE and getattr(application, "amount_approved", None):
        return "accordé"
    if getattr(application, "amount_proposed", None):
        return "proposé"
    return "demandé"
