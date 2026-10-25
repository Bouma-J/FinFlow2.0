"""Utilitaires de gestion des fichiers uploadés."""
import os
import re


_UNSAFE_CHARS = re.compile(r"[^\w.\- ()\[\]]+", re.UNICODE)


def safe_filename(filename, max_base=80):
    """
    Nom de fichier sûr pour stockage local / clés S3.

    - Ne conserve que le dernier segment (anti path traversal)
    - Supprime séparateurs et caractères de contrôle
    - Tronque base + extension
    """
    raw = (filename or "").replace("\\", "/").strip()
    name = os.path.basename(raw)
    if not name or name in (".", ".."):
        name = "file"

    # Neutralise null bytes / contrôles
    name = "".join(ch for ch in name if ch.isprintable() and ch not in "/\\")
    name = _UNSAFE_CHARS.sub("_", name).strip("._ ") or "file"

    base, ext = os.path.splitext(name)
    base = (base or "file").strip("._ ") or "file"
    # Extension : point + alphanum uniquement
    if ext:
        ext_body = "".join(c for c in ext[1:] if c.isalnum())[:11]
        ext = f".{ext_body}" if ext_body else ""
    return f"{base[:max_base]}{ext}"
