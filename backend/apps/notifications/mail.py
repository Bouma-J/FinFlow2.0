"""Envoi d'e-mails avec SMTP optionnel par filiale."""
from __future__ import annotations

import logging
import os
import socket
import smtplib
import ssl
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.mail.backends.smtp import EmailBackend as DjangoSMTPBackend

logger = logging.getLogger("finflow")

SMTP_CONNECT_TIMEOUT = 12


def build_smtp_ssl_context(*, verify: bool | None = None) -> ssl.SSLContext:
    """
    Contexte TLS pour SMTP (STARTTLS / SSL implicite).

    Charge les CA système + bundles optionnels (proxy / antivirus).
    Si `SMTP_SSL_VERIFY=0`, la vérification est désactivée (démo Windows
    derrière Avast Mail Shield).
    """
    if verify is None:
        verify = bool(getattr(settings, "SMTP_SSL_VERIFY", True))

    if not verify:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        logger.warning(
            "SMTP TLS : vérification des certificats désactivée "
            "(SMTP_SSL_VERIFY=0)."
        )
        return ctx

    ctx = ssl.create_default_context()
    candidates = [
        os.environ.get("SSL_CERT_FILE"),
        os.environ.get("REQUESTS_CA_BUNDLE"),
        "/etc/ssl/certs/ca-certificates.crt",
        str(Path(settings.BASE_DIR) / "certs" / "ca-bundle.crt"),
    ]
    for path in candidates:
        if not path or not os.path.isfile(path) or os.path.getsize(path) == 0:
            continue
        try:
            ctx.load_verify_locations(cafile=path)
        except ssl.SSLError:
            logger.debug("Impossible de charger le bundle CA %s", path)
    return ctx


def _prefs_for(tenant):
    if tenant is None:
        return None
    from .models import TenantNotificationSettings

    return TenantNotificationSettings.for_tenant(tenant)


def tenant_has_smtp(prefs) -> bool:
    if prefs is None:
        return False
    return bool((prefs.smtp_host or "").strip() and (prefs.smtp_username or "").strip())


def normalize_smtp_host(host: str | None) -> str:
    """Corrige les hôtes courants mal saisis (ex. gmail.com → smtp.gmail.com)."""
    h = (host or "").strip()
    if not h:
        return ""
    key = h.lower().rstrip(".")
    aliases = {
        "gmail.com": "smtp.gmail.com",
        "googlemail.com": "smtp.gmail.com",
        "smtp.googlemail.com": "smtp.gmail.com",
        "outlook.com": "smtp.office365.com",
        "hotmail.com": "smtp.office365.com",
        "live.com": "smtp.office365.com",
        "office365.com": "smtp.office365.com",
    }
    return aliases.get(key, h)


def normalize_smtp_security(
    port: int | None,
    use_tls: bool,
    use_ssl: bool,
    *,
    host: str | None = None,
) -> tuple[int, bool, bool]:
    """
    Aligne port / TLS / SSL sur les usages SMTP courants.

    - 587 → STARTTLS (TLS), pas de SSL implicite
    - 465 → SSL implicite, pas de STARTTLS
    - Gmail / Google : forcer 587+TLS (le port 465 est souvent intercepté
      par les antivirus « Mail Shield », d'où des erreurs SSL trompeuses)
    """
    host_l = normalize_smtp_host(host).lower()
    if "gmail.com" in host_l or "googlemail.com" in host_l:
        return 587, True, False
    if "office365.com" in host_l or "outlook.com" in host_l:
        return 587, True, False

    port = int(port or 587)
    if port == 465:
        return port, False, True
    if port == 587:
        return port, True, False
    if use_ssl and use_tls:
        return port, False, True
    if not use_ssl and not use_tls:
        return port, True, False
    return port, bool(use_tls), bool(use_ssl)


def check_smtp_tcp(host: str, port: int, *, timeout: float = 5) -> str | None:
    """
    Vérifie rapidement la joignabilité TCP (IPv4 d'abord).
    Retourne un message d'erreur ou None si OK.
    """
    host = (host or "").strip()
    if not host:
        return "Serveur SMTP non renseigné."
    last_err: Exception | None = None
    try:
        infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        return f"Résolution DNS impossible pour {host}: {exc}"
    for _af, socktype, proto, _canon, sockaddr in infos:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socktype, proto)
            sock.settimeout(timeout)
            sock.connect(sockaddr)
            sock.close()
            return None
        except OSError as exc:
            last_err = exc
            if sock is not None:
                sock.close()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return None
    except OSError as exc:
        last_err = exc
    return f"Impossible de joindre {host}:{port} ({last_err})"


class _IPv4SMTP(smtplib.SMTP):
    """SMTP en IPv4 pour éviter les timeouts IPv6 derrière certains réseaux."""

    def _get_socket(self, host, port, timeout):
        last_error: OSError | None = None
        for res in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM):
            af, socktype, proto, _canon, sa = res
            sock = None
            try:
                sock = socket.socket(af, socktype, proto)
                if timeout is not None:
                    sock.settimeout(timeout)
                sock.connect(sa)
                return sock
            except OSError as exc:
                last_error = exc
                if sock is not None:
                    sock.close()
        if last_error is not None:
            raise last_error
        return super()._get_socket(host, port, timeout)


