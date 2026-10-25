"""Validation centralisée des uploads (taille, extension, magic bytes, quota)."""
from __future__ import annotations

import os
from typing import Any

from django.conf import settings
from rest_framework.exceptions import ValidationError

from apps.common.files import safe_filename

# Signatures minimales (préfixe) → extensions attendues
_MAGIC_RULES: list[tuple[bytes, frozenset[str]]] = [
    (b"%PDF", frozenset({"pdf"})),
    (b"\xff\xd8\xff", frozenset({"jpg", "jpeg"})),
    (b"\x89PNG\r\n\x1a\n", frozenset({"png"})),
    (b"II*\x00", frozenset({"tiff", "tif"})),
    (b"MM\x00*", frozenset({"tiff", "tif"})),
    # DOCX / XLSX = ZIP (PK)
    (b"PK\x03\x04", frozenset({"docx", "xlsx", "zip"})),
    (b"PK\x05\x06", frozenset({"docx", "xlsx", "zip"})),
    (b"PK\x07\x08", frozenset({"docx", "xlsx", "zip"})),
]


def resolve_tenant_from_context(context: dict | None):
    """Tenant courant depuis le contexte serializer / request."""
    context = context or {}
    request = context.get("request")
    user = getattr(request, "user", None) if request is not None else None
    tenant = getattr(user, "tenant", None) if user is not None else None
    if tenant is not None:
        return tenant
    if request is None:
        return None
    from apps.common.tenancy import get_current_tenant_id
    from apps.tenants.models import Tenant

    tid = get_current_tenant_id()
    if not tid:
        return None
    return Tenant.objects.filter(pk=tid).first()


def _file_size(file_obj) -> int:
    size = getattr(file_obj, "size", None)
    if size is not None:
        return int(size)
    if hasattr(file_obj, "seek") and hasattr(file_obj, "tell"):
        pos = file_obj.tell()
        file_obj.seek(0, os.SEEK_END)
        size = file_obj.tell()
        file_obj.seek(pos)
        return int(size)
    return 0


def _read_header(file_obj, n: int = 16) -> bytes:
    if not hasattr(file_obj, "read"):
        return b""
    pos = file_obj.tell() if hasattr(file_obj, "tell") else 0
    try:
        header = file_obj.read(n) or b""
    finally:
        if hasattr(file_obj, "seek"):
            try:
                file_obj.seek(pos)
            except Exception:  # noqa: BLE001
                pass
    return header if isinstance(header, (bytes, bytearray)) else b""


def _extension(name: str) -> str:
    return os.path.splitext(safe_filename(name or "file"))[1].lower().lstrip(".")


def _magic_compatible(header: bytes, ext: str) -> bool:
    """True si pas de règle ou si le magic matche l'extension."""
    if not header or len(header) < 2:
        return True  # flux vide / non lisible : ne bloque pas hors taille/ext
    matched_exts: set[str] = set()
    for prefix, exts in _MAGIC_RULES:
        if header.startswith(prefix):
            matched_exts |= set(exts)
    if not matched_exts:
        # Pas de signature connue (ex. texte) — refuse les binaires suspects
        # seulement si l'extension est dans la liste « magique » attendue.
        if ext in {"pdf", "jpg", "jpeg", "png", "tiff", "tif", "docx", "xlsx"}:
            return False
        return True
    return ext in matched_exts


def validate_uploaded_file(
    file_obj,
    *,
    tenant=None,
    check_quota: bool = True,
    allowed_extensions: list[str] | None = None,
    max_mb: int | None = None,
):
    """
    Valide un fichier uploadé.

    - Taille ≤ GED_MAX_UPLOAD_SIZE_MB (ou max_mb)
    - Extension allowlist
    - Magic bytes compatibles (PDF/JPEG/PNG/TIFF/Office)
    - Quota GED optionnel
    - Renomme file_obj.name via safe_filename
    """
    if file_obj is None:
        return file_obj

    max_mb = int(max_mb or getattr(settings, "GED_MAX_UPLOAD_SIZE_MB", 25))
    allowed = {
        e.lower().lstrip(".")
        for e in (
            allowed_extensions
            or getattr(settings, "GED_ALLOWED_EXTENSIONS", [])
            or []
        )
    }
    max_bytes = max_mb * 1024 * 1024
    size = _file_size(file_obj)
    if size > max_bytes:
        raise ValidationError(
            f"Fichier trop volumineux (max {max_mb} Mo)."
        )

    raw_name = getattr(file_obj, "name", "") or "file"
    safe_name = safe_filename(raw_name)
    ext = _extension(safe_name)
    if not ext or ext not in allowed:
        raise ValidationError(
            f"Extension « {ext or '?'} » non autorisée. "
            f"Autorisées : {', '.join(sorted(allowed))}."
        )

    header = _read_header(file_obj)
    if not _magic_compatible(header, ext):
        raise ValidationError(
            "Le contenu du fichier ne correspond pas à son extension "
            "(type MIME réel suspect)."
        )

    if check_quota and tenant is not None and size > 0:
        from apps.documents.quotas import assert_ged_quota

        assert_ged_quota(tenant, size)

    if hasattr(file_obj, "name"):
        file_obj.name = safe_name
    return file_obj


def validate_attrs_uploads(
    attrs: dict[str, Any],
    context: dict | None = None,
    *,
    check_quota: bool = True,
    allowed_extensions: list[str] | None = None,
) -> dict[str, Any]:
    """Parcourt attrs et valide tout objet fichier (FileField / upload)."""
    tenant = resolve_tenant_from_context(context)
    for key, value in list(attrs.items()):
        if value is None:
            continue
        if hasattr(value, "read") and (
            hasattr(value, "size") or hasattr(value, "seek")
        ):
            attrs[key] = validate_uploaded_file(
                value,
                tenant=tenant,
                check_quota=check_quota,
                allowed_extensions=allowed_extensions,
            )
    return attrs


def assert_upload_meta(
    *,
    filename: str,
    size: int | None = None,
    allowed_extensions: list[str] | None = None,
    max_mb: int | None = None,
) -> str:
    """Valide métadonnées avant présign (sans fichier ouvert). Retourne safe name."""
    max_mb = int(max_mb or getattr(settings, "GED_MAX_UPLOAD_SIZE_MB", 25))
    allowed = {
        e.lower().lstrip(".")
        for e in (
            allowed_extensions
            or getattr(settings, "GED_ALLOWED_EXTENSIONS", [])
            or []
        )
    }
    safe_name = safe_filename(filename or "file")
    ext = _extension(safe_name)
    if not ext or ext not in allowed:
        raise ValidationError(
            f"Extension « {ext or '?'} » non autorisée pour l'upload."
        )
    if size is not None and size > max_mb * 1024 * 1024:
        raise ValidationError(f"Fichier trop volumineux (max {max_mb} Mo).")
    return safe_name
