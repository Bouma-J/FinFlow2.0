"""Création idempotente des catégories GED par processus métier."""


def ensure_document_categories(tenant, codes) -> int:
    """
    Crée les catégories (code, label) absentes pour la filiale.

    Utilise ``all_tenants`` pour rester fiable hors ContextVar
    (ex. sync_role_packs, Celery).
    """
    from apps.documents.models import DocumentCategory

    created = 0
    for entry in codes:
        if len(entry) == 3:
            code, label, tracks_expiry = entry
        else:
            code, label = entry
            tracks_expiry = False
        _, was = DocumentCategory.all_tenants.get_or_create(
            tenant=tenant,
            code=code,
            defaults={
                "label": label,
                "is_active": True,
                "tracks_expiry": bool(tracks_expiry),
            },
        )
        if was:
            created += 1
    return created


# Catalogue cœur KYC / crédit (CDC §3.3) — seed au bootstrap filiale.
CORE_DOCUMENT_CATEGORIES = (
    ("CNI", "Carte nationale d'identité", True),
    ("PASSPORT", "Passeport", True),
    ("CONSULAR_CARD", "Carte consulaire", True),
    ("PHOTO_ID", "Photo d'identité", False),
    ("RCCM", "RCCM / registre de commerce", False),
    ("IFU", "IFU / NINEA", False),
    ("STATUTS", "Statuts de la société", False),
    ("ETATS_FIN", "États financiers", False),
    ("BULLETINS", "Bulletins de salaire", False),
    ("RELEVE_BANCAIRE", "Relevé bancaire", False),
    ("JUSTIFICATIF_DOMICILE", "Justificatif de domicile", False),
    ("CONTRAT_TRAVAIL", "Contrat de travail", False),
    ("VISITE_TERRAIN", "Rapport de visite terrain", False),
    ("EXPERTISE", "Expertise / évaluation", False),
    ("CREDIT_PIECE", "Pièce du dossier de crédit", False),
    ("CREDIT_OTHER", "Autre pièce crédit", False),
    ("CAUTION_PIECE", "Pièce de caution", False),
    ("GARANTIE_PIECE", "Pièce de garantie", False),
)

COMMITTEE_DOCUMENT_CATEGORIES = (
    (
        "PV_COMITE",
        "Procès-verbal de comité de crédit",
        False,
    ),
)


def ensure_core_document_categories(tenant) -> int:
    """Catégories KYC / crédit / collatéral génériques."""
    return ensure_document_categories(tenant, CORE_DOCUMENT_CATEGORIES)


def ensure_committee_document_categories(tenant) -> int:
    """Catégorie GED pour le PV de comité de crédit."""
    return ensure_document_categories(tenant, COMMITTEE_DOCUMENT_CATEGORIES)


def ensure_all_process_document_categories(tenant) -> int:
    """
    Seed complet des catégories GED pour une filiale :
    cœur + comité + main levée + dation + formalisation + contentieux.
    """
    from apps.collections.services import ensure_litigation_document_categories
    from apps.guarantees.formalization_services import (
        ensure_formalization_document_categories,
    )
    from apps.guarantees.process_services import (
        ensure_dation_document_categories,
        ensure_release_document_categories,
    )

    total = 0
    total += ensure_core_document_categories(tenant)
    total += ensure_committee_document_categories(tenant)
    total += ensure_release_document_categories(tenant)
    total += ensure_dation_document_categories(tenant)
    total += ensure_formalization_document_categories(tenant)
    total += ensure_litigation_document_categories(tenant)
    return total
