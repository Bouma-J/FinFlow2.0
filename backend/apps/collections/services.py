"""Services de recouvrement : PAR, synchro impayés CBS, escalade, tableau de bord."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

logger = logging.getLogger("finflow")

CBS_REPAYMENT_DENIED = (
    "Les encaissements sont enregistrés dans le CBS. "
    "Actualisez le dossier : le retard diminue ou le crédit passe soldé."
)

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.credits.models import Installment, Loan

from .models import (
    CollectionAction,
    CollectionActionType,
    CollectionCase,
    CollectionEscalationRule,
    CollectionStageHistory,
    CollectionTranche,
    LitigationFile,
    LoanRestructure,
    PaymentPromise,
    Repayment,
    WriteOff,
)

STAGE_RANK = {
    CollectionCase.Stage.AMICABLE: 0,
    CollectionCase.Stage.PRECONTENTIOUS: 1,
    CollectionCase.Stage.LITIGATION: 2,
    CollectionCase.Stage.CLOSED: -1,
}

DEFAULT_ESCALATION_RULES = (
    (31, CollectionCase.Stage.PRECONTENTIOUS, "Précontentieux dès 31 j"),
    (91, CollectionCase.Stage.LITIGATION, "Contentieux dès 91 j"),
)

DEFAULT_TRANCHES = (
    (1, "Gestionnaire", 1, 30, CollectionTranche.OwnerKind.GESTIONNAIRE),
    (2, "Service recouvrement", 31, 90, CollectionTranche.OwnerKind.COLLECTION),
    (3, "Juridique", 91, None, CollectionTranche.OwnerKind.LEGAL),
)

OWNER_KIND_STAGE = {
    CollectionTranche.OwnerKind.GESTIONNAIRE: CollectionCase.Stage.AMICABLE,
    CollectionTranche.OwnerKind.COLLECTION: CollectionCase.Stage.PRECONTENTIOUS,
    CollectionTranche.OwnerKind.LEGAL: CollectionCase.Stage.LITIGATION,
}


def classify_par(days_overdue):
    """Classe un prêt dans une catégorie de portefeuille à risque (PAR)."""
    if days_overdue <= 0:
        return CollectionCase.ParClass.HEALTHY
    if days_overdue <= 30:
        return CollectionCase.ParClass.PAR1
    if days_overdue <= 90:
        return CollectionCase.ParClass.PAR30
    if days_overdue <= 180:
        return CollectionCase.ParClass.PAR90
    return CollectionCase.ParClass.PAR180


def _loan_fully_settled(loan: Loan) -> bool:
    return not loan.installments.exclude(status=Installment.Status.PAID).exists()


def ensure_default_escalation_rules(tenant) -> int:
    """Crée les règles d'escalade par défaut si absentes."""
    created = 0
    # all_tenants : hors ContextVar tenant (ex. sync_role_packs).
    for days, stage, label in DEFAULT_ESCALATION_RULES:
        _, was_created = CollectionEscalationRule.all_tenants.get_or_create(
            tenant=tenant,
            min_days_overdue=days,
            defaults={
                "target_stage": stage,
                "label": label,
                "is_active": True,
            },
        )
        if was_created:
            created += 1
    return created


@transaction.atomic
def change_case_stage(
    case: CollectionCase,
    to_stage: str,
    *,
    user=None,
    reason: str = "",
    automatic: bool = False,
) -> CollectionCase:
    """Change le stade et enregistre l'historique."""
    from_stage = case.stage or ""
    if from_stage == to_stage:
        return case
    case.stage = to_stage
    case.stage_changed_at = timezone.now()
    case.save(update_fields=["stage", "stage_changed_at"])
    CollectionStageHistory.objects.create(
        tenant_id=case.tenant_id,
        case=case,
        from_stage=from_stage,
        to_stage=to_stage,
        reason=reason or ("Escalade automatique" if automatic else ""),
        automatic=automatic,
        changed_by=user if user and getattr(user, "is_authenticated", False) else None,
    )
    if (
        automatic
        and to_stage == CollectionCase.Stage.LITIGATION
        and (
            not case.next_action_date
            or case.next_action_type != CollectionActionType.LEGAL
        )
    ):
        set_next_action(
            case,
            action_date=timezone.localdate(),
            action_type=CollectionActionType.LEGAL,
            note="Escalade contentieux — ouvrir / suivre le dossier",
        )
    return case


def suggested_stage_for_days(tenant_id, days_overdue: int) -> str | None:
    """Retourne le stade cible le plus élevé applicable selon les règles actives."""
    ensure_default_escalation_rules_by_id(tenant_id)
    rules = (
        CollectionEscalationRule.objects.filter(
            tenant_id=tenant_id,
            is_active=True,
            min_days_overdue__lte=days_overdue,
        )
        .order_by("-min_days_overdue")
    )
    best = None
    best_rank = -1
    for rule in rules:
        rank = STAGE_RANK.get(rule.target_stage, -1)
        if rank > best_rank:
            best_rank = rank
            best = rule.target_stage
    return best


def ensure_default_escalation_rules_by_id(tenant_id) -> None:
    from apps.tenants.models import Tenant

    tenant = Tenant.objects.filter(pk=tenant_id).first()
    if tenant:
        ensure_default_escalation_rules(tenant)


def apply_escalation_rules(case: CollectionCase) -> CollectionCase:
    """Tranche (affectation) puis stade selon les règles d'escalade."""
    case = apply_tranche_transfer(case)
    if case.stage == CollectionCase.Stage.CLOSED:
        return case
    suggested = suggested_stage_for_days(case.tenant_id, case.days_overdue)
    if not suggested:
        return case
    if STAGE_RANK.get(suggested, -1) <= STAGE_RANK.get(case.stage, -1):
        return case
    return change_case_stage(
        case,
        suggested,
        automatic=True,
        reason=f"Escalade automatique — {case.days_overdue} j de retard",
    )


def ensure_default_tranches(tenant) -> int:
    """Crée les 3 tranches par défaut si la filiale n'en a aucune."""
    existing = CollectionTranche.all_tenants.filter(tenant=tenant).exists()
    if existing:
        return 0
    created = 0
    for position, name, min_days, max_days, owner in DEFAULT_TRANCHES:
        CollectionTranche.all_tenants.create(
            tenant=tenant,
            position=position,
            name=name,
            min_days_overdue=min_days,
            max_days_overdue=max_days,
            owner_kind=owner,
            is_active=True,
        )
        created += 1
    return created


def ensure_default_tranches_by_id(tenant_id) -> None:
    from apps.tenants.models import Tenant

    tenant = Tenant.objects.filter(pk=tenant_id).first()
    if tenant:
        ensure_default_tranches(tenant)


def resolve_tranche(tenant_id, days_overdue: int):
    """Tranche active correspondant au nombre de jours de retard."""
    if days_overdue <= 0:
        return None
    ensure_default_tranches_by_id(tenant_id)
    candidates = CollectionTranche.objects.filter(
        tenant_id=tenant_id,
        is_active=True,
        min_days_overdue__lte=days_overdue,
    ).order_by("-min_days_overdue")
    for tranche in candidates:
        if (
            tranche.max_days_overdue is not None
            and days_overdue > tranche.max_days_overdue
        ):
            continue
        return tranche
    return None


def _credit_officer(case: CollectionCase):
    app = getattr(case.loan, "application", None)
    if app is None:
        return None
    return getattr(app, "submitted_by", None) or getattr(app, "created_by", None)


def _assign_for_tranche(case: CollectionCase, tranche: CollectionTranche) -> list[str]:
    """Met à jour l'affectation selon le responsable de la tranche."""
    if tranche.owner_kind == CollectionTranche.OwnerKind.GESTIONNAIRE:
        officer = _credit_officer(case)
        if officer is not None and case.assigned_to_id != officer.pk:
            case.assigned_to = officer
            return ["assigned_to"]
        return []
    if case.assigned_to_id is not None:
        case.assigned_to = None
        return ["assigned_to"]
    return []


