"""Collatéral d'instruction : garanties réelles (avec haircuts) + cautions (pilier séparé)."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from apps.credits.amounts import reference_amount


def _dec(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _haircut_pct(thresholds, key: str, default: Decimal = Decimal("0")) -> Decimal:
    raw = getattr(thresholds, key, None)
    if raw is None:
        return default
    return _dec(raw)


def haircut_key_for_guarantee(guarantee) -> str:
    """Clé de haircut filiale selon le type / sous-type de garantie."""
    from apps.guarantees.models import Guarantee, PledgeCategory

    gtype = guarantee.guarantee_type
    if gtype == Guarantee.GuaranteeType.MORTGAGE:
        return "haircut_mortgage"
    if gtype == Guarantee.GuaranteeType.PLEDGE:
        if guarantee.pledge_category == PledgeCategory.VEHICLE:
            return "haircut_vehicle"
        return "haircut_jewelry"
    if gtype == Guarantee.GuaranteeType.FINANCIAL:
        kind = (guarantee.financial_type or "").upper()
        if kind in {"SECURITY", "TITLE", "BOND", "SHARE", "STOCK"}:
            return "haircut_financial_security"
        return "haircut_financial_deposit"
    return "haircut_other"


def retained_value(guarantee, thresholds) -> Decimal:
    """Valeur retenue après haircut filiale (sur current_value déjà décotée titres)."""
    base = _dec(guarantee.current_value)
    key = haircut_key_for_guarantee(guarantee)
    haircut = _haircut_pct(thresholds, key)
    factor = (Decimal("100") - haircut) / Decimal("100")
    if factor < 0:
        factor = Decimal("0")
    return (base * factor).quantize(Decimal("0.01"))


def build_collateral_summary(application, thresholds=None) -> dict:
    """
    Synthèse pour l'analyse d'octroi.

    - Pilier garanties réelles : valeurs retenues + couverture %
    - Pilier cautions : engagements (séparé, non fusionné dans la couverture)
    """
    from apps.credits.models import AnalysisThreshold
    from apps.guarantees.models import Guarantee
    from apps.sureties.models import SuretyEngagement

    if thresholds is None:
        thresholds = AnalysisThreshold.for_application(application)

    amount = reference_amount(application)
    amount_dec = _dec(amount) if amount else Decimal("0")

    guarantees = list(
        application.guarantees.filter(status=Guarantee.Status.ACTIVE).select_related(
            "surety", "client"
        )
    )
    guarantee_rows = []
    total_retained = Decimal("0")
    total_gross = Decimal("0")
    alerts = []

    for g in guarantees:
        gross = _dec(g.current_value)
        retained = retained_value(g, thresholds)
        total_gross += gross
        total_retained += retained
        if gross <= 0:
            alerts.append(
                f"Garantie {g.reference or g.pk} : valeur nulle "
                f"({g.get_guarantee_type_display()})."
            )
        if not g.belongs_to_applicant and not g.surety_id:
            alerts.append(
                f"Garantie {g.reference or g.pk} : bien hors client sans caution propriétaire."
            )
        guarantee_rows.append(
            {
                "id": str(g.id),
                "reference": g.reference or "",
                "guarantee_type": g.guarantee_type,
                "guarantee_type_display": g.get_guarantee_type_display(),
                "pledge_category": g.pledge_category or "",
                "status": g.status,
                "gross_value": str(gross),
                "retained_value": str(retained),
                "haircut_key": haircut_key_for_guarantee(g),
                "haircut_pct": str(_haircut_pct(thresholds, haircut_key_for_guarantee(g))),
                "belongs_to_applicant": g.belongs_to_applicant,
                "surety_id": str(g.surety_id) if g.surety_id else None,
                "surety_name": (
                    g.surety.display_name if g.surety_id and g.surety else ""
                ),
            }
        )

    coverage = None
    gap = None
    if amount_dec > 0:
        coverage = (total_retained / amount_dec * Decimal("100")).quantize(
            Decimal("0.01")
        )
        gap = (amount_dec - total_retained).quantize(Decimal("0.01"))

    min_cov = _dec(thresholds.min_guarantee_coverage)
    guarantee_ok = coverage is not None and coverage >= min_cov
    if coverage is not None and not guarantee_ok:
        alerts.append(
            f"Couverture garanties réelles ({coverage} %) inférieure au seuil "
            f"filiale ({min_cov} %)."
        )

    engagements = list(
        SuretyEngagement.objects.filter(
            application=application,
            status=SuretyEngagement.Status.ACTIVE,
        ).select_related("surety")
    )
    surety_rows = []
    surety_total = Decimal("0")
    for eng in engagements:
        eng_amt = _dec(eng.amount)
        surety_total += eng_amt
        surety = eng.surety
        ceiling = _dec(getattr(surety, "commitment_ceiling", 0))
        if ceiling <= 0:
            alerts.append(
                f"Caution {surety.display_name if surety else eng.pk} : "
                "plafond d'engagement ouvert (0)."
            )
        income = _dec(getattr(surety, "estimated_income", 0) or 0)
        if income > 0 and eng_amt > income * Decimal("12"):
            alerts.append(
                f"Caution {surety.display_name} : engagement élevé vs revenu estimé."
            )
        surety_rows.append(
            {
                "id": str(eng.id),
                "surety_id": str(eng.surety_id),
                "surety_name": surety.display_name if surety else "",
                "surety_type": getattr(surety, "surety_type", "") if surety else "",
                "amount": str(eng_amt),
                "ceiling": str(ceiling) if surety else "0",
                "available_ceiling": str(
                    getattr(surety, "available_ceiling", "") or ""
                ),
                "signed_date": (
                    eng.signed_date.isoformat() if eng.signed_date else None
                ),
            }
        )

    surety_ratio = None
    if amount_dec > 0:
        surety_ratio = (surety_total / amount_dec * Decimal("100")).quantize(
            Decimal("0.01")
        )
        if surety_total > 0 and surety_total < amount_dec:
            alerts.append(
                f"Cautions : couverture partielle ({surety_ratio} % du crédit)."
            )

    product = getattr(application, "product", None)
    requires_guarantee = bool(getattr(product, "requires_guarantee", False))
    if requires_guarantee and not guarantees and not engagements:
        alerts.append(
            "Le produit exige une garantie ou caution : aucune n'est rattachée."
        )

    return {
        "reference_amount": str(amount_dec) if amount else None,
        "currency": getattr(application, "currency", None)
        or getattr(getattr(application, "product", None), "currency", "XOF"),
        "guarantees": guarantee_rows,
        "guarantees_gross_total": str(total_gross),
        "guarantees_retained_total": str(total_retained),
        "guarantee_coverage_pct": str(coverage) if coverage is not None else None,
        "guarantee_gap": str(gap) if gap is not None else None,
        "min_guarantee_coverage": str(min_cov),
        "guarantee_ok": guarantee_ok if coverage is not None else None,
        "sureties": surety_rows,
        "sureties_total": str(surety_total),
        "surety_coverage_pct": str(surety_ratio) if surety_ratio is not None else None,
        "requires_guarantee": requires_guarantee,
        "alerts": alerts,
        "haircuts": {
            "mortgage": str(_haircut_pct(thresholds, "haircut_mortgage")),
            "vehicle": str(_haircut_pct(thresholds, "haircut_vehicle")),
            "jewelry": str(_haircut_pct(thresholds, "haircut_jewelry")),
            "financial_deposit": str(
                _haircut_pct(thresholds, "haircut_financial_deposit")
            ),
            "financial_security": str(
                _haircut_pct(thresholds, "haircut_financial_security")
            ),
            "other": str(_haircut_pct(thresholds, "haircut_other")),
        },
    }


def guarantee_coverage_retained(analysis, thresholds=None) -> Decimal | None:
    """Couverture % basée sur valeurs retenues (ACTIVE + haircuts)."""
    app = analysis.application
    if app is None:
        return None
    from apps.credits.models import AnalysisThreshold

    summary = build_collateral_summary(
        app, thresholds if thresholds is not None else AnalysisThreshold.for_application(app, individual_profile=analysis.individual_profile)
    )
    raw = summary.get("guarantee_coverage_pct")
    if raw is None:
        return None
    return _dec(raw)
