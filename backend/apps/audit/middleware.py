"""Middleware renseignant le contexte d'audit pour chaque requête."""
from .context import reset_audit_context, set_audit_context


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class AuditContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and not user.is_authenticated:
            user = None
        tokens = set_audit_context(user, _client_ip(request))
        try:
            return self.get_response(request)
        finally:
            reset_audit_context(tokens)
