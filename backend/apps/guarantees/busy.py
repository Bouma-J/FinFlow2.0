"""Verrou partagé : une garantie ne peut être dans qu'un processus ouvert."""
from __future__ import annotations

KIND_DATION = "DATION"
KIND_FORMALIZATION = "FORMALIZATION"
KIND_RELEASE = "RELEASE"

_KIND_PRIORITY = (KIND_DATION, KIND_RELEASE, KIND_FORMALIZATION)

_LABELS = {
    KIND_DATION: "Dation en cours",
    KIND_FORMALIZATION: "Formalisation en cours",
    KIND_RELEASE: "Main levée en cours",
}

_MESSAGES = {
    KIND_DATION: "Cette garantie est déjà engagée dans une dation ouverte.",
    KIND_FORMALIZATION: "Une formalisation est déjà en cours pour cette garantie.",
    KIND_RELEASE: "Une demande de main levée est déjà en cours pour cette garantie.",
}


def _payload(kind: str, request_id) -> dict:
    return {
        "kind": kind,
        "id": str(request_id),
        "label": _LABELS[kind],
        "message": _MESSAGES[kind],
    }


def busy_map(
    guarantee_ids,
    *,
    exclude_kind: str | None = None,
    exclude_id=None,
) -> dict[str, dict]:
    """
    {guarantee_id: {kind, id, label, message}} pour les garanties occupées.
    Si plusieurs processus ouverts (données anciennes), le plus destructeur gagne.
    """
    from .models import (
        DationAsset,
        DationRequest,
        GuaranteeFormalizationRequest,
        GuaranteeReleaseRequest,
    )

    ids = [gid for gid in guarantee_ids if gid]
    if not ids:
        return {}

    found: dict[str, dict] = {}

    def _keep(gid, kind, request_id):
        if exclude_kind == kind and exclude_id and str(request_id) == str(exclude_id):
            return
        key = str(gid)
        prev = found.get(key)
        if prev and _KIND_PRIORITY.index(prev["kind"]) <= _KIND_PRIORITY.index(kind):
            return
        found[key] = _payload(kind, request_id)

    open_dation = (
        DationRequest.Status.DRAFT,
        DationRequest.Status.IN_APPROVAL,
        DationRequest.Status.RETURNED,
        DationRequest.Status.APPROVED,
        DationRequest.Status.BLOCKED,
    )
    for gid, req_id in DationAsset.objects.filter(
        guarantee_id__in=ids,
        dation__status__in=open_dation,
    ).values_list("guarantee_id", "dation_id"):
        _keep(gid, KIND_DATION, req_id)

    open_release = (
        GuaranteeReleaseRequest.Status.DRAFT,
        GuaranteeReleaseRequest.Status.IN_APPROVAL,
        GuaranteeReleaseRequest.Status.RETURNED,
        GuaranteeReleaseRequest.Status.APPROVED,
        GuaranteeReleaseRequest.Status.BLOCKED,
    )
    for gid, req_id in GuaranteeReleaseRequest.objects.filter(
        guarantee_id__in=ids,
        status__in=open_release,
    ).values_list("guarantee_id", "id"):
        _keep(gid, KIND_RELEASE, req_id)

    open_form = (
        GuaranteeFormalizationRequest.Status.DRAFT,
        GuaranteeFormalizationRequest.Status.IN_PROGRESS,
        GuaranteeFormalizationRequest.Status.IN_APPROVAL,
        GuaranteeFormalizationRequest.Status.RETURNED,
        GuaranteeFormalizationRequest.Status.APPROVED,
    )
    for gid, req_id in GuaranteeFormalizationRequest.objects.filter(
        guarantee_id__in=ids,
        status__in=open_form,
    ).values_list("guarantee_id", "id"):
        _keep(gid, KIND_FORMALIZATION, req_id)

    return found


def guarantee_busy(
    guarantee,
    *,
    exclude_kind: str | None = None,
    exclude_id=None,
) -> dict | None:
    return busy_map(
        [getattr(guarantee, "pk", guarantee)],
        exclude_kind=exclude_kind,
        exclude_id=exclude_id,
    ).get(str(getattr(guarantee, "pk", guarantee)))