def apply_tranche_transfer(case: CollectionCase) -> CollectionCase:
    """
    Passe le dossier à la tranche correspondant au retard.

    Transfert uniquement vers le haut. À l'arrivée dans le service
    recouvrement ou le juridique, le dossier rejoint la file (non affecté).
    """
    if case.stage == CollectionCase.Stage.CLOSED:
        return case
    target = resolve_tranche(case.tenant_id, case.days_overdue)
    if target is None:
        return case
    current = case.tranche
    if current is not None and current.position >= target.position:
        return case
    target_stage = OWNER_KIND_STAGE.get(target.owner_kind)
    current_rank = STAGE_RANK.get(case.stage, -1)
    target_rank = STAGE_RANK.get(target_stage, -1)
    if current is None and current_rank > target_rank:
        return case

    update_fields = ["tranche"]
    case.tranche = target
    update_fields.extend(_assign_for_tranche(case, target))
    case.save(update_fields=update_fields)

    reason = (
        f"Transfert automatique — {target.name} "
        f"({case.days_overdue} j de retard)"
    )
    if target_stage and case.stage != target_stage:
        case = change_case_stage(
            case,
            target_stage,
            automatic=True,
            reason=reason,
        )
    else:
        CollectionStageHistory.objects.create(
            tenant_id=case.tenant_id,
            case=case,
            from_stage=case.stage or "",
            to_stage=case.stage or CollectionCase.Stage.AMICABLE,
            reason=reason,
            automatic=True,
        )
    try:
        from apps.notifications.services import notify_collection_tranche_transfer

        notify_collection_tranche_transfer(
            case, from_tranche=current, to_tranche=target
        )
    except Exception:  # noqa: BLE001 — l'alerte ne doit pas bloquer le transfert
        logger.exception("Alerte transfert de tranche en échec")
    return case


def validate_tranche_specs(items: list[dict]) -> list[dict]:
    """Valide et normalise une liste de tranches (nombre et jours libres)."""
    from rest_framework.exceptions import ValidationError

    if not items:
        raise ValidationError(
            {"detail": "Définissez au moins une tranche de recouvrement."}
        )
    cleaned = []
    for raw in items:
        name = str(raw.get("name") or "").strip()
        if not name:
            raise ValidationError({"detail": "Chaque tranche doit avoir un libellé."})
        try:
            min_days = int(raw.get("min_days_overdue"))
        except (TypeError, ValueError):
            raise ValidationError(
                {"detail": "Le retard minimum doit être un nombre entier."}
            )
        if min_days < 1:
            raise ValidationError(
                {"detail": "Le retard minimum d'une tranche est d'au moins 1 jour."}
            )
        max_raw = raw.get("max_days_overdue")
        max_days = None if max_raw in (None, "", 0, "0") else int(max_raw)
        if max_days is not None and max_days < min_days:
            raise ValidationError(
                {
                    "detail": (
                        f"« {name} » : le plafond ({max_days} j) est inférieur "
                        f"au minimum ({min_days} j)."
                    )
                }
            )
        owner = str(raw.get("owner_kind") or CollectionTranche.OwnerKind.GESTIONNAIRE)
        if owner not in CollectionTranche.OwnerKind.values:
            raise ValidationError(
                {"detail": f"Responsable inconnu pour « {name} »."}
            )
        cleaned.append(
            {
                "name": name,
                "min_days_overdue": min_days,
                "max_days_overdue": max_days,
                "owner_kind": owner,
                "is_active": bool(raw.get("is_active", True)),
            }
        )
    cleaned.sort(key=lambda row: row["min_days_overdue"])
    for index, row in enumerate(cleaned):
        row["position"] = index + 1
        if index < len(cleaned) - 1:
            if row["max_days_overdue"] is None:
                raise ValidationError(
                    {
                        "detail": (
                            "Seule la dernière tranche peut être sans plafond "
                            "de jours."
                        )
                    }
                )
            nxt = cleaned[index + 1]["min_days_overdue"]
            if row["max_days_overdue"] + 1 != nxt:
                raise ValidationError(
                    {
                        "detail": (
                            "Les tranches doivent se succéder sans trou ni "
                            f"chevauchement ({row['max_days_overdue']} j puis "
                            f"{nxt} j)."
                        )
                    }
                )
    return cleaned


def replace_collection_tranches(*, tenant, items: list[dict]) -> list:
    """Remplace le paramétrage des tranches de la filiale."""
    specs = validate_tranche_specs(items)
    CollectionTranche.objects.filter(tenant=tenant).delete()
    created = [
        CollectionTranche.objects.create(tenant=tenant, **spec) for spec in specs
    ]
    open_cases = CollectionCase.objects.filter(tenant=tenant).exclude(
        stage=CollectionCase.Stage.CLOSED
    )
    for case in open_cases:
        target = resolve_tranche(case.tenant_id, case.days_overdue)
        if target is not None and case.tranche_id != target.id:
            case.tranche = target
            case.save(update_fields=["tranche"])
    return created


def loan_cbs_reference(loan: Loan) -> str:
    return (
        (getattr(loan, "core_banking_reference", None) or "").strip()
        or (getattr(loan, "cbs_demande_ref", None) or "").strip()
        or (getattr(loan, "cbs_contract_number", None) or "").strip()
        or (getattr(loan, "cbs_external_id", None) or "").strip()
    )


def fetch_cbs_overdue_for_loan(loan: Loan, as_of=None) -> dict:
    """Interroge le CBS (crd/situation) et calcule jours / montant de retard."""
    from apps.corebanking.services import CoreBankingError, get_loan_status

    ref = loan_cbs_reference(loan)
    if not ref:
        raise CoreBankingError(
            "Référence prêt CBS manquante : le retard ne peut pas être "
            "calculé depuis FinFlow."
        )
    app = getattr(loan, "application", None)
    client = getattr(app, "client", None) if app is not None else None
    status = get_loan_status(
        loan.tenant_id,
        ref,
        code_adherent=getattr(client, "cbs_client_id", None) or None,
        num_manuel=getattr(client, "cbs_account_number", None) or None,
        num_piece_identite=getattr(client, "national_id", None) or None,
    )
    days = int(status.get("days_overdue") or 0)
    amount = Decimal(str(status.get("overdue_amount") or 0))
    return {
        "settled": bool(status.get("settled")) and days <= 0 and amount <= 0,
        "days_overdue": days,
        "overdue_amount": amount,
        "outstanding": status.get("outstanding"),
        "oldest_due": status.get("oldest_due"),
    }


def _normalize_cbs_overdue_payload(cbs_status: dict) -> tuple[bool, int, Decimal]:
    days = int(cbs_status.get("days_overdue") or 0)
    amount = Decimal(str(cbs_status.get("overdue_amount") or 0))
    settled = bool(cbs_status.get("settled")) or (days <= 0 and amount <= 0)
    return settled, max(days, 0), max(amount, Decimal("0"))


