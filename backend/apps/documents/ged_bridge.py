"""Pont pièces métier → index GED (Document GFK) sans supprimer les silos."""
from __future__ import annotations

import logging
import os

from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.db import transaction

logger = logging.getLogger("finflow")


def credit_document_origin_key(credit_doc) -> str:
    return f"credits.CreditDocument:{credit_doc.pk}"


@transaction.atomic
def mirror_credit_document_to_ged(credit_doc, *, user=None) -> None:
    """
    Duplique une ``CreditDocument`` dans l'index GED rattaché au dossier.

    Le silo ``CreditDocument`` reste la source d'upload du formulaire dossier ;
    la GED offre la consultation unifiée. ``origin_key`` lie les deux pour
    purge / anti-doublon.
    """
    if not credit_doc or not credit_doc.file:
        return

    from apps.credits.models import CreditApplication, CreditDocument
    from apps.documents.category_seed import ensure_core_document_categories
    from apps.documents.models import Document, DocumentCategory
    from apps.documents.quotas import bump_ged_usage

    if not isinstance(credit_doc, CreditDocument):
        return

    application = credit_doc.application
    tenant = application.tenant
    ensure_core_document_categories(tenant)

    category = DocumentCategory.all_tenants.filter(
        tenant=tenant, code="CREDIT_PIECE"
    ).first()
    if category is None:
        category = DocumentCategory.all_tenants.filter(
            tenant=tenant, code="CREDIT_OTHER"
        ).first()
    if category is None:
        logger.warning(
            "mirror_credit_document_to_ged: catégorie CREDIT_PIECE absente "
            "tenant=%s",
            tenant.pk,
        )
        return

    origin = credit_document_origin_key(credit_doc)
    existing = Document.all_tenants.filter(
        tenant_id=tenant.pk, origin_key=origin
    ).first()
    if existing:
        return

    ct = ContentType.objects.get_for_model(CreditApplication)
    name = (credit_doc.label or "").strip() or os.path.basename(
        credit_doc.file.name
    )
    # Ancien miroir sans origin_key : évite un second doublon.
    legacy = Document.objects.filter(
        tenant_id=tenant.pk,
        content_type=ct,
        object_id=application.id,
        name=name,
        category=category,
        origin_key="",
    ).first()
    if legacy:
        legacy.origin_key = origin
        legacy.save(update_fields=["origin_key", "updated_at"])
        return

    try:
        credit_doc.file.open("rb")
        raw = credit_doc.file.read()
    except Exception:
        logger.exception(
            "mirror_credit_document_to_ged: lecture fichier impossible id=%s",
            credit_doc.pk,
        )
        return
    finally:
        try:
            credit_doc.file.close()
        except Exception:
            pass

    if not raw:
        return

    filename = os.path.basename(credit_doc.file.name) or "piece.bin"
    doc = Document(
        tenant_id=tenant.pk,
        category=category,
        name=name[:255],
        content_type=ct,
        object_id=application.id,
        uploaded_by=user,
        origin_key=origin,
    )
    doc.file.save(filename, ContentFile(raw), save=False)
    doc.mime_type = getattr(credit_doc.file.file, "content_type", "") or ""
    doc.compute_hash()
    doc.save()
    bump_ged_usage(tenant.pk, doc.size_bytes)


@transaction.atomic
def unmirror_credit_document_from_ged(credit_doc) -> None:
    """Supprime l'entrée GED liée à une ``CreditDocument`` (et le fichier)."""
    if not credit_doc:
        return

    from apps.documents.models import Document
    from apps.documents.quotas import bump_ged_usage

    origin = credit_document_origin_key(credit_doc)
    qs = Document.including_deleted.filter(origin_key=origin)
    for doc in qs:
        size = doc.size_bytes or 0
        file_name = ""
        storage = None
        if doc.file and getattr(doc.file, "name", None):
            file_name = doc.file.name
            storage = doc.file.storage
        tenant_id = doc.tenant_id
        doc.delete()
        if file_name and storage is not None:
            try:
                storage.delete(file_name)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Échec suppression miroir GED key=%s", file_name
                )
        if size:
            try:
                bump_ged_usage(tenant_id, -size)
            except Exception:  # noqa: BLE001
                logger.exception("Échec ajustement quota après unmirror")
