"""Middleware résolvant le tenant courant et observabilité latence."""
from __future__ import annotations

import logging
import time

from .tenancy import (
    reset_current_tenant,
    set_current_tenant,
    set_group_context,
)

# En-tête permettant à un utilisateur Groupe de cibler une filiale précise
TENANT_HEADER = "HTTP_X_TENANT_ID"

logger = logging.getLogger("finflow.metrics")


class CurrentTenantMiddleware:
    """
    Détermine le tenant courant pour chaque requête :

    1. Utilisateur rattaché à une filiale -> son tenant.
    2. Utilisateur Groupe -> contexte Groupe ; peut cibler une filiale
       précise via l'en-tête `X-Tenant-Id`.
    3. Anonyme -> aucun tenant (les vues protégées refuseront l'accès).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = None
        group_token = None
        user = getattr(request, "user", None)

        if user is not None and user.is_authenticated:
            is_group = getattr(user, "is_group_level", False)
            if is_group:
                group_token = set_group_context(True)
                requested = request.META.get(TENANT_HEADER)
                token = set_current_tenant(requested or None)
            else:
                group_token = set_group_context(False)
                token = set_current_tenant(getattr(user, "tenant_id", None))

        try:
            response = self.get_response(request)
        finally:
            if token is not None:
                reset_current_tenant(token)
            if group_token is not None:
                from .tenancy import _is_group_context

                _is_group_context.reset(group_token)
        return response


class RequestTimingMiddleware:
    """Logue les requêtes lentes et expose X-Response-Time-Ms."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.slow_ms = 1500

    def __call__(self, request):
        start = time.perf_counter()
        response = self.get_response(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        response["X-Response-Time-Ms"] = f"{elapsed_ms:.1f}"
        if elapsed_ms >= self.slow_ms:
            logger.warning(
                "slow_request path=%s method=%s status=%s ms=%.1f",
                getattr(request, "path", ""),
                getattr(request, "method", ""),
                getattr(response, "status_code", ""),
                elapsed_ms,
            )
        return response