@transaction.atomic
def refresh_loan_overdue(loan: Loan, as_of=None, *, cbs_status=None):
    """
    Recalcule le retard d'un prêt **depuis le CBS** puis actualise le
    dossier de recouvrement (tranches, PAR). L'échéancier FinFlow n'est
    pas utilisé pour les jours / le montant d'impayé.
    """
    as_of = as_of or date.today()
    error = ""
    if cbs_status is None:
        try:
            cbs_status = fetch_cbs_overdue_for_loan(loan, as_of=as_of)
        except Exception as exc:  # noqa: BLE001 — CoreBankingError ou connecteur
            from apps.corebanking.services import CoreBankingError

            if not isinstance(exc, CoreBankingError):
                raise
            error = str(exc)
            case = CollectionCase.objects.filter(loan=loan).first()
            if case:
                case.cbs_sync_error = error[:255]
                case.cbs_synced_at = timezone.now()
                case.save(update_fields=["cbs_sync_error", "cbs_synced_at"])
            return case

    settled, days_overdue, overdue_amount = _normalize_cbs_overdue_payload(
        cbs_status
    )
    existing = CollectionCase.objects.filter(loan=loan).first()
    previous_amount = (
        Decimal(existing.overdue_amount) if existing is not None else None
    )

    if settled or (days_overdue <= 0 and overdue_amount <= 0):
        case = existing
        if case:
            case.days_overdue = 0
            case.overdue_amount = 0
            case.par_class = CollectionCase.ParClass.HEALTHY
            case.cbs_synced_at = timezone.now()
            case.cbs_sync_error = ""
            case.save(
                update_fields=[
                    "days_overdue",
                    "overdue_amount",
                    "par_class",
                    "cbs_synced_at",
                    "cbs_sync_error",
                ]
            )
            _mark_promises_kept_from_cbs(
                case,
                previous_amount=previous_amount,
                new_amount=Decimal("0"),
                settled=True,
            )
            if case.stage != CollectionCase.Stage.CLOSED:
                change_case_stage(
                    case,
                    CollectionCase.Stage.CLOSED,
                    automatic=True,
                    reason="Soldé au CBS",
                )
        if settled and loan.status == Loan.Status.ACTIVE:
            loan.status = Loan.Status.CLOSED
            loan.save(update_fields=["status"])
        return CollectionCase.objects.filter(loan=loan).first()

    case, created = CollectionCase.objects.get_or_create(
        loan=loan, defaults={"tenant_id": loan.tenant_id}
    )
    case.days_overdue = max(days_overdue, 0)
    case.overdue_amount = max(overdue_amount, 0)
    case.par_class = classify_par(case.days_overdue)
    case.cbs_synced_at = timezone.now()
    case.cbs_sync_error = ""
    case.save(
        update_fields=[
            "days_overdue",
            "overdue_amount",
            "par_class",
            "cbs_synced_at",
            "cbs_sync_error",
        ]
    )
    if previous_amount is not None:
        _mark_promises_kept_from_cbs(
            case,
            previous_amount=previous_amount,
            new_amount=case.overdue_amount,
            settled=False,
        )

    if created:
        case.stage_changed_at = timezone.now()
        update_fields = ["stage_changed_at"]
        app = getattr(loan, "application", None)
        agent = None
        if app is not None:
            agent = getattr(app, "submitted_by", None) or getattr(
                app, "created_by", None
            )
        if agent is not None and case.assigned_to_id is None:
            case.assigned_to = agent
            update_fields.append("assigned_to")
        case.save(update_fields=update_fields)
        LoanRestructure.objects.filter(loan=loan, case__isnull=True).update(
            case=case
        )
        CollectionStageHistory.objects.create(
            tenant_id=case.tenant_id,
            case=case,
            from_stage="",
            to_stage=CollectionCase.Stage.AMICABLE,
            reason="Nouveau retard",
            automatic=True,
        )
        if not case.next_action_date:
            set_next_action(
                case,
                action_date=as_of,
                action_type=CollectionActionType.CALL,
                note="Premier contact",
            )
    elif case.stage == CollectionCase.Stage.CLOSED:
        change_case_stage(
            case,
            CollectionCase.Stage.AMICABLE,
            automatic=True,
            reason="Réouverture",
        )
        case.refresh_from_db()
        if not case.next_action_date:
            set_next_action(
                case,
                action_date=as_of,
                action_type=CollectionActionType.CALL,
                note="Réouverture — reprise de contact",
            )

    return apply_escalation_rules(case)


@transaction.atomic
def apply_repayment_to_schedule(repayment: Repayment, *, as_of=None, cbs_status=None):
    """Alloue un encaissement sur les échéances (FIFO) puis relit le retard CBS."""
    as_of = as_of or repayment.payment_date or date.today()
    remaining = Decimal(repayment.amount)
    if remaining <= 0:
        return refresh_loan_overdue(
            repayment.loan, as_of=as_of, cbs_status=cbs_status
        )

    installments = (
        repayment.loan.installments.exclude(status=Installment.Status.PAID)
        .order_by("due_date", "number")
        .select_for_update()
    )

    for inst in installments:
        if remaining <= 0:
            break
        balance = Decimal(inst.total_due) - Decimal(inst.amount_paid)
        if balance <= 0:
            inst.status = Installment.Status.PAID
            inst.amount_paid = inst.total_due
            inst.save(update_fields=["status", "amount_paid"])
            continue
        pay = min(remaining, balance)
        inst.amount_paid = Decimal(inst.amount_paid) + pay
        remaining -= pay
        if inst.amount_paid >= inst.total_due:
            inst.amount_paid = inst.total_due
            inst.status = Installment.Status.PAID
        else:
            inst.status = Installment.Status.PARTIAL
        inst.save(update_fields=["status", "amount_paid"])

    _mark_kept_promises(repayment)
    return refresh_loan_overdue(
        repayment.loan, as_of=as_of, cbs_status=cbs_status
    )


def _mark_kept_promises(repayment: Repayment):
    case = getattr(repayment.loan, "collection_case", None)
    if case is None:
        return
    _mark_promises_kept_from_cbs(
        case,
        previous_amount=Decimal(repayment.amount),
        new_amount=Decimal("0"),
        settled=False,
    )


def _mark_promises_kept_from_cbs(
    case: CollectionCase,
    *,
    previous_amount,
    new_amount,
    settled: bool,
):
    """Une baisse d'impayé CBS (ou un solde) honore les promesses en attente."""
    pending = case.promises.filter(
        status=PaymentPromise.Status.PENDING
    ).order_by("promised_date")
    if settled:
        for promise in pending:
            promise.status = PaymentPromise.Status.KEPT
            promise.save(update_fields=["status"])
        return
    if previous_amount is None:
        return
    leftover = Decimal(previous_amount) - Decimal(new_amount)
    if leftover <= 0:
        return
    for promise in pending:
        if leftover <= 0:
            break
        if Decimal(promise.amount) <= leftover:
            promise.status = PaymentPromise.Status.KEPT
            promise.save(update_fields=["status"])
            leftover -= Decimal(promise.amount)


@transaction.atomic
def refresh_broken_promises(as_of=None) -> int:
    """Passe en BROKEN les promesses PENDING dont la date est dépassée.

    Planifie une reprise de contact si aucune prochaine action future n'existe.
    """
    as_of = as_of or timezone.localdate()
    # all_tenants : appelé depuis Celery hors ContextVar tenant.
    qs = (
        PaymentPromise.all_tenants.filter(
            status=PaymentPromise.Status.PENDING,
            promised_date__lt=as_of,
        )
        .select_related("case")
        .order_by("promised_date")
    )
    count = 0
    for promise in qs:
        promise.status = PaymentPromise.Status.BROKEN
        promise.save(update_fields=["status"])
        count += 1
        case = promise.case
        if case is None:
            continue
        if case.next_action_date and case.next_action_date >= as_of:
            continue
        set_next_action(
            case,
            action_date=as_of,
            action_type=CollectionActionType.CALL,
            note="Promesse non tenue",
        )
    return count


