"""Détection d'URL / hôte IPv4 (HSTS IP vs domaine)."""


def host_is_ipv4(value: str) -> bool:
    host = (value or "").split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    parts = host.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False
