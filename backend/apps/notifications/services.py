"""
Envoi des alertes e-mail liées aux circuits d'approbation.

- Étape suivante : utilisateurs du rôle de l'étape qui vient d'être ouverte.
  Pour le rôle Chef d'agence : limité à l'agence du dossier (sinon toute la filiale).
- Fin de circuit : initiateur + tous les intervenants ayant agi.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.html import escape

from .mail import send_email_for_tenant
from .models import NotificationLog, TenantNotificationSettings

logger = logging.getLogger("finflow")
User = get_user_model()


def _settings_for(tenant) -> TenantNotificationSettings | None:
    if tenant is None:
        return None
    return TenantNotificationSettings.for_tenant(tenant)


def _frontend_base() -> str:
    return (getattr(settings, "FRONTEND_BASE_URL", None) or "http://localhost").rstrip(
        "/"
    )


def _format_money(amount, currency: str = "XOF") -> str:
    if amount is None:
        return "—"
    try:
        value = f"{float(amount):,.0f}".replace(",", " ")
    except (TypeError, ValueError):
        value = str(amount)
    return f"{value} {currency}".strip()


def _client_nom_prenom(client) -> str:
    """Nom puis prénom (personne physique) ou raison sociale."""
    if client is None:
        return ""
    last = (getattr(client, "last_name", "") or "").strip()
    first = (getattr(client, "first_name", "") or "").strip()
    if last or first:
        return f"{last} {first}".strip()
    return (getattr(client, "display_name", None) or str(client) or "").strip()


_PROCESS_SUBJECT_LABEL = {
    "MAIN_LEVEE": "Dossier de main levée",
    "DATION": "Dossier de dation",
}


def _client_name_from_meta(meta: dict) -> str:
    return (
        meta.get("client_nom_prenom") or meta.get("client_display") or ""
    ).strip()


def _subject_tail(meta: dict, fallback: str = "") -> str:
    """Crédit : « Nom Prénom - montant ». Main levée / dation : libellé + client."""
    fallback = fallback or meta.get("reference") or meta.get("process_label") or "dossier"
    kind = meta.get("kind") or ""
    name = _client_name_from_meta(meta)
    if kind == "CREDIT":
        amount = (meta.get("amount_label") or "").strip()
        if amount in {"", "—"}:
            amount = ""
        if name and amount:
            return f"{name} - {amount}"
        if name:
            return name
        if amount:
            return amount
        return fallback
    label = _PROCESS_SUBJECT_LABEL.get(kind)
    if label:
        return f"{label} - {name}" if name else label
    return fallback


def _alert_subject(prefix: str, meta: dict, fallback: str = "") -> str:
    kind = meta.get("kind") or ""
    if kind in _PROCESS_SUBJECT_LABEL:
        return f"[FIN_FLOW] {_subject_tail(meta, fallback)}"[:255]
    return f"{prefix} — {_subject_tail(meta, fallback)}"[:255]


def _describe_target(instance) -> dict:
    """Résumé métier de la cible du circuit (détails crédit inclus)."""
    target = instance.target
    definition = instance.definition
    process_label = (
        definition.get_target_type_display()
        if definition
        else "Processus"
    )
    reference = getattr(target, "reference", None) or str(getattr(target, "pk", ""))
    detail_path = None
    client_display = ""
    client_nom_prenom = ""
    amount_label = ""
    details: list[tuple[str, str]] = []
    kind = definition.target_type if definition else ""

    if target is None:
        return {
            "kind": kind,
            "process_label": process_label,
            "reference": reference,
            "detail_path": None,
            "client_display": "",
            "client_nom_prenom": "",
            "amount_label": "",
            "details": details,
            "detail_url": _frontend_base(),
        }

    from apps.credits.models import CreditApplication
    from apps.guarantees.models import DationRequest, GuaranteeReleaseRequest

    if isinstance(target, CreditApplication):
        detail_path = f"/dossiers/{target.id}"
        client = target.client
        client_display = getattr(client, "display_name", str(client))
        client_nom_prenom = _client_nom_prenom(client)
        currency = getattr(target, "currency", None) or "XOF"
        product = getattr(target, "product", None)
        agency = getattr(target, "agency", None)
        amount = (
            target.amount_approved
            or target.amount_proposed
            or target.amount_requested
        )
        amount_label = _format_money(amount, currency)
        details = [
            ("Produit", product.label if product else "—"),
            ("Montant", _format_money(amount, currency)),
            ("Montant demandé", _format_money(target.amount_requested, currency)),
            (
                "Durée",
                f"{target.duration_months} mois"
                if target.duration_months
                else "—",
            ),
            ("Agence", agency.name if agency else "—"),
            (
                "Statut dossier",
                target.get_status_display()
                if hasattr(target, "get_status_display")
                else target.status,
            ),
        ]
        if target.purpose:
            purpose = " ".join(str(target.purpose).split())
            if len(purpose) > 160:
                purpose = purpose[:157] + "…"
            details.append(("Objet", purpose))
    elif isinstance(target, GuaranteeReleaseRequest):
        detail_path = f"/mains-levees/{target.id}"
        client = target.guarantee.client if target.guarantee_id else None
        client_display = getattr(client, "display_name", str(client)) if client else ""
        client_nom_prenom = _client_nom_prenom(client)
        if target.guarantee_id:
            details.append(("Garantie", target.guarantee.reference or str(target.guarantee_id)))
    elif isinstance(target, DationRequest):
        detail_path = f"/dations/{target.id}"
        client = target.client
        client_display = getattr(client, "display_name", str(client))
        client_nom_prenom = _client_nom_prenom(client)

    return {
        "kind": kind,
        "process_label": process_label,
        "reference": reference,
        "detail_path": detail_path,
        "client_display": client_display or "",
        "client_nom_prenom": client_nom_prenom or "",
        "amount_label": amount_label,
        "details": details,
        "detail_url": (
            f"{_frontend_base()}{detail_path}" if detail_path else _frontend_base()
        ),
    }


def _group_role_name(group) -> str:
    if group is None:
        return ""
    role = getattr(group, "tenant_role", None)
    if role is not None and getattr(role, "name", None):
        return str(role.name)
    return str(getattr(group, "name", "") or "")


def _group_is_chef_agence(group) -> bool:
    from apps.accounts.capabilities import AGENCY_MANAGER, group_has_capability

    return group_has_capability(group, AGENCY_MANAGER)


def _target_agency_id(instance):
    """Agence métier du dossier / processus (crédits, ML, dation, formalisation)."""
    target = getattr(instance, "target", None)
    if target is None:
        return None
    agency_id = getattr(target, "agency_id", None)
    if agency_id:
        return agency_id
    application = getattr(target, "application", None)
    if application is not None:
        return getattr(application, "agency_id", None)
    guarantee = getattr(target, "guarantee", None)
    if guarantee is not None:
        agency_id = getattr(guarantee, "agency_id", None)
        if agency_id:
            return agency_id
        app = getattr(guarantee, "application", None)
        if app is not None:
            return getattr(app, "agency_id", None)
    return None


def _users_for_group(group, tenant_id, *, agency_id=None):
    """Membres du rôle (+ délégataires). Optionnellement restreints à une agence.

    Si ``agency_id`` est fourni mais qu'aucun membre n'y est rattaché, repli
    sur l'ensemble du rôle filiale (évite un dossier sans alerte).
    """
    from apps.accounts.models import Delegation

    if group is None:
        return User.objects.none()
    qs = User.objects.filter(
        groups=group,
        is_active=True,
    ).exclude(email="")
    if tenant_id:
        qs = qs.filter(Q(tenant_id=tenant_id) | Q(is_group_level=True)).distinct()

    if agency_id:
        scoped = qs.filter(
            Q(agency_id=agency_id) | Q(agencies=agency_id)
        ).distinct()
        if scoped.exists():
            qs = scoped
        else:
            logger.info(
                "Aucun destinataire du rôle « %s » pour l'agence %s — "
                "repli sur tous les membres du rôle.",
                _group_role_name(group) or getattr(group, "name", group),
                agency_id,
            )

    member_ids = list(qs.values_list("id", flat=True))
    today = timezone.now().date()
    delegate_ids = list(
        Delegation.objects.filter(
            delegator_id__in=member_ids,
            is_active=True,
            start_date__lte=today,
            end_date__gte=today,
        ).values_list("delegate_id", flat=True)
    )
    if not delegate_ids:
        return qs

    delegates = User.objects.filter(
        id__in=delegate_ids,
        is_active=True,
    ).exclude(email="")
    if tenant_id:
        delegates = delegates.filter(
            Q(tenant_id=tenant_id) | Q(is_group_level=True)
        )
    return User.objects.filter(
        Q(pk__in=member_ids) | Q(pk__in=delegates.values_list("id", flat=True))
    ).distinct()


def _users_for_step(instance, step):
    """Destinataires d'une alerte d'étape (agence pour Chef d'agence)."""
    group = getattr(step, "required_group", None)
    agency_id = None
    if _group_is_chef_agence(group):
        agency_id = _target_agency_id(instance)
    return _users_for_group(
        group,
        getattr(instance, "tenant_id", None),
        agency_id=agency_id,
    )


def _emails(users) -> list[str]:
    seen = set()
    out = []
    for u in users:
        email = (u.email or "").strip()
        if email and email.lower() not in seen:
            seen.add(email.lower())
            out.append(email)
    return out


def _initiator_users(instance):
    """Soumissionnaire puis créateur du dossier (pas le dernier modificateur)."""
    target = instance.target
    users = []
    if target is None:
        return users
    seen = set()
    for attr in ("submitted_by", "created_by"):
        user = getattr(target, attr, None)
        if user is None:
            continue
        if user.pk in seen:
            continue
        if not (getattr(user, "email", None) or "").strip():
            continue
        if not getattr(user, "is_active", True):
            continue
        seen.add(user.pk)
        users.append(user)
    return users


def _participant_users(instance):
    """Initiateur + utilisateurs ayant déjà agi sur le circuit."""
    from apps.workflow.models import ApprovalTask

    users = list(_initiator_users(instance))
    seen = {u.pk for u in users}
    # all_tenants : hors requête HTTP, le related manager `instance.tasks` est vide.
    for task in ApprovalTask.all_tenants.filter(instance=instance).select_related(
        "acted_by"
    ):
        actor = task.acted_by
        if (
            actor
            and actor.pk not in seen
            and (actor.email or "").strip()
            and actor.is_active
        ):
            seen.add(actor.pk)
            users.append(actor)
    return users


def _is_credit_application(instance) -> bool:
    from apps.credits.models import CreditApplication

    return isinstance(instance.target, CreditApplication)


def _build_bodies(
    *,
    title: str,
    intro: str,
    meta: dict,
    extra: str = "",
    cta_label: str = "Ouvrir le dossier",
) -> tuple[str, str]:
    details = list(meta.get("details") or [])
    lines = [
        title,
        "",
        intro,
        "",
        f"Processus : {meta['process_label']}",
        f"Référence : {meta['reference']}",
    ]
    if meta.get("client_display"):
        lines.append(f"Client : {meta['client_display']}")
    for label, value in details:
        if value and value != "—":
            lines.append(f"{label} : {value}")
    if extra:
        lines.extend(["", extra])
    lines.extend(
        [
            "",
            f"Ouvrir dans Fin Flow : {meta['detail_url']}",
            "",
            "— FIN_FLOW",
        ]
    )
    text = "\n".join(lines)

    html_extra = f"<p>{escape(extra)}</p>" if extra else ""
    client_html = (
        f"<li><strong>Client :</strong> {escape(meta['client_display'])}</li>"
        if meta.get("client_display")
        else ""
    )
    details_html = "".join(
        f"<li><strong>{escape(label)} :</strong> {escape(str(value))}</li>"
        for label, value in details
        if value and value != "—"
    )
    html = f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#17231f;">
      <h2 style="color:#0f9488;">{escape(title)}</h2>
      <p>{escape(intro)}</p>
      <ul>
        <li><strong>Processus :</strong> {escape(meta['process_label'])}</li>
        <li><strong>Référence :</strong> {escape(meta['reference'])}</li>
        {client_html}
        {details_html}
      </ul>
      {html_extra}
      <p><a href="{escape(meta['detail_url'])}"
            style="display:inline-block;padding:10px 16px;background:#0f9488;
                   color:#fff;text-decoration:none;border-radius:8px;">
        {escape(cta_label)}
      </a></p>
      <p style="color:#6b7671;font-size:12px;">— FIN_FLOW</p>
    </div>
    """
    return text, html


def _send_email(
    *,
    tenant,
    prefs: TenantNotificationSettings,
    kind: str,
    subject: str,
    recipients: list[str],
    text_body: str,
    html_body: str,
    workflow_instance_id=None,
    approval_task_id=None,
) -> NotificationLog:
    # all_tenants : création hors requête HTTP (Celery / batchs).
    log = NotificationLog.all_tenants.create(
        tenant=tenant,
        kind=kind,
        status=NotificationLog.Status.PENDING,
        subject=subject,
        recipients=recipients,
        body_preview=text_body[:2000],
        workflow_instance_id=workflow_instance_id,
        approval_task_id=approval_task_id,
    )
    if not recipients:
        log.status = NotificationLog.Status.SKIPPED
        log.error_message = "Aucun destinataire avec adresse e-mail."
        log.save(update_fields=["status", "error_message", "updated_at"])
        return log

    from_email = None  # résolu dans send_email_for_tenant
    cc = []
    if prefs.cc_tenant_email and tenant.email:
        cc.append(tenant.email)
    reply_to = [prefs.reply_to] if prefs.reply_to else None

    try:
        send_email_for_tenant(
            tenant=tenant,
            prefs=prefs,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            recipients=recipients,
            reply_to=reply_to,
            cc=cc or None,
            from_email=from_email,
        )
        log.status = NotificationLog.Status.SENT
        log.save(update_fields=["status", "updated_at"])
    except Exception as exc:  # noqa: BLE001
        logger.exception("Échec d'envoi de notification e-mail")
        log.status = NotificationLog.Status.FAILED
        log.error_message = str(exc)
        log.save(update_fields=["status", "error_message", "updated_at"])
    return log


def notify_step_opened(instance, step, task=None):
    """Alerte les utilisateurs du rôle de l'étape nouvellement ouverte.

    Déclenché à la soumission (1ʳᵉ étape) et à chaque validation qui ouvre
    l'étape suivante du circuit.
    """
    tenant = instance.tenant
    prefs = _settings_for(tenant)
    if not prefs or not prefs.enabled or not prefs.notify_on_step:
        return None

    users = _users_for_step(instance, step)
    recipients = _emails(users)
    meta = _describe_target(instance)
    subject = _alert_subject(
        "[FIN_FLOW] Dossier en attente",
        meta,
        fallback=meta["reference"] or meta["process_label"],
    )
    client_bit = (
        f" concernant {meta['client_display']}"
        if meta.get("client_display")
        else ""
    )
    intro = (
        f"Un dossier{client_bit} attend votre intervention "
        f"à l'étape « {step.name} ». "
        "Connectez-vous à Fin Flow pour le traiter."
    )
    text, html = _build_bodies(
        title="Dossier en attente de votre intervention",
        intro=intro,
        meta=meta,
        extra=f"Étape à traiter : {step.name}",
    )
    return _send_email(
        tenant=tenant,
        prefs=prefs,
        kind=NotificationLog.Kind.STEP,
        subject=subject,
        recipients=recipients,
        text_body=text,
        html_body=html,
        workflow_instance_id=instance.id,
        approval_task_id=getattr(task, "id", None),
    )


def notify_workflow_outcome(instance, outcome: str):
    """
    Informe l'initiateur (et les intervenants) de la fin / issue du circuit.

    outcome: APPROVED | REJECTED | RETURNED

    Pour un dossier crédit :
    - APPROVED : invitation à générer les contrats ;
    - REJECTED / RETURNED : information claire à l'initiateur pour suite à donner.
    """
    tenant = instance.tenant
    prefs = _settings_for(tenant)
    if not prefs or not prefs.enabled:
        return None

    if outcome == "APPROVED" and not prefs.notify_on_completion:
        return None
    if outcome == "REJECTED" and not (
        prefs.notify_on_rejection or prefs.notify_on_completion
    ):
        return None
    if outcome == "RETURNED" and not (
        prefs.notify_on_return or prefs.notify_on_completion
    ):
        return None

    is_credit = _is_credit_application(instance)
    # Initiateur en premier, puis les autres acteurs du circuit.
    recipients = _emails(_initiator_users(instance) + _participant_users(instance))

    meta = _describe_target(instance)
    client_bit = (
        f" concernant {meta['client_display']}"
        if meta.get("client_display")
        else ""
    )
    ref = meta["reference"] or meta["process_label"]
    extra = ""
    cta_label = "Ouvrir le dossier"

    if outcome == "APPROVED" and is_credit:
        title = "Dossier validé — contrats à générer"
        intro = (
            f"Votre dossier{client_bit} a été validé en fin de circuit d'approbation. "
            "Vous pouvez maintenant générer les contrats et les faire signer par le client."
        )
        extra = (
            "Prochaine étape : ouvrez le dossier, section Contrats, "
            "générez les documents puis déposez l'exemplaire signé."
        )
        cta_label = "Générer les contrats"
        subject = _alert_subject(
            "[FIN_FLOW] Dossier validé — générez les contrats",
            meta,
            fallback=ref,
        )
    elif outcome == "REJECTED" and is_credit:
        title = "Dossier rejeté"
        intro = (
            f"Votre dossier{client_bit} a été rejeté au cours du circuit d'approbation. "
            "Consultez le dossier pour prendre connaissance du motif."
        )
        extra = (
            "Aucune suite n'est attendue sur ce dossier tant qu'une nouvelle "
            "demande n'est pas créée, sauf consignes contraires de votre hiérarchie."
        )
        cta_label = "Voir le dossier rejeté"
        subject = _alert_subject("[FIN_FLOW] Dossier rejeté", meta, fallback=ref)
    elif outcome == "RETURNED" and is_credit:
        title = "Dossier renvoyé pour correction"
        intro = (
            f"Votre dossier{client_bit} vous a été renvoyé pour correction. "
            "Modifiez les éléments demandés puis soumettez-le à nouveau."
        )
        extra = (
            "Ouvrez le dossier, consultez les commentaires des validateurs, "
            "apportez les corrections puis resoumettez le circuit."
        )
        cta_label = "Corriger et resoumettre"
        subject = _alert_subject(
            "[FIN_FLOW] Dossier renvoyé pour correction",
            meta,
            fallback=ref,
        )
    else:
        labels = {
            "APPROVED": ("Circuit approuvé", "Le circuit a été approuvé."),
            "REJECTED": ("Circuit rejeté", "Le circuit a été rejeté."),
            "RETURNED": (
                "Dossier renvoyé",
                "Le dossier a été renvoyé pour correction.",
            ),
        }
        title, intro = labels.get(
            outcome, ("Mise à jour du circuit", "Le circuit a été mis à jour.")
        )
        subject = _alert_subject(
            f"[FIN_FLOW] {title}",
            meta,
            fallback=f"{meta['process_label']} {meta['reference']}".strip(),
        )

    kind = {
        "APPROVED": NotificationLog.Kind.COMPLETION,
        "REJECTED": NotificationLog.Kind.REJECTION,
        "RETURNED": NotificationLog.Kind.RETURN,
    }.get(outcome, NotificationLog.Kind.COMPLETION)

    text, html = _build_bodies(
        title=title,
        intro=intro,
        meta=meta,
        extra=extra,
        cta_label=cta_label,
    )
    return _send_email(
        tenant=tenant,
        prefs=prefs,
        kind=kind,
        subject=subject,
        recipients=recipients,
        text_body=text,
        html_body=html,
        workflow_instance_id=instance.id,
    )


def schedule_step_notifications(instance, order):
    """À appeler après ouverture des tâches d'un ordre donné."""
    from apps.workflow.models import ApprovalTask

    tasks = list(
        ApprovalTask.all_tenants.filter(
            instance=instance,
            step__order=order,
            status=ApprovalTask.Status.PENDING,
        ).select_related("step", "step__required_group")
    )
    if not tasks:
        return

    def _send():
        from .tasks import send_step_opened_emails

        send_step_opened_emails.delay(str(instance.id), order)

    transaction.on_commit(_send)


def schedule_outcome_notification(instance, outcome: str):
    instance_id = str(instance.id)

    def _send():
        from .tasks import send_workflow_outcome_email

        send_workflow_outcome_email.delay(instance_id, outcome)

    transaction.on_commit(_send)


def notify_sla_breach(task):
    """Alerte le rôle de l'étape qu'une tâche a dépassé son SLA."""
    instance = task.instance
    step = task.step
    tenant = instance.tenant
    prefs = _settings_for(tenant)
    if not prefs or not prefs.enabled:
        return None

    users = _users_for_step(instance, step)
    recipients = _emails(users)
    meta = _describe_target(instance)
    due = task.due_at.isoformat() if task.due_at else "—"
    subject = _alert_subject(
        "[FIN_FLOW][SLA] Échéance dépassée",
        meta,
        fallback=f"{meta['process_label']} {meta['reference']}".strip(),
    )
    intro = (
        f"L'étape « {step.name} » a dépassé son délai (SLA). "
        f"Échéance : {due}."
    )
    text, html = _build_bodies(
        title="SLA dépassé",
        intro=intro,
        meta=meta,
        extra=f"Étape : {step.name}",
    )
    return _send_email(
        tenant=tenant,
        prefs=prefs,
        kind=NotificationLog.Kind.STEP,
        subject=subject,
        recipients=recipients,
        text_body=text,
        html_body=html,
        workflow_instance_id=instance.id,
        approval_task_id=task.id,
    )


def _collection_case_meta(case) -> dict:
    from apps.collections.services import _loan_application

    app = _loan_application(case)
    client = getattr(app, "client", None) if app else None
    client_display = ""
    if client is not None:
        client_display = getattr(client, "display_name", None) or str(client)
    reference = (getattr(app, "reference", None) if app else None) or str(case.id)
    currency = getattr(getattr(case, "tenant", None), "currency", None) or "XOF"
    details = [
        ("Retard", f"{case.days_overdue} j"),
        ("Impayé", _format_money(case.overdue_amount, currency)),
    ]
    tranche = getattr(case, "tranche", None)
    if tranche is not None:
        details.append(("Tranche", tranche.name))
    return {
        "kind": "COLLECTION",
        "process_label": "Recouvrement",
        "reference": reference,
        "client_display": client_display,
        "client_nom_prenom": _client_nom_prenom(client) if client else "",
        "detail_path": f"/recouvrement/{case.id}",
        "detail_url": f"{_frontend_base()}/recouvrement/{case.id}",
        "details": details,
        "amount_label": "",
    }


def _collection_recipient_users(case, *, extra_users=(), exclude_ids=None):
    from apps.collections.access import users_for_tranche_owner

    exclude_ids = {pk for pk in (exclude_ids or set()) if pk}
    seen = set()
    users = []
    for user in extra_users:
        if user is None or not getattr(user, "id", None):
            continue
        if user.id in exclude_ids or user.id in seen:
            continue
        if not (getattr(user, "email", None) or "").strip():
            continue
        if not getattr(user, "is_active", True):
            continue
        seen.add(user.id)
        users.append(user)
    assigned = getattr(case, "assigned_to", None)
    if assigned is not None and assigned.id not in seen and assigned.id not in exclude_ids:
        if (assigned.email or "").strip() and assigned.is_active:
            seen.add(assigned.id)
            users.append(assigned)
    for user in users_for_tranche_owner(
        case.tenant_id, getattr(case.tranche, "owner_kind", None), case=case
    ):
        if user.id in seen or user.id in exclude_ids:
            continue
        seen.add(user.id)
        users.append(user)
    return users


def notify_collection_tranche_transfer(case, *, from_tranche=None, to_tranche=None):
    """Alerte les responsables de la tranche d'arrivée."""
    from apps.collections.models import CollectionCase

    case = (
        CollectionCase.objects.select_related(
            "tenant",
            "tranche",
            "assigned_to",
            "loan__application__client",
            "loan__application__submitted_by",
            "loan__application__created_by",
        )
        .get(pk=case.pk)
    )
    tenant = getattr(case, "tenant", None)
    prefs = _settings_for(tenant)
    if not prefs or not prefs.enabled or not prefs.notify_collection_transfer:
        return None
    to_tranche = to_tranche or case.tranche
    extra = []
    assigned = getattr(case, "assigned_to", None)
    if assigned is not None:
        extra.append(assigned)
    users = _collection_recipient_users(case, extra_users=extra)
    recipients = _emails(users)
    meta = _collection_case_meta(case)
    from_label = getattr(from_tranche, "name", None) or "—"
    to_label = getattr(to_tranche, "name", None) or "—"
    subject = (
        f"[FIN_FLOW] Dossier transmis — {to_label} — "
        f"{_subject_tail(meta, meta['reference'])}"
    )[:255]
    intro = (
        f"Un dossier de recouvrement a été transmis de « {from_label} » "
        f"vers « {to_label} ». Connectez-vous à Fin Flow pour le prendre en charge."
    )
    text, html = _build_bodies(
        title="Dossier transmis à votre tranche",
        intro=intro,
        meta=meta,
        extra=f"Transfert : {from_label} → {to_label}",
        cta_label="Ouvrir le dossier de recouvrement",
    )
    return _send_email(
        tenant=tenant,
        prefs=prefs,
        kind=NotificationLog.Kind.COLLECTION_TRANSFER,
        subject=subject,
        recipients=recipients,
        text_body=text,
        html_body=html,
    )


def notify_collection_dialogue(message):
    """Alerte l'équipe de la tranche (et l'agent affecté) d'un nouveau message."""
    case = getattr(message, "case", None)
    if case is None:
        return None
    from apps.collections.models import CollectionCase

    case = (
        CollectionCase.objects.select_related(
            "tenant",
            "tranche",
            "assigned_to",
            "loan__application__client",
            "loan__application__submitted_by",
            "loan__application__created_by",
        )
        .get(pk=case.pk)
    )
    tenant = getattr(case, "tenant", None)
    prefs = _settings_for(tenant)
    if not prefs or not prefs.enabled or not prefs.notify_collection_dialogue:
        return None
    author = getattr(message, "created_by", None)
    extra = []
    assigned = getattr(case, "assigned_to", None)
    if assigned is not None:
        extra.append(assigned)
    app = getattr(getattr(case, "loan", None), "application", None)
    if app is not None:
        extra.append(getattr(app, "submitted_by", None))
        extra.append(getattr(app, "created_by", None))
    if assigned is None:
        users = _collection_recipient_users(
            case,
            extra_users=extra,
            exclude_ids={getattr(author, "id", None)},
        )
    else:
        users = []
        exclude_id = getattr(author, "id", None)
        for user in extra:
            if user is None or user.id == exclude_id:
                continue
            if not getattr(user, "is_active", True):
                continue
            if not (getattr(user, "email", None) or "").strip():
                continue
            if user.id in {u.id for u in users}:
                continue
            users.append(user)
    recipients = _emails(users)
    meta = _collection_case_meta(case)
    kind_label = message.get_kind_display()
    author_name = ""
    if author is not None:
        author_name = author.get_full_name() or author.username
    subject = (
        f"[FIN_FLOW] {kind_label} — {_subject_tail(meta, meta['reference'])}"
    )[:255]
    intro = (
        f"{author_name or 'Un collègue'} a déposé une {kind_label.lower()} "
        "sur un dossier de recouvrement."
    )
    preview = (message.body or "").strip()
    if len(preview) > 400:
        preview = preview[:397] + "…"
    text, html = _build_bodies(
        title=kind_label,
        intro=intro,
        meta=meta,
        extra=preview,
        cta_label="Ouvrir le dossier de recouvrement",
    )
    return _send_email(
        tenant=tenant,
        prefs=prefs,
        kind=NotificationLog.Kind.COLLECTION_DIALOGUE,
        subject=subject,
        recipients=recipients,
        text_body=text,
        html_body=html,
    )
