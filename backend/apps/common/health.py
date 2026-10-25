"""Santé plateforme et métriques d'exploitation."""
from __future__ import annotations

import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import MustChangePasswordGate


def _check_database() -> dict:
    t0 = time.perf_counter()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"ok": True, "latency_ms": round((time.perf_counter() - t0) * 1000, 2)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _check_cache() -> dict:
    t0 = time.perf_counter()
    try:
        key = "healthcheck:ping"
        cache.set(key, "1", 5)
        ok = cache.get(key) == "1"
        return {
            "ok": ok,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _check_storage() -> dict:
    backend = getattr(settings, "STORAGE_BACKEND", "local")
    if backend != "s3":
        return {"ok": True, "backend": "local"}
    try:
        import boto3
        from botocore.client import Config

        t0 = time.perf_counter()
        client = boto3.client(
            "s3",
            endpoint_url=getattr(settings, "AWS_S3_ENDPOINT_URL", None) or None,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=getattr(settings, "AWS_S3_REGION_NAME", "us-east-1"),
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        client.head_bucket(Bucket=settings.AWS_STORAGE_BUCKET_NAME)
        return {
            "ok": True,
            "backend": "s3",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "backend": "s3", "error": str(exc)}


def _sanitize_check(result: dict) -> dict:
    """Masque les messages d'erreur détaillés hors DEBUG (anti-recon)."""
    out = {"ok": bool(result.get("ok"))}
    if "latency_ms" in result:
        out["latency_ms"] = result["latency_ms"]
    if "backend" in result:
        out["backend"] = result["backend"]
    if not out["ok"]:
        if settings.DEBUG:
            out["error"] = str(result.get("error") or "unavailable")
        else:
            out["error"] = "unavailable"
    return out


class HealthView(APIView):
    """
    Sonde liveness/readiness (DB, Redis, stockage).
    Public pour les probes K8s ; ne révèle pas de secrets.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        checks = {
            "database": _sanitize_check(_check_database()),
            "cache": _sanitize_check(_check_cache()),
            "storage": _sanitize_check(_check_storage()),
        }
        ready = all(c.get("ok") for c in checks.values())
        return Response(
            {
                "status": "ok" if ready else "degraded",
                "ready": ready,
                "time": timezone.now().isoformat(),
                "checks": checks,
            },
            status=200 if ready else 503,
        )


def _is_group_operator(user) -> bool:
    return bool(
        user.is_superuser or getattr(user, "is_group_level", False)
    )


def _is_ops_operator(user) -> bool:
    """Exploitation plateforme : staff filiale, Groupe ou superuser."""
    return bool(_is_group_operator(user) or getattr(user, "is_staff", False))


def _request_tenant_id(request):
    """Filiale ciblée (JWT filiale, ou X-Tenant-Id pour un opérateur Groupe)."""
    user = request.user
    if getattr(user, "is_group_level", False) or user.is_superuser:
        return request.META.get("HTTP_X_TENANT_ID") or None
    return getattr(user, "tenant_id", None)


class MetricsView(APIView):
    """Agrégats d'exploitation **transverses** — niveau Groupe uniquement.

    Un administrateur de filiale est ``is_staff`` pour les menus SPA, pas
    pour voir le volume des autres filiales. L'état Celery / soft-delete
    de *sa* filiale est exposé par ``OpsStatusView``.
    """

    permission_classes = [IsAuthenticated, MustChangePasswordGate]

    def get(self, request):
        if not _is_group_operator(request.user):
            raise PermissionDenied(
                "Réservé aux utilisateurs de niveau Groupe."
            )

        from apps.credits.models import CreditApplication
        from apps.documents.models import Document
        from apps.tenants.models import Tenant
        from apps.workflow.models import ApprovalTask

        User = get_user_model()
        celery_info = _celery_metrics()
        soft_deleted = Document.including_deleted.filter(is_deleted=True).count()
        return Response(
            {
                "time": timezone.now().isoformat(),
                "tenants_active": Tenant.objects.filter(is_active=True).count(),
                "users_active": User.objects.filter(is_active=True).count(),
                "applications_total": CreditApplication.all_tenants.count(),
                "documents_total": Document.all_tenants.count(),
                "documents_soft_deleted": soft_deleted,
                "documents_bytes": Document.all_tenants.aggregate(t=Sum("size_bytes"))["t"]
                or 0,
                "approval_tasks_pending": ApprovalTask.all_tenants.filter(
                    status=ApprovalTask.Status.PENDING
                ).count(),
                "ged_quota_total": sum(
                    Tenant.objects.values_list("ged_quota_bytes", flat=True)
                ),
                "ged_used_total": sum(
                    Tenant.objects.values_list("ged_used_bytes", flat=True)
                ),
                "celery": celery_info,
            }
        )


class OpsStatusView(APIView):
    """État d'exploitation sans agrégats inter-filiales.

    Celery est une sonde d'infrastructure (pas un chiffre métier). Le
    compteur GED soft-delete est borné à la filiale de l'appelant, sauf
    pour un opérateur Groupe qui cible une filiale via ``X-Tenant-Id``.
    """

    permission_classes = [IsAuthenticated, MustChangePasswordGate]

    def get(self, request):
        if not _is_ops_operator(request.user):
            raise PermissionDenied("Réservé aux administrateurs.")

        from apps.documents.models import Document

        tenant_id = _request_tenant_id(request)
        deleted_qs = Document.including_deleted.filter(is_deleted=True)
        if tenant_id:
            deleted_qs = deleted_qs.filter(tenant_id=tenant_id)
        elif not _is_group_operator(request.user):
            deleted_qs = deleted_qs.none()

        return Response(
            {
                "time": timezone.now().isoformat(),
                "documents_soft_deleted": deleted_qs.count(),
                "celery": _celery_metrics(),
            }
        )


def _celery_metrics() -> dict:
    """Ping broker + longueur approximative des files Redis (si possible)."""
    out: dict = {"ok": False, "broker": "unknown", "queues": {}}
    # En DEBUG / sans workers, l'inspect Celery est trop coûteux → Redis only.
    if settings.DEBUG:
        out["inspect_skipped"] = True
    else:
        try:
            from celery import current_app

            inspector = current_app.control.inspect(timeout=0.3)
            ping = inspector.ping() if inspector else None
            out["ok"] = bool(ping)
            out["workers"] = list(ping.keys()) if ping else []
            out["broker"] = str(current_app.connection().as_uri())[:80]
        except Exception as exc:  # noqa: BLE001
            out["error"] = "unavailable" if not settings.DEBUG else str(exc)[:200]

    try:
        from django.conf import settings as dj_settings
        import redis

        url = getattr(dj_settings, "CELERY_BROKER_URL", "") or ""
        if url.startswith("redis"):
            client = redis.Redis.from_url(
                url, socket_connect_timeout=0.4, socket_timeout=0.4
            )
            for name in ("celery",):
                out["queues"][name] = int(client.llen(name) or 0)
            out["broker_ping"] = bool(client.ping())
            out["ok"] = out.get("ok") or bool(out.get("broker_ping"))
            out["broker"] = url.split("@")[-1][:80] if "@" in url else url[:80]
    except Exception:  # noqa: BLE001
        pass
    return out