def record_repayment(
    *,
    loan: Loan,
    amount,
    payment_date=None,
    reference="",
    tenant_id=None,
    cbs_status=None,
    user=None,
) -> tuple[Repayment, CollectionCase | None]:
    """Legacy tests only — les encaissements opérationnels passent par le CBS."""
    amount = Decimal(str(amount))
    if amount <= 0:
        raise ValueError("Le montant de l'encaissement doit être positif.")
    payment_date = payment_date or date.today()
    extra = {}
    if user is not None:
        extra["created_by"] = user
        extra["updated_by"] = user
    repayment = Repayment.objects.create(
        tenant_id=tenant_id or loan.tenant_id,
        loan=loan,
        amount=amount,
        payment_date=payment_date,
        reference=reference or "",
        **extra,
    )
    case = apply_repayment_to_schedule(
        repayment, as_of=payment_date, cbs_status=cbs_status
    )
    return repayment, case


def set_next_action(
    case: CollectionCase,
    *,
    action_date=None,
    action_type: str = "",
    note: str = "",
) -> CollectionCase:
    case.next_action_date = action_date
    case.next_action_type = action_type or ""
    case.next_action_note = note or ""
    case.save(
        update_fields=["next_action_date", "next_action_type", "next_action_note"]
    )
    return case


def agent_dashboard(*, user, tenant_id=None, scope: str = "mine") -> dict:
    """Indicateurs portefeuille agent (`mine`) ou filiale / équipe (`team`)."""
    from .access import mine_collection_cases, scoped_collection_cases

    today = timezone.localdate()
    month_start = today.replace(day=1)
    qs = CollectionCase.objects.exclude(stage=CollectionCase.Stage.CLOSED)
    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)
    if user:
        qs = scoped_collection_cases(qs, user)

    scope = (scope or "mine").lower()
    if scope not in {"mine", "team"}:
        scope = "mine"

    if scope == "team":
        portfolio_qs = qs
    elif user:
        portfolio_qs = mine_collection_cases(qs, user)
    else:
        portfolio_qs = qs.none()

    followups = portfolio_qs.filter(
        next_action_date__isnull=False,
        next_action_date__lte=today,
    ).count()
    pending_promises = PaymentPromise.objects.filter(
        case__in=portfolio_qs,
        status=PaymentPromise.Status.PENDING,
    ).count()
    broken_promises = PaymentPromise.objects.filter(
        case__in=portfolio_qs,
        status=PaymentPromise.Status.BROKEN,
        promised_date__gte=today - timedelta(days=30),
    ).count()

    closed_qs = CollectionCase.objects.filter(stage=CollectionCase.Stage.CLOSED)
    if tenant_id:
        closed_qs = closed_qs.filter(tenant_id=tenant_id)
    if user:
        closed_qs = scoped_collection_cases(closed_qs, user)
    if scope == "mine" and user:
        closed_qs = mine_collection_cases(closed_qs, user)
    elif scope != "team":
        closed_qs = closed_qs.none()
    settled_this_month = closed_qs.filter(
        stage_changed_at__date__gte=month_start
    ).count()

    by_par = {
        row["par_class"]: row["n"]
        for row in portfolio_qs.values("par_class").annotate(n=Count("id"))
    }
    by_stage = {
        row["stage"]: row["n"]
        for row in portfolio_qs.values("stage").annotate(n=Count("id"))
    }

    due_cases = list(
        portfolio_qs.filter(next_action_date__isnull=False)
        .order_by("next_action_date")
        .select_related(
            "loan__application__client",
            "loan__application",
            "assigned_to",
        )[:10]
    )
    due_followups = []
    for c in due_cases:
        app = _loan_application(c)
        client = getattr(app, "client", None) if app else None
        due_followups.append({
            "id": str(c.id),
            "application_reference": (app.reference or "") if app else "",
            "client_name": client.display_name if client else "—",
            "next_action_date": c.next_action_date.isoformat() if c.next_action_date else None,
            "next_action_type": c.next_action_type,
            "next_action_note": c.next_action_note,
            "days_overdue": c.days_overdue,
            "overdue_amount": str(c.overdue_amount),
            "par_class": c.par_class,
            "stage": c.stage,
            "assigned_to_name": (
                (c.assigned_to.get_full_name() or c.assigned_to.username)
                if c.assigned_to_id
                else None
            ),
        })

    unassigned_open = (
        portfolio_qs.filter(assigned_to__isnull=True).count()
        if scope == "team"
        else 0
    )

    return {
        "scope": scope,
        "assigned_open": portfolio_qs.count(),
        "unassigned_open": unassigned_open,
        "followups_due": followups,
        "pending_promises": pending_promises,
        "broken_promises_30d": broken_promises,
        "repayments_this_month_count": 0,
        "repayments_this_month_amount": "0",
        "settled_this_month": settled_this_month,
        "by_par_class": by_par,
        "by_stage": by_stage,
        "due_followups": due_followups,
        "as_of": today.isoformat(),
    }


def outstanding_principal(loan: Loan) -> Decimal:
    """Capital restant dû approximé (intérêt / épargne d'abord sur les paiements partiels)."""
    total = Decimal("0")
    for inst in loan.installments.exclude(status=Installment.Status.PAID):
        interest_and_savings = Decimal(inst.interest_due) + Decimal(inst.savings_due)
        principal_paid = max(
            Decimal("0"), Decimal(inst.amount_paid) - interest_and_savings
        )
        principal_left = max(
            Decimal("0"), Decimal(inst.principal_due) - principal_paid
        )
        total += principal_left
    return total


CBS_RESTRUCTURE_NOTE = (
    "Perfect ne dispose pas d'API de restructuration. La décision est "
    "interne à FinFlow : l'échéancier CBS reste inchangé tant qu'il n'est "
    "pas saisi manuellement dans le core banking."
)


def _json_schedule_preview(schedule, outstanding, new_rate, new_duration):
    rows = []
    for row in schedule:
        due = row["due_date"]
        rows.append({
            "number": row["number"],
            "due_date": due.isoformat() if hasattr(due, "isoformat") else str(due),
            "principal": str(row["principal"]),
            "interest": str(row["interest"]),
            "savings": str(row.get("savings") or 0),
            "total": str(row["total"]),
            "balance": str(row.get("balance") or 0),
        })
    total = sum((Decimal(r["total"]) for r in rows), Decimal("0"))
    return {
        "outstanding_principal": str(outstanding),
        "new_duration_months": int(new_duration),
        "new_rate": str(new_rate),
        "rows": rows,
        "count": len(rows),
        "first_due_date": rows[0]["due_date"] if rows else None,
        "last_due_date": rows[-1]["due_date"] if rows else None,
        "total_repayment": str(total),
        "cbs_note": CBS_RESTRUCTURE_NOTE,
    }


def build_restructure_preview(
    loan: Loan,
    *,
    new_duration_months: int,
    new_rate=None,
    first_due_date=None,
    effective_date=None,
) -> dict:
    """Calcule l'échéancier proposé sans enregistrer ni muter le prêt."""
    from apps.credits.models import RepaymentMechanism
    from apps.credits.services import compute_amortization_schedule

    if loan.status != Loan.Status.ACTIVE:
        raise ValueError("Seuls les prêts actifs peuvent être restructurés.")
    new_duration_months = int(new_duration_months)
    if new_duration_months < 1:
        raise ValueError("La durée doit être d'au moins 1 mois.")

    outstanding = outstanding_principal(loan)
    if outstanding <= 0:
        raise ValueError("Aucun capital restant dû à restructurer.")

    effective_date = effective_date or timezone.localdate()
    first_due_date = first_due_date or (effective_date + timedelta(days=30))
    previous_rate = Decimal(loan.interest_rate)
    new_rate = Decimal(str(new_rate if new_rate is not None else previous_rate))

    app = loan.application
    mechanism = getattr(app, "repayment_mechanism", None) or RepaymentMechanism.DEGRESSIVE
    periodicity = getattr(app, "periodicity", None) or "MONTHLY"

    schedule = compute_amortization_schedule(
        principal=outstanding,
        annual_rate=new_rate,
        duration_months=new_duration_months,
        periodicity=periodicity,
        start_date=effective_date,
        first_due_date=first_due_date,
        savings_rate=loan.mandatory_savings_rate or 0,
        mechanism=mechanism,
    )
    if not schedule:
        raise ValueError("Impossible de générer le nouvel échéancier.")

    preview = _json_schedule_preview(
        schedule, outstanding, new_rate, new_duration_months
    )
    preview["previous_duration_months"] = loan.duration_months
    preview["previous_rate"] = str(previous_rate)
    preview["effective_date"] = effective_date.isoformat()
    preview["first_due_date"] = first_due_date.isoformat()
    return preview


