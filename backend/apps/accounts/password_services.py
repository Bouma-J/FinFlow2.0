"""Génération et envoi des mots de passe temporaires."""
from __future__ import annotations

import logging
import secrets
import string

from django.conf import settings
from django.utils.html import escape

logger = logging.getLogger("finflow")


def generate_temporary_password(length: int = 14) -> str:
    """Mot de passe aléatoire respectant les contraintes de complexité usuelles."""
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"
    specials = "!@#$%&*"
    for _ in range(50):
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in pwd)
            and any(c.isupper() for c in pwd)
            and any(c.isdigit() for c in pwd)
            and any(c in specials for c in pwd)
        ):
            return pwd
    return (
        secrets.choice(string.ascii_uppercase)
        + secrets.choice(string.ascii_lowercase)
        + secrets.choice(string.digits)
        + secrets.choice(specials)
        + "".join(secrets.choice(alphabet) for _ in range(max(0, length - 4)))
    )


def _frontend_base() -> str:
    return (getattr(settings, "FRONTEND_BASE_URL", None) or "http://localhost").rstrip(
        "/"
    )


def send_credentials_email(user, raw_password: str, *, reason: str = "created") -> bool:
    """
    Envoie le mot de passe temporaire par e-mail.

    Utilise le SMTP de la filiale de l'utilisateur s'il est configuré,
    sinon le SMTP global Django.
    """
    email = (user.email or "").strip()
    if not email:
        logger.warning(
            "Pas d'e-mail pour envoyer le mot de passe (user=%s)", user.username
        )
        return False

    login_url = f"{_frontend_base()}/login"
    if reason == "reset":
        subject = "[FIN_FLOW] Nouveau mot de passe temporaire"
        title = "Mot de passe régénéré"
        intro = (
            "Un administrateur a régénéré votre mot de passe FIN_FLOW. "
            "Utilisez le mot de passe temporaire ci-dessous pour vous connecter, "
            "puis choisissez immédiatement un nouveau mot de passe."
        )
    else:
        subject = "[FIN_FLOW] Vos identifiants de connexion"
        title = "Bienvenue sur FIN_FLOW"
        intro = (
            "Votre compte FIN_FLOW a été créé. "
            "Connectez-vous avec les identifiants ci-dessous ; "
            "vous devrez changer votre mot de passe à la première connexion."
        )

    display = user.get_full_name() or user.username
    text = (
        f"{title}\n\n"
        f"Bonjour {display},\n\n"
        f"{intro}\n\n"
        f"Identifiant : {user.username}\n"
        f"Mot de passe temporaire : {raw_password}\n\n"
        f"Connexion : {login_url}\n\n"
        "Ne partagez pas ce message. Ce mot de passe est à usage unique "
        "jusqu'à son remplacement.\n"
    )
    html = f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;max-width:560px;margin:0 auto;color:#1a1a1a">
      <h2 style="color:#0b3d2e">{escape(title)}</h2>
      <p>Bonjour <strong>{escape(display)}</strong>,</p>
      <p>{escape(intro)}</p>
      <table style="border-collapse:collapse;margin:16px 0;width:100%">
        <tr>
          <td style="padding:8px;background:#f4f7f5;border:1px solid #dce5e0">Identifiant</td>
          <td style="padding:8px;border:1px solid #dce5e0"><code>{escape(user.username)}</code></td>
        </tr>
        <tr>
          <td style="padding:8px;background:#f4f7f5;border:1px solid #dce5e0">Mot de passe temporaire</td>
          <td style="padding:8px;border:1px solid #dce5e0"><code>{escape(raw_password)}</code></td>
        </tr>
      </table>
      <p><a href="{escape(login_url)}" style="display:inline-block;padding:10px 16px;background:#0b3d2e;color:#fff;text-decoration:none;border-radius:4px">Se connecter</a></p>
      <p style="color:#666;font-size:13px">Ne partagez pas ce message. Changez ce mot de passe dès la première connexion.</p>
    </div>
    """

    try:
        from apps.notifications.mail import send_email_for_tenant

        tenant = getattr(user, "tenant", None)
        send_email_for_tenant(
            tenant=tenant,
            subject=subject,
            text_body=text,
            html_body=html,
            recipients=[email],
        )
        return True
    except Exception:  # noqa: BLE001
        logger.exception(
            "Échec d'envoi du mot de passe temporaire à %s (user=%s)",
            email,
            user.username,
        )
        return False


def _invalidate_me_cache(user) -> None:
    try:
        from apps.common.cache_utils import invalidate_prefix

        invalidate_prefix("me", user.id)
    except Exception:  # noqa: BLE001
        logger.debug("Impossible d'invalider le cache me pour %s", user.pk)


def assign_password(
    user,
    raw_password: str,
    *,
    must_change_password: bool = True,
    commit: bool = True,
) -> None:
    """Applique un mot de passe choisi (admin) après validation Django."""
    from django.contrib.auth.password_validation import validate_password

    validate_password(raw_password, user=user)
    user.set_password(raw_password)
    user.must_change_password = must_change_password
    if commit:
        user.save(update_fields=["password", "must_change_password"])
        _invalidate_me_cache(user)


def issue_temporary_password(
    user,
    *,
    reason: str = "created",
    send_email: bool = True,
    commit: bool = True,
) -> tuple[str, bool]:
    """Définit un mot de passe temporaire et force le changement à la prochaine connexion."""
    raw = generate_temporary_password()
    user.set_password(raw)
    user.must_change_password = True
    if commit:
        user.save(update_fields=["password", "must_change_password"])
        _invalidate_me_cache(user)
    email_sent = False
    if send_email:
        email_sent = send_credentials_email(user, raw, reason=reason)
    return raw, email_sent


PASSWORD_DELIVERY_EMAIL = "email"
PASSWORD_DELIVERY_MANUAL = "manual"
PASSWORD_DELIVERY_CHOICES = (
    (PASSWORD_DELIVERY_EMAIL, "Envoyer par e-mail"),
    (PASSWORD_DELIVERY_MANUAL, "Définir manuellement"),
)


def validate_password_delivery(attrs: dict, *, email_field: str = "email") -> dict:
    """
    Valide password_delivery / password / password_confirm.

    - email : adresse e-mail obligatoire, mot de passe généré côté serveur.
    - manual : mot de passe + confirmation obligatoires (e-mail optionnel).
    """
    from rest_framework import serializers

    delivery = (attrs.get("password_delivery") or PASSWORD_DELIVERY_EMAIL).strip()
    if delivery not in (PASSWORD_DELIVERY_EMAIL, PASSWORD_DELIVERY_MANUAL):
        raise serializers.ValidationError({
            "password_delivery": "Choix invalide (email ou manual)."
        })
    attrs["password_delivery"] = delivery

    email = (attrs.get(email_field) or "").strip()
    if delivery == PASSWORD_DELIVERY_EMAIL and not email:
        raise serializers.ValidationError({
            email_field: (
                "L'adresse e-mail est obligatoire pour envoyer le mot de passe."
            )
        })
    if email_field in attrs or email:
        attrs[email_field] = email

    password = attrs.get("password") or ""
    confirm = attrs.get("password_confirm") or ""
    if delivery == PASSWORD_DELIVERY_MANUAL:
        if not password:
            raise serializers.ValidationError({
                "password": "Indiquez le mot de passe à attribuer."
            })
        if password != confirm:
            raise serializers.ValidationError({
                "password_confirm": "Les mots de passe ne correspondent pas."
            })
        if len(password) < 10:
            raise serializers.ValidationError({
                "password": "Le mot de passe doit contenir au moins 10 caractères."
            })
    else:
        attrs.pop("password", None)
        attrs.pop("password_confirm", None)
    return attrs
