"""Calcul et agrégation des frais d'un dossier de crédit."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .amounts import reference_amount


def _dec(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def fees_base_amount(application) -> Decimal | None:
    """Base de calcul des % : montant de référence du dossier."""
    return reference_amount(application)


def build_fees_breakdown(application) -> dict:
    from .pricing import quote_pricing

    return quote_pricing(application)["fees"]


def build_legacy_fees_breakdown(application, manual_fees=None) -> dict:
    """
    Liste des frais (dossier + additionnels) avec montants calculés et total.

    Les frais sont exprimés pour information / contractualisation. Ils sont
    prélevés par le CBS sur le montant mis en place (montant accordé) — Fin Flow
    transmet le montant accordé intégral, sans soustraction locale.
    """
    base = fees_base_amount(application)
    lines = []

    dossier_rate = _dec(getattr(application, "fees_rate", None))
    if dossier_rate is not None:
        amount = (
            _money(base * dossier_rate / Decimal("100")) if base is not None else None
        )
        lines.append(
            {
                "id": None,
                "label": "Frais de dossier",
                "mode": "PERCENT",
                "value": str(dossier_rate),
                "amount": str(amount) if amount is not None else None,
                "is_dossier": True,
            }
        )

    rows = (
        manual_fees
        if manual_fees is not None
        else [
            {"id": fee.id, "label": fee.label, "mode": fee.mode, "value": fee.value}
            for fee in application.extra_fees.all()
        ]
    )
    for fee in rows:
        value = _dec(fee["value"]) or Decimal("0")
        if fee["mode"] == "PERCENT":
            amount = _money(base * value / Decimal("100")) if base is not None else None
        else:
            amount = _money(value)
        lines.append(
            {
                "id": str(fee["id"]) if fee.get("id") else None,
                "label": fee["label"],
                "mode": fee["mode"],
                "value": str(value),
                "amount": str(amount) if amount is not None else None,
                "is_dossier": False,
            }
        )

    total = Decimal("0")
    has_amount = False
    for line in lines:
        if line["amount"] is not None:
            total += Decimal(line["amount"])
            has_amount = True

    net_after_fees = None
    if base is not None and has_amount:
        net_after_fees = _money(base - total)

    return {
        "base_amount": str(base) if base is not None else None,
        "lines": lines,
        "total": str(_money(total)) if has_amount else None,
        "net_after_fees": str(net_after_fees) if net_after_fees is not None else None,
    }


def parse_extra_fees(payload):
    """Valide toutes les lignes avant toute suppression ou écriture."""
    from django.core.exceptions import ValidationError
    from apps.configuration.pricing_catalog import number

    if payload is None:
        return None
    if isinstance(payload, str):
        import json

        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("Liste de frais invalide.") from exc
    if not isinstance(payload, list) or len(payload) > 100:
        raise ValueError("Une liste de 100 frais au maximum est attendue.")
    cleaned = []
    for raw in payload:
        if not isinstance(raw, dict) or set(raw) - {
            "label",
            "mode",
            "value",
            "id",
            "sort_order",
        }:
            raise ValueError("Ligne de frais invalide ou champs inconnus.")
        label, mode = raw.get("label"), raw.get("mode", "AMOUNT")
        if (
            not isinstance(label, str)
            or not label.strip()
            or len(label) > 150
            or not isinstance(mode, str)
            or mode.upper() not in {"AMOUNT", "PERCENT"}
        ):
            raise ValueError("Libellé ou mode de frais invalide.")
        mode = mode.upper()
        try:
            value = number(
                raw.get("value"),
                maximum="100" if mode == "PERCENT" else "999999999999999.999",
                nullable=False,
            )
        except ValidationError as exc:
            raise ValueError(" ".join(exc.messages)) from exc
        cleaned.append({"label": label.strip(), "mode": mode, "value": value})
    return cleaned


def sync_extra_fees(application, payload) -> None:
    """Remplace les frais additionnels à partir d'une liste JSON valide."""
    from django.db import transaction
    from .models import CreditApplicationFee

    rows = parse_extra_fees(payload)
    if rows is None:
        return
    with transaction.atomic():
        application.extra_fees.all().delete()
        for idx, row in enumerate(rows):
            CreditApplicationFee.objects.create(
                tenant_id=application.tenant_id,
                application=application,
                **row,
                sort_order=idx,
            )
    getattr(application, "_prefetched_objects_cache", {}).pop("extra_fees", None)
