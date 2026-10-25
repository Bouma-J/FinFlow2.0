"""Statut des tâches Celery lancées par l'API (polling FE)."""
from __future__ import annotations

from celery.result import AsyncResult
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import MustChangePasswordGate
from apps.common.scoped import async_task_owner


class AsyncTaskStatusView(APIView):
    """
    GET /api/v1/async-tasks/<task_id>/

    Retourne l'état Celery (PENDING / STARTED / SUCCESS / FAILURE…).
    Si la tâche a été trackée à l'enqueue, seul le lanceur (ou un
    superuser) peut la consulter.
    """

    permission_classes = [IsAuthenticated, MustChangePasswordGate]

    def get(self, request, task_id: str):
        task_id = (task_id or "").strip()
        if not task_id:
            raise NotFound()

        owner = async_task_owner(task_id)
        if owner is not None:
            if (
                str(request.user.id) != owner
                and not request.user.is_superuser
            ):
                raise PermissionDenied(
                    "Cette tâche ne vous appartient pas."
                )
        else:
            # Tâche non trackée : ne pas interroger le broker (latence / faux PENDING).
            return Response(
                {
                    "task_id": task_id,
                    "state": "UNKNOWN",
                    "ready": False,
                    "detail": "Tâche inconnue ou expirée.",
                }
            )

        result = AsyncResult(task_id)
        try:
            state = result.state or "PENDING"
            ready = result.ready()
        except Exception:  # noqa: BLE001 — broker down / test sans Redis
            state = "PENDING"
            ready = False
            result = None

        payload: dict = {
            "task_id": task_id,
            "state": state,
            "ready": ready,
        }

        if result is not None and state == "FAILURE":
            err = result.result
            payload["detail"] = (
                str(err)[:500] if err is not None else "Échec de la tâche."
            )
        elif result is not None and state == "SUCCESS" and isinstance(
            result.result, dict
        ):
            slim = {
                k: result.result[k]
                for k in ("id", "status", "detail", "updated", "created")
                if k in result.result
            }
            if slim:
                payload["result"] = slim

        return Response(payload)
