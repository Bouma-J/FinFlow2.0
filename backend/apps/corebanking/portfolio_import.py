"""Import du portefeuille CBS existant (première connexion / relance)."""
from __future__ import annotations

import csv
import io
import logging
import unicodedata
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.catalog.models import CreditProduct, ProductCategory
from apps.clients.models import Client
from apps.common.tenancy import get_current_tenant_id, tenant_context
from apps.credits.models import CreditApplication, Installment, Loan
from apps.tenants.models import Agency, Tenant

from .models import CoreBankingConnector
from .services import (
    CoreBankingError,
    credit_snapshot_from_cbs_row,
    get_client_situation,
    get_loan_status,
    list_cbs_outstanding_credits,
    resolve_active_connector,
)

logger = logging.getLogger("finflow")

CBS_IMPORT_CATEGORY_CODE = "CBS"
CBS_IMPORT_PRODUCT_CODE = "CBS-IMP"
MAX_DOSSIER_REFS = 5000
_REF_HEADER_TOKENS = {
    "numero",
    "n",
    "no",
    "n°",
    "dossier",
    "reference",
    "ref",
    "refdemande",
    "ref_demande",
    "numdemande",
    "numcontrat",
    "contrat",
    "demande",
    "credit",
    "pret",
    "loan",
    "loan_ref",
}


def is_live_cbs_connector(connector: CoreBankingConnector | None) -> bool:
    if connector is None or not connector.is_active:
        return False
    rules = connector.mapping_rules or {}
    if rules.get("force_simulate"):
        return False
    mode = str((rules.get("disbursement") or {}).get("mode") or "").upper()
    if mode == "LOCAL":
        return False
    return bool((connector.base_url or "").strip())


def _blank(value) -> str:
    text = str(value or "").strip()
    if text.upper() in {"", "N/A", "NA", "EMPTY"}:
        return ""
    return text


def _normalize_header_token(value: str) -> str:
    raw = unicodedata.normalize("NFKD", (value or "").strip().lower())
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    return "".join(ch for ch in raw if ch.isalnum() or ch in {"_", "°"})


