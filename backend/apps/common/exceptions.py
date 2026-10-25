"""Gestion homogène des erreurs de l'API."""
import logging

from rest_framework.views import exception_handler

logger = logging.getLogger("finflow")


def custom_exception_handler(exc, context):
    """Enveloppe les erreurs DRF dans un format cohérent et journalisé."""
    response = exception_handler(exc, context)

    if response is not None:
        response.data = {
            "success": False,
            "status_code": response.status_code,
            "errors": response.data,
        }
    else:
        view = context.get("view")
        logger.exception("Erreur non gérée dans %s", view)

    return response