class _IPv4SMTP_SSL(smtplib.SMTP_SSL):
    def _get_socket(self, host, port, timeout):
        last_error: OSError | None = None
        context = self.context if self.context else build_smtp_ssl_context()
        for res in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM):
            af, socktype, proto, _canon, sa = res
            sock = None
            try:
                sock = socket.socket(af, socktype, proto)
                if timeout is not None:
                    sock.settimeout(timeout)
                sock.connect(sa)
                server_hostname = host if context.check_hostname else None
                return context.wrap_socket(sock, server_hostname=server_hostname)
            except OSError as exc:
                last_error = exc
                if sock is not None:
                    sock.close()
        if last_error is not None:
            raise last_error
        return super()._get_socket(host, port, timeout)


class TenantSMTPEmailBackend(DjangoSMTPBackend):
    """SMTP filiale en IPv4, avec contexte TLS adapté (CA / antivirus)."""

    def __init__(self, *args, **kwargs):
        # Consumé avant super() pour ne pas polluer EmailBackend.
        self._custom_ssl_context = kwargs.pop("ssl_context", None)
        super().__init__(*args, **kwargs)

    @property
    def connection_class(self):
        return _IPv4SMTP_SSL if self.use_ssl else _IPv4SMTP

    @property
    def ssl_context(self):
        if self._custom_ssl_context is not None:
            return self._custom_ssl_context
        return build_smtp_ssl_context()


def _sanitize_display_name(name: str) -> str:
    return (
        (name or "")
        .replace("<", "")
        .replace(">", "")
        .replace('"', "")
        .replace("\n", " ")
        .replace("\r", " ")
        .strip()
    )


def _extract_email_address(value: str) -> str:
    """Extrait l'adresse d'un From « Nom <email> » ou renvoie la valeur si simple."""
    import re

    value = (value or "").strip()
    if not value:
        return ""
    m = re.search(r"<\s*([^<>@\s]+@[^<>@\s]+)\s*>", value)
    if m:
        return m.group(1).strip()
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        return value
    return value


def format_noreply_from(address: str, *, tenant=None) -> str:
    """
    Construit l'en-tête From : « NOREPLY NomFiliale <adresse@…> ».

    Si `address` contient déjà un nom d'affichage explicite, il est conservé.
    """
    address = (address or "").strip()
    if not address:
        return ""
    if "<" in address and ">" in address:
        return address

    email = _extract_email_address(address) or address
    tenant_label = ""
    if tenant is not None:
        tenant_label = _sanitize_display_name(
            getattr(tenant, "name", None) or getattr(tenant, "code", "") or ""
        )
    display = f"NOREPLY {tenant_label}".strip() if tenant_label else "NOREPLY"
    if any(c in display for c in (",", ";", "@")):
        display = f'"{display}"'
    return f"{display} <{email}>"


def resolve_from_email(prefs=None, *, tenant=None, fallback: str | None = None) -> str:
    """
    Expéditeur effectif.

    Priorité adresse : from_email (prefs) → identifiant SMTP → DEFAULT_FROM_EMAIL.
    Nom d'affichage : « NOREPLY {filiale} » (sauf From déjà formatté avec un nom).
    """
    if tenant is None and prefs is not None:
        tenant = getattr(prefs, "tenant", None)

    address = ""
    if prefs is not None:
        custom = (prefs.from_email or "").strip()
        if custom:
            if "<" in custom and ">" in custom:
                return custom
            address = _extract_email_address(custom) or custom
        elif tenant_has_smtp(prefs) and (prefs.smtp_username or "").strip():
            address = prefs.smtp_username.strip()

    if not address:
        address = (fallback or settings.DEFAULT_FROM_EMAIL or "").strip()

    return format_noreply_from(address, tenant=tenant)


def get_connection_for_tenant(tenant=None, prefs=None):
    """
    Connexion SMTP de la filiale si configurée, sinon backend Django global.
    """
    prefs = prefs if prefs is not None else _prefs_for(tenant)
    if tenant_has_smtp(prefs):
        host = normalize_smtp_host(prefs.smtp_host)
        port, use_tls, use_ssl = normalize_smtp_security(
            prefs.smtp_port,
            bool(prefs.smtp_use_tls),
            bool(prefs.smtp_use_ssl),
            host=host,
        )
        password = (prefs.smtp_password or "").replace(" ", "")
        from apps.common.secret_crypto import decrypt_str

        password = decrypt_str(password).replace(" ", "")
        return get_connection(
            backend="apps.notifications.mail.TenantSMTPEmailBackend",
            host=host,
            port=port,
            username=(prefs.smtp_username or "").strip(),
            password=password,
            use_tls=use_tls,
            use_ssl=use_ssl,
            timeout=SMTP_CONNECT_TIMEOUT,
            fail_silently=False,
            ssl_context=build_smtp_ssl_context(),
        )
    return get_connection(fail_silently=False)


def send_email_for_tenant(
    *,
    tenant,
    subject: str,
    text_body: str,
    html_body: str | None = None,
    recipients: list[str],
    reply_to: list[str] | None = None,
    cc: list[str] | None = None,
    from_email: str | None = None,
    prefs=None,
) -> None:
    """
    Envoie un e-mail via le SMTP de la filiale (ou le SMTP global en repli).

    Lève une exception en cas d'échec (à journaliser côté appelant).
    """
    if not recipients:
        raise ValueError("Aucun destinataire.")

    prefs = prefs if prefs is not None else _prefs_for(tenant)
    connection = get_connection_for_tenant(tenant, prefs=prefs)
    explicit = (from_email or "").strip()
    if explicit:
        sender = format_noreply_from(explicit, tenant=tenant)
    else:
        sender = resolve_from_email(prefs, tenant=tenant)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=sender,
        to=recipients,
        cc=cc or None,
        reply_to=reply_to or None,
        connection=connection,
    )
    if html_body:
        msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)