def _assert_no_pending_financial(loan: Loan) -> None:
    if LoanRestructure.objects.filter(
        loan=loan, status=LoanRestructure.Status.PENDING
    ).exists():
        raise ValueError("Une demande de restructuration est déjà en attente.")
    if WriteOff.objects.filter(loan=loan, status=WriteOff.Status.PENDING).exists():
        raise ValueError("Une demande de passage en perte est déjà en attente.")


def _require_other_decider(record, user) -> None:
    from rest_framework.exceptions import PermissionDenied

    initiator_id = getattr(record, "requested_by_id", None)
    if initiator_id and user and getattr(user, "pk", None) == initiator_id:
        raise PermissionDenied(
            "Vous ne pouvez pas statuer sur votre propre demande."
        )


def _log_restructure_action(case, *, result: str, comment: str, action_date) -> None:
    if case is None:
        return
    CollectionAction.objects.create(
        tenant_id=case.tenant_id,
        case=case,
        action_type=CollectionActionType.LETTER,
        action_date=action_date,
        result=result,
        comment=comment,
    )


@transaction.atomic
def propose_restructure(
    loan: Loan,
    *,
    new_duration_months: int,
    new_rate=None,
    first_due_date=None,
    effective_date=None,
    reason: str = "",
    origin: str = LoanRestructure.Origin.COLLECTION,
    request_kind: str = LoanRestructure.RequestKind.INTERNAL,
    case=None,
    user=None,
) -> LoanRestructure:
    """Enregistre une demande d'analyse. N'altère pas l'échéancier FinFlow."""
    loan = (
        Loan.objects.select_for_update()
        .select_related("application", "collection_case")
        .get(pk=loan.pk)
    )
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("Le motif de la demande est obligatoire.")

    if case is None:
        live = getattr(loan, "collection_case", None)
        if live is not None and live.stage != CollectionCase.Stage.CLOSED:
            case = live
    elif case.stage == CollectionCase.Stage.CLOSED:
        raise ValueError("Le dossier de recouvrement est clôturé.")

    _assert_no_pending_financial(loan)
    preview = build_restructure_preview(
        loan,
        new_duration_months=new_duration_months,
        new_rate=new_rate,
        first_due_date=first_due_date,
        effective_date=effective_date,
    )
    effective = date.fromisoformat(preview["effective_date"])
    first_due = date.fromisoformat(preview["first_due_date"])

    record = LoanRestructure.objects.create(
        tenant_id=loan.tenant_id,
        case=case,
        loan=loan,
        origin=origin or LoanRestructure.Origin.COLLECTION,
        request_kind=request_kind or LoanRestructure.RequestKind.INTERNAL,
        effective_date=effective,
        first_due_date=first_due,
        previous_duration_months=loan.duration_months,
        new_duration_months=int(new_duration_months),
        previous_rate=Decimal(loan.interest_rate),
        new_rate=Decimal(preview["new_rate"]),
        outstanding_principal=Decimal(preview["outstanding_principal"]),
        proposed_schedule=preview,
        reason=reason,
        status=LoanRestructure.Status.PENDING,
        requested_by=user if user and getattr(user, "is_authenticated", False) else None,
    )
    kind_label = (
        "demande client"
        if record.request_kind == LoanRestructure.RequestKind.CLIENT
        else "initiative interne"
    )
    _log_restructure_action(
        case,
        result="Demande de restructuration",
        comment=(
            f"{kind_label} — capital {record.outstanding_principal} — "
            f"durée {record.new_duration_months} mois — taux {record.new_rate}% "
            f"— {reason}. {CBS_RESTRUCTURE_NOTE}"
        ),
        action_date=effective,
    )
    return record


@transaction.atomic
def approve_restructure(record: LoanRestructure, *, user=None, comment: str = "") -> LoanRestructure:
    """Valide l'analyse. N'injecte rien au CBS et ne rebuild pas l'échéancier."""
    record = (
        LoanRestructure.objects.select_for_update()
        .select_related("loan", "case")
        .get(pk=record.pk)
    )
    if record.status != LoanRestructure.Status.PENDING:
        raise ValueError("Cette demande n'est plus en attente.")
    _require_other_decider(record, user)
    record.status = LoanRestructure.Status.APPROVED
    record.applied_by = user if user and getattr(user, "is_authenticated", False) else None
    record.decided_at = timezone.now()
    record.decision_comment = (comment or "").strip()
    record.save(
        update_fields=["status", "applied_by", "decided_at", "decision_comment"]
    )
    _log_restructure_action(
        record.case,
        result="Restructuration approuvée",
        comment=(
            f"Décision interne — à saisir dans Perfect. {CBS_RESTRUCTURE_NOTE}"
            + (f" — {record.decision_comment}" if record.decision_comment else "")
        ),
        action_date=timezone.localdate(),
    )
    return record


@transaction.atomic
def reject_restructure(record: LoanRestructure, *, user=None, comment: str = "") -> LoanRestructure:
    record = LoanRestructure.objects.select_for_update().select_related("case").get(
        pk=record.pk
    )
    if record.status != LoanRestructure.Status.PENDING:
        raise ValueError("Cette demande n'est plus en attente.")
    _require_other_decider(record, user)
    comment = (comment or "").strip()
    if not comment:
        raise ValueError("Le motif du rejet est obligatoire.")
    record.status = LoanRestructure.Status.REJECTED
    record.applied_by = user if user and getattr(user, "is_authenticated", False) else None
    record.decided_at = timezone.now()
    record.decision_comment = comment
    record.save(
        update_fields=["status", "applied_by", "decided_at", "decision_comment"]
    )
    _log_restructure_action(
        record.case,
        result="Restructuration rejetée",
        comment=comment,
        action_date=timezone.localdate(),
    )
    return record


@transaction.atomic
def cancel_restructure(record: LoanRestructure, *, user=None) -> LoanRestructure:
    record = LoanRestructure.objects.select_for_update().select_related("case").get(
        pk=record.pk
    )
    if record.status != LoanRestructure.Status.PENDING:
        raise ValueError("Cette demande n'est plus en attente.")
    initiator_id = record.requested_by_id
    if (
        user
        and not getattr(user, "is_superuser", False)
        and initiator_id
        and user.pk != initiator_id
        and not user.has_perm("collections.change_loanrestructure")
    ):
        from rest_framework.exceptions import PermissionDenied

        raise PermissionDenied("Seul l'initiateur peut annuler cette demande.")
    record.status = LoanRestructure.Status.CANCELLED
    record.applied_by = user if user and getattr(user, "is_authenticated", False) else None
    record.decided_at = timezone.now()
    record.save(update_fields=["status", "applied_by", "decided_at"])
    _log_restructure_action(
        record.case,
        result="Restructuration annulée",
        comment="Demande retirée",
        action_date=timezone.localdate(),
    )
    return record