def _cell_ref(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    return _blank(value)


def _is_header_cell(value: str) -> bool:
    token = _normalize_header_token(value)
    if not token:
        return False
    if token in _REF_HEADER_TOKENS:
        return True
    return any(
        key in token
        for key in ("dossier", "demande", "contrat", "reference", "numero")
    )


def _dedupe_refs(values) -> list[str]:
    seen = set()
    out = []
    for raw in values:
        ref = _cell_ref(raw)
        if not ref or _is_header_cell(ref):
            continue
        if ref in seen:
            continue
        seen.add(ref)
        out.append(ref)
        if len(out) >= MAX_DOSSIER_REFS:
            break
    return out


def parse_cbs_dossier_refs(file_obj) -> list[str]:
    """
    Lit un Excel / CSV / texte : un numéro de dossier CBS par ligne
    (1re colonne). La première ligne d'en-tête est ignorée.
    """
    name = (getattr(file_obj, "name", "") or "").lower()
    if hasattr(file_obj, "seek"):
        file_obj.seek(0)
    if name.endswith(".xlsx"):
        refs = _parse_xlsx_dossier_refs(file_obj)
    else:
        refs = _parse_text_dossier_refs(file_obj)
    if not refs:
        raise ValueError(
            "Aucun numéro de dossier trouvé dans le fichier. "
            "Mettez un numéro CBS par ligne (1re colonne)."
        )
    return refs


def _parse_xlsx_dossier_refs(file_obj) -> list[str]:
    from openpyxl import load_workbook

    workbook = load_workbook(file_obj, read_only=True, data_only=True)
    try:
        sheet = workbook.active
        values = []
        for row in sheet.iter_rows(min_col=1, max_col=1, values_only=True):
            values.append(row[0] if row else None)
    finally:
        workbook.close()
    return _dedupe_refs(values)


def _parse_text_dossier_refs(file_obj) -> list[str]:
    raw = file_obj.read()
    if isinstance(raw, bytes):
        text = raw.decode("utf-8-sig", errors="replace")
    else:
        text = str(raw or "")
    sample = text.lstrip()
    delimiter = ";" if sample[:200].count(";") > sample[:200].count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    values = []
    for row in reader:
        values.append(row[0] if row else "")
    return _dedupe_refs(values)


def _snapshots_from_loan_refs(loan_refs) -> list[dict]:
    snapshots = []
    for ref in _dedupe_refs(loan_refs or []):
        snapshots.append(
            credit_snapshot_from_cbs_row({"refDemande": ref, "loan_ref": ref})
        )
    return snapshots


def ensure_cbs_import_product(tenant) -> CreditProduct:
    category, _ = ProductCategory.objects.get_or_create(
        tenant=tenant,
        code=CBS_IMPORT_CATEGORY_CODE,
        defaults={"label": "Crédits importés CBS", "is_active": True},
    )
    product, _ = CreditProduct.objects.get_or_create(
        tenant=tenant,
        code=CBS_IMPORT_PRODUCT_CODE,
        defaults={
            "label": "Crédit existant (CBS)",
            "category": category,
            "client_type": CreditProduct.ClientType.ALL,
            "amount_min": Decimal("0"),
            "amount_max": Decimal("999999999"),
            "duration_min_months": 1,
            "duration_max_months": 360,
            "interest_rate": Decimal("0"),
            "is_active": True,
        },
    )
    return product


def _find_loan_by_cbs_refs(*refs) -> Loan | None:
    query = Q()
    seen = set()
    for ref in refs:
        text = _blank(ref)
        if not text or text in seen:
            continue
        seen.add(text)
        query |= (
            Q(core_banking_reference=text)
            | Q(cbs_demande_ref=text)
            | Q(cbs_contract_number=text)
            | Q(cbs_demande_number=text)
            | Q(cbs_external_id=text)
        )
    if not seen:
        return None
    return Loan.objects.filter(query).select_related("application__client").first()


def _find_client(snapshot: dict) -> Client | None:
    code = _blank(snapshot.get("code_adherent"))
    if code:
        match = Client.objects.filter(cbs_client_id=code).first()
        if match:
            return match
    piece = _blank(snapshot.get("num_piece_identite"))
    if piece:
        match = Client.objects.filter(national_id=piece).first()
        if match:
            return match
    manuel = _blank(snapshot.get("num_manuel"))
    if manuel:
        match = Client.objects.filter(cbs_account_number=manuel).first()
        if match:
            return match
    return None


def _resolve_agency(tenant, point_of_service: str = "") -> Agency | None:
    qs = Agency.objects.filter(tenant=tenant)
    if point_of_service:
        match = qs.filter(cbs_point_of_service_id=point_of_service).first()
        if match:
            return match
    return qs.order_by("created_at").first()


def find_or_create_cbs_client(tenant, snapshot: dict, *, user=None) -> Client:
    existing = _find_client(snapshot)
    if existing:
        return existing

    preview = {}
    ids = {
        "code_adherent": _blank(snapshot.get("code_adherent")),
        "num_manuel": _blank(snapshot.get("num_manuel")),
        "num_piece_identite": _blank(snapshot.get("num_piece_identite")),
    }
    if any(ids.values()):
        try:
            preview = get_client_situation(tenant.id, **ids)
        except CoreBankingError:
            preview = {}

    code = _blank(preview.get("code_adherent")) or _blank(snapshot.get("code_adherent"))
    if code:
        existing = Client.objects.filter(cbs_client_id=code).first()
        if existing:
            return existing

    name = _blank(preview.get("full_name")) or _blank(snapshot.get("client_name"))
    last_name = _blank(preview.get("last_name"))
    first_name = _blank(preview.get("first_name"))
    company = _blank(preview.get("company_name"))
    is_corporate = bool(
        company
        or preview.get("identification_nationale")
        or preview.get("num_carte_operateur")
    )
    if not last_name and not first_name and name and not is_corporate:
        parts = name.split(None, 1)
        last_name = parts[0]
        first_name = parts[1] if len(parts) > 1 else ""

    agency = _resolve_agency(tenant, _blank(preview.get("id_point_service")))
    fields = {
        "tenant": tenant,
        "client_type": (
            Client.ClientType.CORPORATE
            if is_corporate
            else Client.ClientType.INDIVIDUAL
        ),
        "agency": agency,
        "phone": _blank(preview.get("phone")),
        "email": _blank(preview.get("email")),
        "city": _blank(preview.get("city")),
        "address": _blank(preview.get("address") or preview.get("head_office")),
        "cbs_client_id": code,
        "cbs_account_number": _blank(preview.get("num_manuel"))
        or _blank(snapshot.get("num_manuel")),
        "kyc_status": Client.KycStatus.PENDING,
        "created_by": user if getattr(user, "is_authenticated", False) else None,
        "updated_by": user if getattr(user, "is_authenticated", False) else None,
    }
    if is_corporate:
        fields["company_name"] = company or name or f"Adhérent CBS {code or ''}".strip()
        fields["ifu"] = _blank(preview.get("identification_nationale"))
        fields["rccm"] = _blank(preview.get("num_carte_operateur"))
    else:
        fields["last_name"] = last_name or name or f"Adhérent CBS {code or ''}".strip()
        fields["first_name"] = first_name
        fields["national_id"] = _blank(preview.get("num_piece_identite")) or _blank(
            snapshot.get("num_piece_identite")
        )
    return Client.objects.create(**fields)


def _sync_local_schedule(loan: Loan, schedule: list, tenant) -> None:
    if loan.installments.exists() or not isinstance(schedule, list):
        return
    number = 0
    for row in schedule:
        if not isinstance(row, dict):
            continue
        from apps.corebanking.services import _is_paid_schedule_status, _parse_schedule_date

        due = _parse_schedule_date(
            row.get("date")
            or row.get("dateEcheance")
            or row.get("dueDate")
            or row.get("date_echeance")
        )
        if due is None:
            continue
        try:
            if row.get("montantTotal") not in (None, ""):
                total = Decimal(str(row["montantTotal"]))
            else:
                total = Decimal(str(row.get("montantCapital") or "0"))
                total += Decimal(str(row.get("montantInteret") or "0"))
            principal = Decimal(str(row.get("montantCapital") or total))
            interest = Decimal(str(row.get("montantInteret") or "0"))
        except Exception:  # noqa: BLE001
            continue
        number += 1
        paid = _is_paid_schedule_status(str(row.get("statut") or row.get("status") or ""))
        Installment.objects.create(
            tenant=tenant,
            loan=loan,
            number=number,
            due_date=due,
            principal_due=principal,
            interest_due=interest,
            total_due=total,
            amount_paid=total if paid else Decimal("0"),
            status=Installment.Status.PAID if paid else Installment.Status.PENDING,
        )


def _upsert_loan_from_cbs(tenant, snapshot: dict, status: dict, *, user=None) -> tuple[Loan, bool]:
    refs = (
        snapshot.get("loan_ref"),
        snapshot.get("ref_demande"),
        snapshot.get("num_contrat"),
        snapshot.get("num_demande"),
        status.get("ref_demande"),
        status.get("num_contrat"),
        status.get("num_demande"),
    )
    existing = _find_loan_by_cbs_refs(*refs)
    if existing:
        return existing, False

    client = find_or_create_cbs_client(tenant, snapshot, user=user)
    product = ensure_cbs_import_product(tenant)
    days = int(status.get("days_overdue") or snapshot.get("days_overdue") or 0)
    principal = snapshot.get("principal") or status.get("outstanding") or Decimal("0")
    if not isinstance(principal, Decimal):
        principal = Decimal(str(principal or "0"))
    if principal <= 0:
        principal = Decimal(str(snapshot.get("overdue_amount") or "1"))
    first_due = status.get("oldest_due") or (date.today() - timedelta(days=max(days, 1)))
    if hasattr(first_due, "isoformat") and not isinstance(first_due, date):
        first_due = date.today() - timedelta(days=max(days, 1))
    disbursed_at = first_due - timedelta(days=30) if first_due else date.today()
    agency = client.agency or _resolve_agency(tenant)

    app = CreditApplication.objects.create(
        tenant=tenant,
        client=client,
        product=product,
        agency=agency,
        amount_requested=principal,
        amount_approved=principal,
        duration_months=12,
        first_due_date=first_due,
        interest_rate=product.interest_rate,
        currency=getattr(tenant, "currency", None) or "XOF",
        purpose="Crédit existant importé depuis le CBS (recouvrement).",
        status=CreditApplication.Status.DISBURSED,
        disbursed_at=timezone.now(),
        created_by=user if getattr(user, "is_authenticated", False) else None,
        updated_by=user if getattr(user, "is_authenticated", False) else None,
    )
    loan_ref = _blank(snapshot.get("loan_ref")) or _blank(status.get("ref_demande"))
    loan = Loan.objects.create(
        tenant=tenant,
        application=app,
        principal=principal,
        interest_rate=product.interest_rate or Decimal("0"),
        duration_months=12,
        disbursed_at=disbursed_at,
        first_due_date=first_due,
        status=Loan.Status.ACTIVE,
        core_banking_reference=(
            _blank(status.get("num_contrat"))
            or _blank(snapshot.get("num_contrat"))
            or loan_ref
        )[:100],
        cbs_external_id=loan_ref[:100],
        cbs_demande_number=_blank(status.get("num_demande") or snapshot.get("num_demande"))[:100],
        cbs_demande_ref=_blank(status.get("ref_demande") or snapshot.get("ref_demande") or loan_ref)[:100],
        cbs_contract_number=_blank(status.get("num_contrat") or snapshot.get("num_contrat"))[:100],
        cbs_disbursement_status="IMPORTED",
        cbs_disbursement_payload=snapshot.get("raw") or {},
    )
    _sync_local_schedule(loan, status.get("schedule") or [], tenant)
    return loan, True


def _mark_connector_import(connector: CoreBankingConnector, stats: dict) -> None:
    rules = dict(connector.mapping_rules or {})
    now = timezone.now().isoformat()
    rules.setdefault("portfolio_import_started_at", now)
    rules["portfolio_import_completed_at"] = now
    rules["portfolio_import_last_stats"] = stats
    connector.mapping_rules = rules
    connector.save(update_fields=["mapping_rules", "updated_at"])


def import_cbs_portfolio(
    tenant_id,
    *,
    connector=None,
    user=None,
    overdue_only=True,
    loan_refs=None,
) -> dict:
    """
    Récupère les crédits CBS, crée les prêts FinFlow manquants, puis ouvre
    les dossiers de recouvrement dans la tranche correspondant au retard CBS.

    Si ``loan_refs`` est fourni (fichier Excel / liste), chaque numéro est
    interrogé via ``crd/situation`` — sans appeler la liste des impayés.
    """
    from apps.collections.services import refresh_loan_overdue

    tenant_id = str(tenant_id)
    explicit_refs = _dedupe_refs(loan_refs or [])
    with tenant_context(tenant_id):
        tenant = Tenant.objects.get(pk=tenant_id)
        try:
            connector = connector or resolve_active_connector(tenant_id)
            if explicit_refs:
                credits = _snapshots_from_loan_refs(explicit_refs)
                overdue_only = False
            else:
                listed = list_cbs_outstanding_credits(
                    tenant_id, overdue_only=overdue_only, connector=connector
                )
                credits = listed.get("credits") or []
        except CoreBankingError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        stats = {
            "discovered": len(credits),
            "source": "file" if explicit_refs else "cbs_list",
            "loans_created": 0,
            "loans_updated": 0,
            "cases_opened": 0,
            "skipped": 0,
            "errors": [],
        }
        for raw in credits:
            snapshot = (
                raw
                if raw.get("loan_ref")
                else credit_snapshot_from_cbs_row(raw.get("raw") or raw)
            )
            ref = snapshot.get("loan_ref")
            if not ref:
                stats["skipped"] += 1
                continue
            try:
                with transaction.atomic():
                    status = get_loan_status(
                        tenant_id,
                        ref,
                        code_adherent=snapshot.get("code_adherent") or None,
                        num_manuel=snapshot.get("num_manuel") or None,
                        num_piece_identite=snapshot.get("num_piece_identite") or None,
                        connector=connector,
                    )
                    if status.get("settled"):
                        stats["skipped"] += 1
                        continue
                    if overdue_only and int(status.get("days_overdue") or 0) <= 0:
                        stats["skipped"] += 1
                        continue
                    loan, created = _upsert_loan_from_cbs(
                        tenant, snapshot, status, user=user
                    )
                    if created:
                        stats["loans_created"] += 1
                    else:
                        stats["loans_updated"] += 1
                    case = refresh_loan_overdue(loan, cbs_status=status)
                    if case is not None and case.stage != case.Stage.CLOSED:
                        stats["cases_opened"] += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception("Import portefeuille CBS ref=%s", ref)
                if len(stats["errors"]) < 25:
                    stats["errors"].append({"ref": ref, "error": str(exc)[:240]})
                stats["skipped"] += 1
        _mark_connector_import(connector, stats)
        return stats


def loan_refs_from_upload(file_obj) -> list[str]:
    """Valide le fichier puis extrait les numéros de dossier CBS."""
    from rest_framework.exceptions import ValidationError

    from apps.common.upload_validation import validate_uploaded_file

    if file_obj is None:
        raise ValidationError("Joignez un fichier Excel (.xlsx) ou texte (.csv / .txt).")
    validate_uploaded_file(
        file_obj,
        check_quota=False,
        allowed_extensions=["xlsx", "csv", "txt"],
        max_mb=5,
    )
    try:
        return parse_cbs_dossier_refs(file_obj)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


def enqueue_initial_portfolio_import(
    connector: CoreBankingConnector, *, force: bool = False
):
    """Déclenche l'import une fois, à la première connexion CBS réelle."""
    if not force and not is_live_cbs_connector(connector):
        return None
    rules = dict(connector.mapping_rules or {})
    if not force and rules.get("portfolio_import_started_at"):
        return None
    rules["portfolio_import_started_at"] = timezone.now().isoformat()
    connector.mapping_rules = rules
    connector.save(update_fields=["mapping_rules", "updated_at"])
    from .tasks import import_cbs_portfolio_task

    tenant_id = str(connector.tenant_id or get_current_tenant_id())
    return import_cbs_portfolio_task.delay(tenant_id, str(connector.id))
