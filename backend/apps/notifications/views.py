from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet
import logging

from apps.common.permissions import MustChangePasswordGate, is_configuration_administrator
from apps.common.tenancy import get_current_tenant_id
from apps.common.viewsets import TenantContextMixin, TenantScopedReadOnlyViewSet
from apps.tenants.models import Tenant

from .mail import (
    check_smtp_tcp,
    normalize_smtp_host,
    normalize_smtp_security,
    resolve_from_email,
    send_email_for_tenant,
    tenant_has_smtp,
)
from .models import NotificationLog, TenantNotificationSettings
from .serializers import (
    NotificationLogSerializer,
    TenantNotificationSettingsSerializer,
)

logger = logging.getLogger("finflow")

TENANT_HEADER = "HTTP_X_TENANT_ID"


class NotificationLogViewSet(TenantScopedReadOnlyViewSet):
    queryset = NotificationLog.objects.all()
    serializer_class = NotificationLogSerializer
    filterset_fields = ["kind", "status"]
    search_fields = ["subject", "error_message"]


class TenantNotificationSettingsViewSet(TenantContextMixin, ReadOnlyModelViewSet):
    """
    Lecture / mise à jour des préférences e-mail de la filiale active.

    - GET  /api/v1/notification-settings/current/
    - PATCH /api/v1/notification-settings/current/
    - POST /api/v1/notification-settings/current/test/

    Hérite de TenantContextMixin : le JWT est authentifié dans `initial()`,
    puis le header X-Tenant-Id (groupe) ou user.tenant_id (filiale) est
    installé — le middleware Django ne voit pas encore l'utilisateur JWT.
    """

    serializer_class = TenantNotificationSettingsSerializer
    # Read access is decided by _can_view; settings writes and SMTP tests use
    # _can_manage in their actions. A class-level admin gate would block the
    # read-only permission checked by the UI and its API contract.
    permission_classes = [IsAuthenticated, MustChangePasswordGate]
    queryset = TenantNotificationSettings.objects.select_related("tenant").all()

    def _resolve_tenant(self, request):
        tenant_id = get_current_tenant_id()
        if not tenant_id:
            tenant_id = request.META.get(TENANT_HEADER) or None
        if not tenant_id and getattr(request.user, "tenant_id", None):
            tenant_id = request.user.tenant_id
        if not tenant_id:
            return None
        return Tenant.objects.filter(pk=tenant_id).first()

    def _can_manage(self, user) -> bool:
        return bool(
            is_configuration_administrator(user)
            or user.is_superuser
            or (getattr(user, "is_group_level", False) and user.is_staff)
            or user.has_perm("notifications.change_tenantnotificationsettings")
            or user.has_perm("tenants.change_tenant")
        )

    def _can_view(self, user) -> bool:
        return bool(
            self._can_manage(user)
            or user.has_perm("notifications.view_tenantnotificationsettings")
        )

    @action(detail=False, methods=["get", "patch"])
    def current(self, request):
        tenant = self._resolve_tenant(request)
        if tenant is None:
            return Response(
                {"detail": "Sélectionnez une filiale pour paramétrer les alertes."},
                status=400,
            )
        prefs = TenantNotificationSettings.for_tenant(tenant)
        if request.method == "GET":
            if not self._can_view(request.user):
                return Response({"detail": "Droit insuffisant."}, status=403)
            return Response(self.get_serializer(prefs).data)

        if not self._can_manage(request.user):
            return Response({"detail": "Droit insuffisant."}, status=403)

        serializer = self.get_serializer(prefs, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path="current/test")
    def test_email(self, request):
        """Envoie un e-mail de test avec la config SMTP de la filiale."""
        tenant = self._resolve_tenant(request)
        if tenant is None:
            return Response(
                {"detail": "Sélectionnez une filiale."},
                status=400,
            )
        if not self._can_manage(request.user):
            return Response({"detail": "Droit insuffisant."}, status=403)

        prefs = TenantNotificationSettings.for_tenant(tenant)
        to = (request.data.get("to") or request.user.email or "").strip()
        if not to:
            return Response(
                {"detail": "Indiquez une adresse destinataire (champ « to »)."},
                status=400,
            )

        if tenant_has_smtp(prefs):
            host = normalize_smtp_host(prefs.smtp_host)
            port, _tls, _ssl = normalize_smtp_security(
                prefs.smtp_port,
                bool(prefs.smtp_use_tls),
                bool(prefs.smtp_use_ssl),
                host=host,
            )
            unreachable = check_smtp_tcp(host, port, timeout=5)
            if unreachable:
                return Response(
                    {
                        "detail": "Échec d'envoi du test.",
                        "error": unreachable,
                        "hint": (
                            "Le serveur SMTP est injoignable depuis FIN_FLOW. "
                            "Vérifiez l'hôte (ex. smtp.gmail.com, pas gmail.com), "
                            "et que le pare-feu autorise les ports 587/465."
                        ),
                        "smtp_configured": True,
                        "smtp_host": host,
                        "smtp_port": port,
                    },
                    status=400,
                )

        try:
            send_email_for_tenant(
                tenant=tenant,
                prefs=prefs,
                subject=f"[FIN_FLOW] Test e-mail — {tenant.code}",
                text_body=(
                    f"Ceci est un e-mail de test pour la filiale {tenant.name}.\n"
                    f"Expéditeur effectif : {resolve_from_email(prefs, tenant=tenant)}\n"
                    f"SMTP filiale : {'oui' if tenant_has_smtp(prefs) else 'non (repli global)'}\n"
                ),
                html_body=(
                    f"<p>Ceci est un e-mail de test pour la filiale "
                    f"<strong>{tenant.name}</strong>.</p>"
                    f"<p>Expéditeur : <code>{resolve_from_email(prefs, tenant=tenant)}</code></p>"
                ),
                recipients=[to],
            )
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
            logger.exception("smtp_test_failed tenant=%s", tenant.code)
            hint = None
            low = err.lower()
            if (
                "10060" in low
                or "cannot connect to smtp" in low
                or "timed out" in low
                or "timeout" in low
                or "connection refused" in low
            ):
                hint = (
                    "Timeout réseau vers le serveur SMTP. Sur Windows, désactivez "
                    "temporairement Avast/Norton « Mail Shield » (ou Web Shield), "
                    "ou ajoutez une exclusion pour smtp.gmail.com ports 587/465. "
                    "Vérifiez aussi que le pare-feu n'bloque pas les sorties SMTP."
                )
            elif "unexpected_eof" in low or "ssl" in low or "certificate" in low:
                hint = (
                    "Erreur SSL : un antivirus (Avast Mail Shield) ou un proxy "
                    "injecte souvent un certificat auto-signé. Solutions : "
                    "1) désactiver temporairement le Mail Shield, "
                    "2) exporter la CA Avast dans backend/certs/ca-bundle.crt "
                    "puis rebuild, "
                    "3) en démo locale : SMTP_SSL_VERIFY=0 dans le .env / "
                    "docker-compose. Gmail : port 587 + TLS + mot de passe "
                    "d'application (16 caractères)."
                )
            elif (
                "authentication" in low
                or "username and password" in low
                or "badcredentials" in low
                or "5.7.8" in low
            ):
                hint = (
                    "Authentification refusée : pour Gmail, utilisez un "
                    "« mot de passe d'application » (pas le mot de passe du compte)."
                )
            return Response(
                {
                    "detail": "Échec d'envoi du test.",
                    "error": err or repr(exc),
                    "hint": hint,
                    "smtp_configured": tenant_has_smtp(prefs),
                    "smtp_port": prefs.smtp_port,
                    "smtp_use_tls": prefs.smtp_use_tls,
                    "smtp_use_ssl": prefs.smtp_use_ssl,
                },
                status=400,
            )
        return Response({
            "detail": f"E-mail de test envoyé à {to}.",
            "to": to,
            "from_email": resolve_from_email(prefs, tenant=tenant),
            "smtp_configured": tenant_has_smtp(prefs),
        })