def apply_restructure(
    case: CollectionCase,
    *,
    new_duration_months: int,
    new_rate=None,
    first_due_date=None,
    effective_date=None,
    reason: str = "",
    user=None,
) -> LoanRestructure:
    """Compat : enregistre une demande depuis un dossier de recouvrement."""
    return propose_restructure(
        case.loan,
        new_duration_months=new_duration_months,
        new_rate=new_rate,
        first_due_date=first_due_date,
        effective_date=effective_date,
        reason=reason or "Restructuration",
        origin=LoanRestructure.Origin.COLLECTION,
        request_kind=LoanRestructure.RequestKind.INTERNAL,
        case=case,
        user=user,
    )


@transaction.atomic
def propose_write_off(
    case: CollectionCase,
    *,
    amount=None,
    write_off_date=None,
    reason: str = "",
    user=None,
) -> WriteOff:
    loan = (
        Loan.objects.select_for_update()
        .select_related("collection_case")
        .get(pk=case.loan_id)
    )
    if loan.status == Loan.Status.CLOSED:
        raise ValueError("Le prêt est déjà soldé.")
    if loan.status == Loan.Status.DEFAULTED:
        raise ValueError("Le prêt est déjà passé en perte.")
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("Le motif du passage en perte est obligatoire.")
    _assert_no_pending_financial(loan)

    write_off_date = write_off_date or timezone.localdate()
    if amount is None:
        amount = case.overdue_amount or outstanding_principal(loan)
    amount = Decimal(str(amount))
    if amount <= 0:
        amount = outstanding_principal(loan)

    record = WriteOff.objects.create(
        tenant_id=case.tenant_id,
        case=case,
        loan=loan,
        amount=amount,
        write_off_date=write_off_date,
        reason=reason,
        status=WriteOff.Status.PENDING,
        requested_by=user if user and getattr(user, "is_authenticated", False) else None,
    )
    CollectionAction.objects.create(
        tenant_id=case.tenant_id,
        case=case,
        action_type=CollectionActionType.LEGAL,
        action_date=write_off_date,
        result="Demande de passage en perte",
        comment=f"Montant {amount} — {reason}",
    )
    return record


@transaction.atomic
def approve_write_off(record: WriteOff, *, user=None, comment: str = "") -> WriteOff:
    record = (
        WriteOff.objects.select_for_update()
        .select_related("loan", "case")
        .get(pk=record.pk)
    )
    if record.status != WriteOff.Status.PENDING:
        raise ValueError("Cette demande n'est plus en attente.")
    _require_other_decider(record, user)
    record.status = WriteOff.Status.APPLIED
    record.approved_by = user if user and getattr(user, "is_authenticated", False) else None
    record.decided_at = timezone.now()
    record.decision_comment = (comment or "").strip()
    record.save(
        update_fields=["status", "approved_by", "decided_at", "decision_comment"]
    )
    _execute_write_off(record.case, record.loan, record, user=user)
    return record


@transaction.atomic
def reject_write_off(record: WriteOff, *, user=None, comment: str = "") -> WriteOff:
    record = WriteOff.objects.select_for_update().select_related("case").get(pk=record.pk)
    if record.status != WriteOff.Status.PENDING:
        raise ValueError("Cette demande n'est plus en attente.")
    _require_other_decider(record, user)
    comment = (comment or "").strip()
    if not comment:
        raise ValueError("Le motif du rejet est obligatoire.")
    record.status = WriteOff.Status.REJECTED
    record.approved_by = user if user and getattr(user, "is_authenticated", False) else None
    record.decided_at = timezone.now()
    record.decision_comment = comment
    record.save(
        update_fields=["status", "approved_by", "decided_at", "decision_comment"]
    )
    CollectionAction.objects.create(
        tenant_id=record.case.tenant_id,
        case=record.case,
        action_type=CollectionActionType.LEGAL,
        action_date=timezone.localdate(),
        result="Passage en perte rejeté",
        comment=comment,
    )
    return record


@transaction.atomic
def cancel_write_off(record: WriteOff, *, user=None) -> WriteOff:
    record = WriteOff.objects.select_for_update().select_related("case").get(pk=record.pk)
    if record.status != WriteOff.Status.PENDING:
        raise ValueError("Cette demande n'est plus en attente.")
    initiator_id = record.requested_by_id
    if (
        user
        and not getattr(user, "is_superuser", False)
        and initiator_id
        and user.pk != initiator_id
        and not user.has_perm("collections.change_writeoff")
    ):
        from rest_framework.exceptions import PermissionDenied

        raise PermissionDenied("Seul l'initiateur peut annuler cette demande.")
    record.status = WriteOff.Status.CANCELLED
    record.approved_by = user if user and getattr(user, "is_authenticated", False) else None
    record.decided_at = timezone.now()
    record.save(update_fields=["status", "approved_by", "decided_at"])
    return record


def _execute_write_off(case: CollectionCase, loan: Loan, record: WriteOff, *, user=None) -> None:
    if loan.status == Loan.Status.CLOSED:
        raise ValueError("Le prêt est déjà soldé.")
    if loan.status == Loan.Status.DEFAULTED:
        raise ValueError("Le prêt est déjà passé en perte.")

    loan.status = Loan.Status.DEFAULTED
    loan.save(update_fields=["status"])

    case.next_action_date = None
    case.next_action_type = ""
    case.next_action_note = ""
    case.days_overdue = 0
    case.overdue_amount = 0
    case.par_class = CollectionCase.ParClass.HEALTHY
    case.save(
        update_fields=[
            "next_action_date",
            "next_action_type",
            "next_action_note",
            "days_overdue",
            "overdue_amount",
            "par_class",
        ]
    )
    if case.stage != CollectionCase.Stage.CLOSED:
        change_case_stage(
            case,
            CollectionCase.Stage.CLOSED,
            user=user,
            reason=record.reason or "Passage en perte",
            automatic=False,
        )

    CollectionAction.objects.create(
        tenant_id=case.tenant_id,
        case=case,
        action_type=CollectionActionType.LEGAL,
        action_date=record.write_off_date,
        result="Passage en perte",
        comment=f"Montant {record.amount} — {record.reason}".strip(" —"),
    )


@transaction.atomic
def write_off_case(
    case: CollectionCase,
    *,
    amount=None,
    write_off_date=None,
    reason: str = "",
    user=None,
) -> WriteOff:
    """Compat tests : propose puis applique (sans second regard)."""
    record = propose_write_off(
        case,
        amount=amount,
        write_off_date=write_off_date,
        reason=reason or "Passage en perte",
        user=user,
    )
    # Les appels service historiques n'ont pas de second acteur : on exécute.
    record.status = WriteOff.Status.APPLIED
    record.approved_by = user if user and getattr(user, "is_authenticated", False) else None
    record.decided_at = timezone.now()
    record.save(update_fields=["status", "approved_by", "decided_at"])
    _execute_write_off(record.case, record.loan, record, user=user)
    return record


LITIGATION_SCALAR_FIELDS = (
    "title",
    "action_type",
    "court_name",
    "court_registry",
    "case_reference",
    "chamber",
    "lawyer",
    "bailiff",
    "mandate_start",
    "mandate_end",
    "mandate_fee",
    "mandate_notes",
    "claimed_principal",
    "claimed_interest",
    "claimed_penalties",
    "claimed_costs",
    "claimed_total",
    "notice_date",
    "filing_date",
    "service_date",
    "first_hearing_date",
    "hearing_date",
    "hearing_time",
    "hearing_location",
    "judgment_date",
    "judgment_outcome",
    "judgment_amount",
    "judgment_enforceable",
    "judgment_served_at",
    "status",
    "notes",
)

LITIGATION_FK_FIELDS = ("law_firm_id", "lawyer_party_id", "bailiff_party_id")


def _mark_case_litigation(case: CollectionCase) -> None:
    if case.stage not in (
        CollectionCase.Stage.LITIGATION,
        CollectionCase.Stage.CLOSED,
    ):
        change_case_stage(
            case,
            CollectionCase.Stage.LITIGATION,
            automatic=False,
            reason="Ouverture dossier contentieux",
        )


