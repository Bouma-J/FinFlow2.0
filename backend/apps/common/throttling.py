"""Limitation de débit API (anti-abus)."""

from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """Limite les tentatives d'obtention de jeton JWT."""

    scope = "login"


class BurstUserRateThrottle(SimpleRateThrottle):
    """Plafond court pour un utilisateur authentifié (rafales)."""

    scope = "user_burst"

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return None
        return self.cache_format % {
            "scope": self.scope,
            "ident": request.user.pk,
        }
