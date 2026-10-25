"""Contexte de requête pour la piste d'audit (utilisateur, IP)."""
from contextvars import ContextVar

_current_user = ContextVar("audit_current_user", default=None)
_current_ip = ContextVar("audit_current_ip", default=None)


def set_audit_context(user, ip):
    return _current_user.set(user), _current_ip.set(ip)


def get_current_user():
    return _current_user.get()


def get_current_ip():
    return _current_ip.get()


def reset_audit_context(tokens):
    user_token, ip_token = tokens
    _current_user.reset(user_token)
    _current_ip.reset(ip_token)