def _apply_litigation_data(lit: LitigationFile, data: dict) -> LitigationFile:
    updated = []
    for name in LITIGATION_SCALAR_FIELDS:
        if name in data:
            setattr(lit, name, data[name])
            updated.append(name)
    for name in ("law_firm", "lawyer_party", "bailiff_party"):
        if name in data:
            setattr(lit, name, data[name])
            updated.append(name)
        key = f"{name}_id"
        if key in data:
            setattr(lit, key, data[key])
            updated.append(key)
    # Total réclamé auto si non fourni
    if "claimed_total" not in data:
        parts = [
            lit.claimed_principal,
            lit.claimed_interest,
            lit.claimed_penalties,
            lit.claimed_costs,
        ]
        if any(p is not None for p in parts):
            total = sum((p or Decimal("0")) for p in parts)
            lit.claimed_total = total
            updated.append("claimed_total")
    if updated:
        lit.save(update_fields=list(dict.fromkeys(updated + ["updated_at"])))
    guarantee_ids = data.get("related_guarantee_ids")
    if guarantee_ids is not None:
        _assert_related_guarantees(lit.case, guarantee_ids)
        lit.related_guarantees.set(guarantee_ids)
    return lit


def _assert_related_guarantees(case, guarantee_ids):
    from apps.guarantees.models import Guarantee

    ids = list(guarantee_ids or [])
    if not ids:
        return
    app = getattr(getattr(case, "loan", None), "application", None)
    client_id = getattr(app, "client_id", None)
    qs = Guarantee.objects.filter(pk__in=ids)
    if client_id:
        qs = qs.filter(client_id=client_id)
    found = {str(pk) for pk in qs.values_list("id", flat=True)}
    wanted = {str(pk) for pk in ids}
    if wanted - found:
        raise ValueError(
            "Une garantie liée n'appartient pas au client du dossier."
        )


@transaction.atomic
def create_litigation(case: CollectionCase, *, data: dict) -> LitigationFile:
    """Crée une nouvelle procédure contentieuse sur le dossier."""
    lit = LitigationFile.objects.create(
        tenant_id=case.tenant_id,
        case=case,
        title=data.get("title") or "",
        status=data.get("status") or LitigationFile.Status.PRE_LITIGATION,
    )
    _apply_litigation_data(lit, data)
    _mark_case_litigation(case)
    return lit


