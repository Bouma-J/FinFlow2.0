"""Pont dation ↔ recouvrement : gel financier et historique à la clôture."""
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.guarantees.models import DationRequest

from .models import CollectionAction, CollectionActionType, CollectionCase

_OPEN_DATION_STATUSES = (
    DationRequest.Status.DRAFT,
    DationRequest.Status.IN_APPROVAL,
    DationRequest.Status.RETURNED,
    DationRequest.Status.APPROVED,
    DationRequest.Status.BLOCKED,
)

_DENY_FINANCIAL = (
    "Opération financière suspendue : une dation est en cours ou vient "
    "de couvrir intégralement la créance. Attendez la clôture CBS, "
    "le rejet ou le solde résiduel."
)


def _application_id(case: CollectionCase):
    return getattr(getattr(case, "loan", None), "application_id", None)


def _dations_for_application(application):
    if application is None:
        return []
    cache = getattr(application, "_prefetched_objects_cache", None)
    if cache is not None and "dation_requests" in cache:
        return list(application.dation_requests.all())
    app_id = getattr(application, "id", None)
    if not app_id:
        return []
    return list(
        DationRequest.objects.filter(application_id=app_id).order_by(
            "-created_at"
        )
    )


def _dations_for_case(case: CollectionCase):
    app = getattr(getattr(case, "loan", None), "application", None)
    if app is None:
        app_id = _application_id(case)
        if not app_id:
            return []
        return list(
            DationRequest.objects.filter(application_id=app_id).order_by(
                "-created_at"
            )
        )
    return _dations_for_application(app)


def serialize_dation_brief(dation) -> dict | None:
    if dation is None:
        return None
    residual = getattr(dation, "residual_balance", None)
    return {
        "id": str(dation.id),
        "reference": dation.reference or "",
        "status": dation.status,
        "status_display": dation.get_status_display(),
        "residual_balance": str(residual) if residual is not None else None,
        "covers_claim": dation.covers_claim(),
    }


def open_dation_for_case(case: CollectionCase):
    for dation in _dations_for_case(case):
        if dation.status in _OPEN_DATION_STATUSES:
            return dation
    return None


def covering_completed_dation(case: CollectionCase):
    completed = [
        d
        for d in _dations_for_case(case)
        if d.status == DationRequest.Status.COMPLETED
    ]
    completed.sort(
        key=lambda d: d.completed_at or d.created_at,
        reverse=True,
    )
    for dation in completed:
        if dation.covers_claim():
            return dation
    return None


def financial_ops_block(case: CollectionCase) -> tuple[bool, str, object]:
    """(gelé, motif, dation bloquante)."""
    if case.stage == CollectionCase.Stage.CLOSED:
        return False, "", None
    open_dation = open_dation_for_case(case)
    if open_dation is not None:
        ref = open_dation.reference or "en cours"
        return (
            True,
            (
                f"Dation {ref} ({open_dation.get_status_display()}) : "
                "restructuration et passage en perte suspendus "
                "jusqu'à clôture, rejet ou annulation."
            ),
            open_dation,
        )
    covering = covering_completed_dation(case)
    if covering is not None:
        ref = covering.reference or "clôturée"
        return (
            True,
            (
                f"Dation {ref} clôturée avec couverture intégrale. "
                "Attendez le solde CBS (recalcul des impayés)."
            ),
            covering,
        )
    return False, "", None


def financial_ops_block_for_loan(loan) -> tuple[bool, str, object]:
    """Gel dation même hors dossier de recouvrement (fiche prêt)."""
    case = getattr(loan, "collection_case", None)
    if case is not None:
        return financial_ops_block(case)
    app = getattr(loan, "application", None)
    open_dation = None
    covering = None
    for dation in _dations_for_application(app):
        if open_dation is None and dation.status in _OPEN_DATION_STATUSES:
            open_dation = dation
        if (
            covering is None
            and dation.status == DationRequest.Status.COMPLETED
            and dation.covers_claim()
        ):
            covering = dation
    if open_dation is not None:
        ref = open_dation.reference or "en cours"
        return (
            True,
            (
                f"Dation {ref} ({open_dation.get_status_display()}) : "
                "restructuration et passage en perte suspendus "
                "jusqu'à clôture, rejet ou annulation."
            ),
            open_dation,
        )
    if covering is not None:
        ref = covering.reference or "clôturée"
        return (
            True,
            (
                f"Dation {ref} clôturée avec couverture intégrale. "
                "Attendez le solde CBS (recalcul des impayés)."
            ),
            covering,
        )
    return False, "", None


def require_financial_ops(user, case: CollectionCase) -> None:
    from .access import require_case_operate

    require_case_operate(user, case)
    blocked, reason, _ = financial_ops_block(case)
    if blocked:
        raise PermissionDenied(reason or _DENY_FINANCIAL)


def require_loan_financial_ops(loan, *, user=None, operate_case: bool = False) -> None:
    """Gel dation. `operate_case` impose aussi le droit d'opérer le recouvrement."""
    case = getattr(loan, "collection_case", None)
    if operate_case and case is not None:
        require_financial_ops(user, case)
        return
    blocked, reason, _ = financial_ops_block_for_loan(loan)
    if blocked:
        raise PermissionDenied(reason or _DENY_FINANCIAL)


def sync_collection_on_dation_complete(request: DationRequest) -> None:
    """Historique + prochaine action. Ne clôture pas le dossier (CBS décide)."""
    if not request.application_id:
        return
    case = (
        CollectionCase.objects.filter(loan__application_id=request.application_id)
        .exclude(stage=CollectionCase.Stage.CLOSED)
        .select_related("loan")
        .order_by("-created_at")
        .first()
    )
    if case is None:
        return

    covers = bool(request.covers_claim())
    residual = request.residual_balance
    ref = request.reference or str(request.id)
    author = request.updated_by or request.created_by
    if covers:
        result = "Couverture intégrale"
        comment = (
            f"Dation {ref} clôturée — la créance CBS est couverte. "
            "Contrôler le solde CBS ; ne pas encaisser avant confirmation."
        )
        note = (
            f"Dation {ref} clôturée (couverture intégrale). "
            "Contrôler le solde CBS."
        )
    else:
        residual_txt = residual if residual is not None else "—"
        result = "Solde résiduel"
        comment = (
            f"Dation {ref} clôturée — résiduel {residual_txt}. "
            "Reprendre le recouvrement du solde."
        )
        note = (
            f"Dation {ref} clôturée — résiduel {residual_txt}. "
            "Reprendre le recouvrement."
        )

    CollectionAction.objects.create(
        tenant_id=case.tenant_id,
        case=case,
        action_type=CollectionActionType.DATION,
        action_date=timezone.localdate(),
        result=result,
        comment=comment,
        created_by=author,
        updated_by=author,
    )
    from .services import set_next_action

    set_next_action(
        case,
        action_date=timezone.localdate(),
        action_type=CollectionActionType.DATION,
        note=note[:255],
    )
