"""Filtres GED (module métier, client, expiration, dates)."""
from __future__ import annotations

from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.common.list_filters import query_param

RELATED_KINDS = {
    "CREDIT": ("credits", "creditapplication"),
    "LOAN": ("credits", "loan"),
    "CLIENT": ("clients", "client"),
    "GUARANTEE": ("guarantees", "guarantee"),
    "SURETY": ("sureties", "surety"),
    "DATION": ("guarantees", "dationrequest"),
    "FORMALIZATION": ("guarantees", "guaranteeformalizationrequest"),
    "RELEASE": ("guarantees", "guaranteereleaserequest"),
    "COLLECTION": ("collections", "collectioncase"),
    "LITIGATION": ("collections", "litigationfile"),
}

# Pièces rattachées à un objet satellite du même module métier.
RELATED_KIND_ALIASES = {
    ("guarantees", "dationasset"): "DATION",
}

KIND_BY_MODEL = {v: k for k, v in RELATED_KINDS.items()}


def related_kind_for(app_label: str, model: str) -> str:
    key = (app_label, model)
    return RELATED_KIND_ALIASES.get(key) or KIND_BY_MODEL.get(key, "OTHER")


def _model_pairs_for_kind(kind: str):
    pairs = [RELATED_KINDS[kind]]
    pairs.extend(
        pair for pair, alias in RELATED_KIND_ALIASES.items() if alias == kind
    )
    return pairs


def _known_related_content_types():
    pairs = list(RELATED_KINDS.values()) + list(RELATED_KIND_ALIASES)
    return [ct for ct in (_content_type(*pair) for pair in pairs) if ct]


def _content_type(app_label: str, model: str):
    return ContentType.objects.filter(app_label=app_label, model=model).first()


def _client_scope_q(client_id):
    """Documents du client ou d'un objet métier rattaché à ce client."""
    from apps.collections.models import CollectionCase, LitigationFile
    from apps.credits.models import CreditApplication, Loan
    from apps.guarantees.models import (
        DationAsset,
        DationRequest,
        Guarantee,
        GuaranteeFormalizationRequest,
        GuaranteeReleaseRequest,
    )
    from apps.sureties.models import SuretyEngagement

    q = Q()

    def _ids(qs):
        return list(qs.values_list("id", flat=True)[:400])

    def _add(app, model, qs):
        nonlocal q
        ct = _content_type(app, model)
        ids = _ids(qs)
        if ct and ids:
            q |= Q(content_type=ct, object_id__in=ids)

    ct_client = _content_type("clients", "client")
    if ct_client:
        q |= Q(content_type=ct_client, object_id=client_id)

    apps = CreditApplication.objects.filter(client_id=client_id)
    app_ids = _ids(apps)
    _add("credits", "creditapplication", apps)
    _add("credits", "loan", Loan.objects.filter(application__client_id=client_id))
    _add("guarantees", "guarantee", Guarantee.objects.filter(client_id=client_id))
    dations = DationRequest.objects.filter(client_id=client_id)
    _add("guarantees", "dationrequest", dations)
    _add(
        "guarantees",
        "dationasset",
        DationAsset.objects.filter(dation__client_id=client_id),
    )
    _add(
        "guarantees",
        "guaranteeformalizationrequest",
        GuaranteeFormalizationRequest.objects.filter(
            Q(guarantee__client_id=client_id) | Q(application__client_id=client_id)
        ),
    )
    _add(
        "guarantees",
        "guaranteereleaserequest",
        GuaranteeReleaseRequest.objects.filter(
            Q(guarantee__client_id=client_id) | Q(application__client_id=client_id)
        ),
    )
    cases = CollectionCase.objects.filter(loan__application__client_id=client_id)
    _add("collections", "collectioncase", cases)
    if app_ids:
        surety_ids = list(
            SuretyEngagement.objects.filter(application_id__in=app_ids)
            .values_list("surety_id", flat=True)
            .distinct()[:400]
        )
        ct_surety = _content_type("sureties", "surety")
        if ct_surety and surety_ids:
            q |= Q(content_type=ct_surety, object_id__in=surety_ids)
    case_ids = _ids(cases)
    if case_ids:
        _add(
            "collections",
            "litigationfile",
            LitigationFile.objects.filter(case_id__in=case_ids),
        )

    return q if q else Q(pk__in=[])


def apply_document_list_filters(qs, request):
    kind = query_param(request, "related_kind").upper()
    if kind in RELATED_KINDS:
        cts = [
            ct
            for ct in (
                _content_type(app, model)
                for app, model in _model_pairs_for_kind(kind)
            )
            if ct
        ]
        qs = qs.filter(content_type__in=cts) if cts else qs.none()
    elif kind == "OTHER":
        known = _known_related_content_types()
        qs = qs.filter(Q(content_type__isnull=True) | ~Q(content_type__in=known))

    expiry = query_param(request, "expiry")
    today = timezone.now().date()
    horizon = today + timedelta(days=30)
    if expiry == "expired":
        qs = qs.filter(expiry_date__lt=today)
    elif expiry == "expiring":
        qs = qs.filter(expiry_date__gte=today, expiry_date__lte=horizon)
    elif expiry == "dated":
        qs = qs.filter(expiry_date__isnull=False)
    elif expiry == "none":
        qs = qs.filter(expiry_date__isnull=True)

    uploader = query_param(request, "uploaded_by") or query_param(
        request, "gestionnaire"
    )
    if uploader:
        qs = qs.filter(uploaded_by_id=uploader)

    created_after = parse_date(query_param(request, "created_after"))
    created_before = parse_date(query_param(request, "created_before"))
    if created_after:
        qs = qs.filter(created_at__date__gte=created_after)
    if created_before:
        qs = qs.filter(created_at__date__lte=created_before)

    client_id = query_param(request, "client")
    if client_id:
        qs = qs.filter(_client_scope_q(client_id))

    return qs