@transaction.atomic
def upsert_litigation(
    case: CollectionCase,
    *,
    data: dict,
    litigation_id=None,
) -> LitigationFile:
    """
    Met à jour une procédure existante (id) ou la plus récente,
    sinon en crée une nouvelle.
    """
    lit = None
    if litigation_id:
        lit = LitigationFile.objects.filter(case=case, pk=litigation_id).first()
        if lit is None:
            raise ValueError("Dossier contentieux introuvable.")
    if lit is None:
        lit = (
            case.litigations.exclude(
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
        return create_litigation(case, data=data)
    _apply_litigation_data(lit, data)
    _mark_case_litigation(case)
    return lit


def ensure_litigation_document_categories(tenant) -> int:
    """Crée les catégories GED contentieux si absentes."""
    from apps.documents.category_seed import ensure_document_categories

    return ensure_document_categories(
        tenant,
        (
            ("LIT_ASSIGNATION", "Assignation / requête"),
            ("LIT_CONCLUSIONS", "Conclusions / mémoire"),
            ("LIT_JUDGMENT", "Jugement / ordonnance"),
            ("LIT_PV_HUISSIER", "PV huissier / saisie"),
            ("LIT_MISE_EN_DEMEURE", "Mise en demeure"),
            ("LIT_PIECE_ADVERSE", "Pièce adverse"),
            ("LIT_FACTURE", "Facture honoraires / frais"),
            ("LIT_OTHER", "Autre pièce contentieux"),
        ),
    )


def litigation_documents(litigation: LitigationFile):
    from django.contrib.contenttypes.models import ContentType

    from apps.documents.models import Document

    ct = ContentType.objects.get_for_model(LitigationFile)
    return Document.objects.filter(content_type=ct, object_id=litigation.id)


def upcoming_hearings(
    *, tenant_id=None, within_days: int = 30, limit: int = 50, user=None
):
    """Agenda des prochaines audiences (périmètre visible de l'utilisateur)."""
    today = timezone.localdate()
    until = today + timedelta(days=within_days)
    qs = (
        LitigationFile.objects.exclude(
            status__in=[
                LitigationFile.Status.CLOSED,
                LitigationFile.Status.ABANDONED,
            ]
        )
        .filter(hearing_date__isnull=False, hearing_date__gte=today, hearing_date__lte=until)
        .select_related(
            "case__loan__application__client",
            "law_firm",
            "lawyer_party",
        )
        .order_by("hearing_date")
    )
    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)
    if user is not None:
        from .access import scoped_collection_cases

        visible = scoped_collection_cases(CollectionCase.objects.all(), user)
        qs = qs.filter(case__in=visible)
    rows = []
    for lit in qs[:limit]:
        app = _loan_application(lit.case)
        client = getattr(app, "client", None) if app else None
        rows.append({
            "id": str(lit.id),
            "case_id": str(lit.case_id),
            "title": lit.title or lit.case_reference or "",
            "case_reference": lit.case_reference,
            "application_reference": (app.reference or "") if app else "",
            "client_name": client.display_name if client else "—",
            "hearing_date": lit.hearing_date.isoformat() if lit.hearing_date else None,
            "hearing_time": lit.hearing_time.isoformat() if lit.hearing_time else None,
            "hearing_location": lit.hearing_location,
            "court_name": lit.court_name,
            "status": lit.status,
            "law_firm_name": lit.law_firm.name if lit.law_firm_id else "",
        })
    return rows


def notify_upcoming_hearings(*, within_days: int = 7) -> dict:
    """
    Alerte e-mail interne (agents assignés) pour audiences à J-within_days.
    Utilise le SMTP filiale ; journalise en NotificationLog.
    """
    from apps.notifications.mail import send_email_for_tenant
    from apps.notifications.models import NotificationLog, TenantNotificationSettings

    today = timezone.localdate()
    target = today + timedelta(days=within_days)
    # all_tenants : tâche Celery hors ContextVar tenant.
    qs = (
        LitigationFile.all_tenants.filter(hearing_date=target)
        .exclude(
            status__in=[
                LitigationFile.Status.CLOSED,
                LitigationFile.Status.ABANDONED,
            ]
        )
        .select_related(
            "tenant",
            "case__assigned_to",
            "case__loan__application",
        )
    )
    sent = skipped = failed = 0
    from apps.common.tenancy import tenant_context

    for lit in qs.iterator():
        with tenant_context(lit.tenant_id):
            prefs = TenantNotificationSettings.for_tenant(lit.tenant)
            agent = lit.case.assigned_to
            email = (getattr(agent, "email", None) or "").strip()
            if not email or not prefs or not prefs.enabled:
                skipped += 1
                continue
            ref = lit.case_reference or lit.title or str(lit.id)
            subject = f"Audience contentieux le {lit.hearing_date} — {ref}"
            text = (
                f"Rappel : audience prévue le {lit.hearing_date}"
                f"{(' à ' + lit.hearing_time.strftime('%H:%M')) if lit.hearing_time else ''}"
                f" — {lit.court_name or 'juridiction n/c'}\n"
                f"Dossier recouvrement : {lit.case_id}\n"
                f"Lieu : {lit.hearing_location or '—'}"
            )
            try:
                send_email_for_tenant(
                    tenant=lit.tenant,
                    subject=subject,
                    text_body=text,
                    recipients=[email],
                    prefs=prefs,
                )
                status = NotificationLog.Status.SENT
                sent += 1
                err = ""
            except Exception as exc:  # noqa: BLE001
                status = NotificationLog.Status.FAILED
                failed += 1
                err = str(exc)
            NotificationLog.objects.create(
                tenant_id=lit.tenant_id,
                kind=NotificationLog.Kind.COLLECTION_REMINDER,
                status=status,
                subject=subject,
                recipients=[email],
                body_preview=text[:500],
                error_message=err,
            )
    return {"sent": sent, "skipped": skipped, "failed": failed, "as_of": target.isoformat()}


def send_sms_stub(*, tenant, phone: str, message: str) -> tuple[str, str]:
    """
    Stub SMS — aucun provider branché (FEATURE_SMS=False par défaut).
    Retourne (status, error_message) avec status SKIPPED.
    """
    from django.conf import settings

    if not getattr(settings, "FEATURE_SMS", False):
        return (
            "SKIPPED",
            "Canal SMS désactivé (FEATURE_SMS=0). Aucun envoi.",
        )
    if not phone:
        return "SKIPPED", "Aucun numéro de téléphone."
    return (
        "SKIPPED",
        "Provider SMS non configuré (stub). Message non envoyé.",
    )


def _loan_application(case):
    loan = getattr(case, "loan", None)
    return getattr(loan, "application", None) if loan else None


def _collection_reminder_body(case: CollectionCase) -> tuple[str, str, str]:
    app = _loan_application(case)
    client = getattr(app, "client", None) if app else None
    name = client.display_name if client else "Client"
    ref = (app.reference or str(app.id)) if app else str(case.id)
    amount = case.overdue_amount
    days = case.days_overdue
    subject = f"Relance de paiement — dossier {ref}"
    text = (
        f"Bonjour {name},\n\n"
        f"Nous vous rappelons qu'un impayé de {amount} est constaté "
        f"sur votre dossier {ref} ({days} jour(s) de retard).\n"
        f"Merci de régulariser votre situation dans les meilleurs délais.\n\n"
        f"Cordialement,\nLe service recouvrement"
    )
    html = (
        f"<p>Bonjour {name},</p>"
        f"<p>Nous vous rappelons qu'un impayé de <strong>{amount}</strong> "
        f"est constaté sur votre dossier <strong>{ref}</strong> "
        f"({days} jour(s) de retard).</p>"
        f"<p>Merci de régulariser votre situation dans les meilleurs délais.</p>"
        f"<p>Cordialement,<br/>Le service recouvrement</p>"
    )
    return subject, text, html


def send_collection_reminder(
    case: CollectionCase,
    *,
    channel: str = "EMAIL",
    force: bool = False,
) -> dict:
    """
    Envoie une relance EMAIL (SMTP filiale) ou SMS (stub).
    Crée une CollectionAction et un NotificationLog.
    """
    from apps.notifications.mail import send_email_for_tenant
    from apps.notifications.models import NotificationLog, TenantNotificationSettings

    channel = (channel or "EMAIL").upper()
    if case.stage == CollectionCase.Stage.CLOSED:
        return {"status": "SKIPPED", "reason": "Dossier clôturé"}

    tenant = case.tenant
    prefs = TenantNotificationSettings.for_tenant(tenant)
    client = getattr(case.loan.application, "client", None)
    subject, text, html = _collection_reminder_body(case)
    today = timezone.localdate()

    if channel == "EMAIL":
        if not force and (not prefs.enabled or not prefs.notify_collection_email):
            return {"status": "SKIPPED", "reason": "Relances e-mail désactivées"}
        email = (getattr(client, "email", None) or "").strip()
        if not email:
            log = NotificationLog.objects.create(
                tenant_id=case.tenant_id,
                kind=NotificationLog.Kind.COLLECTION_REMINDER,
                status=NotificationLog.Status.SKIPPED,
                subject=subject,
                recipients=[],
                body_preview=text[:500],
                error_message="Client sans e-mail",
            )
            return {"status": "SKIPPED", "reason": "Client sans e-mail", "log_id": str(log.id)}
        try:
            send_email_for_tenant(
                tenant=tenant,
                subject=subject,
                text_body=text,
                html_body=html,
                recipients=[email],
                prefs=prefs,
            )
            status = NotificationLog.Status.SENT
            error = ""
        except Exception as exc:  # noqa: BLE001
            status = NotificationLog.Status.FAILED
            error = str(exc)
        log = NotificationLog.objects.create(
            tenant_id=case.tenant_id,
            kind=NotificationLog.Kind.COLLECTION_REMINDER,
            status=status,
            subject=subject,
            recipients=[email],
            body_preview=text[:500],
            error_message=error,
        )
        if status == NotificationLog.Status.SENT:
            CollectionAction.objects.create(
                tenant_id=case.tenant_id,
                case=case,
                action_type=CollectionActionType.EMAIL,
                action_date=today,
                result="Relance automatique",
                comment=subject,
            )
        return {"status": status, "log_id": str(log.id), "channel": "EMAIL"}

    if channel == "SMS":
        from django.conf import settings

        if not getattr(settings, "FEATURE_SMS", False):
            return {
                "status": "SKIPPED",
                "channel": "SMS",
                "reason": "Canal SMS désactivé (FEATURE_SMS=0)",
            }
        if not force and (not prefs.enabled or not prefs.notify_collection_sms):
            return {"status": "SKIPPED", "reason": "Relances SMS désactivées"}
        phone = (getattr(client, "phone", None) or "").strip()
        sms_status, sms_error = send_sms_stub(
            tenant=tenant, phone=phone, message=text[:160]
        )
        log = NotificationLog.objects.create(
            tenant_id=case.tenant_id,
            kind=NotificationLog.Kind.COLLECTION_REMINDER,
            status=sms_status,
            subject=f"SMS — {subject}"[:255],
            recipients=[phone] if phone else [],
            body_preview=text[:160],
            error_message=sms_error,
        )
        CollectionAction.objects.create(
            tenant_id=case.tenant_id,
            case=case,
            action_type=CollectionActionType.SMS,
            action_date=today,
            result="Relance SMS (stub)",
            comment=sms_error,
        )
        return {"status": sms_status, "log_id": str(log.id), "channel": "SMS"}

    return {"status": "SKIPPED", "reason": f"Canal inconnu: {channel}"}


def send_due_collection_reminders(*, as_of=None) -> dict:
    """Relances auto pour les prochaines actions EMAIL/SMS dues."""
    as_of = as_of or timezone.localdate()
    # all_tenants : tâche Celery hors ContextVar tenant.
    qs = (
        CollectionCase.all_tenants.exclude(stage=CollectionCase.Stage.CLOSED)
        .filter(
            next_action_date__isnull=False,
            next_action_date__lte=as_of,
            next_action_type__in=[
                CollectionActionType.EMAIL,
                CollectionActionType.SMS,
            ],
        )
        .select_related(
            "tenant",
            "loan__application__client",
        )
    )
    stats = {"email_sent": 0, "sms_stub": 0, "skipped": 0, "failed": 0}
    from apps.common.tenancy import tenant_context

    for case in qs.iterator():
        with tenant_context(case.tenant_id):
            result = send_collection_reminder(case, channel=case.next_action_type)
            status = result.get("status")
            if status == "SENT":
                stats["email_sent"] += 1
                set_next_action(case, action_date=None, action_type="", note="")
            elif status == "SKIPPED" and case.next_action_type == CollectionActionType.SMS:
                stats["sms_stub"] += 1
                set_next_action(case, action_date=None, action_type="", note="")
            elif status == "FAILED":
                stats["failed"] += 1
            else:
                stats["skipped"] += 1
    return stats
