from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.collections.access import require_finflow_admin

from apps.common.viewsets import TenantScopedReadOnlyViewSet, TenantScopedViewSet

from .models import CoreBankingConnector, IntegrationLog
from .portfolio_import import (
    enqueue_initial_portfolio_import,
    import_cbs_portfolio,
    is_live_cbs_connector,
    loan_refs_from_upload,
)
from .ref_sync import SYNC_SCOPES, sync_cbs_referentials
from .serializers import (
    CoreBankingConnectorSerializer,
    IntegrationLogSerializer,
)
from .services import CoreBankingError, probe_credit_situation, send_operation


class CoreBankingConnectorViewSet(TenantScopedViewSet):
    queryset = CoreBankingConnector.objects.all()
    serializer_class = CoreBankingConnectorSerializer
    action_perms = {
        "test_operation": ["corebanking.change_corebankingconnector"],
        "import_portfolio": ["corebanking.change_corebankingconnector"],
        "sync_referentials": ["corebanking.change_corebankingconnector"],
        "probe_situation": ["corebanking.view_corebankingconnector"],
    }
    filterset_fields = ["protocol", "is_active"]
    search_fields = ["name"]

    def get_queryset(self):
        return super().get_queryset().order_by("name", "id")

    def perform_create(self, serializer):
        super().perform_create(serializer)
        if is_live_cbs_connector(serializer.instance):
            enqueue_initial_portfolio_import(serializer.instance)

    def perform_update(self, serializer):
        previous = self.get_object()
        was_live = is_live_cbs_connector(previous)
        extra = {}
        fields = self._model_fields(serializer)
        if "updated_by" in fields:
            extra["updated_by"] = self.request.user
        serializer.save(**extra)
        if not was_live and is_live_cbs_connector(serializer.instance):
            enqueue_initial_portfolio_import(serializer.instance)

    @action(detail=True, methods=["post"])
    def test_operation(self, request, pk=None):
        """Envoie une opération de test au connecteur (journalisée)."""
        connector = self.get_object()
        operation = request.data.get("operation", "PING")
        if str(operation).strip().upper() == "SUBMIT_CREDIT":
            raise ValidationError("La création d'un crédit doit être transmise depuis le dossier après autorisation de mise en place.")
        payload = request.data.get("payload", {})
        log = send_operation(connector, operation, payload)
        return Response(IntegrationLogSerializer(log).data)

    @action(detail=False, methods=["post"], url_path="probe-situation")
    def probe_situation(self, request):
        """
        Vérification admin ``crd/situation`` :
        body ``{ refDemande, codeAdherent }`` → réponse classée pour l'UI.
        """
        import logging
        from decimal import Decimal

        from apps.common.tenancy import get_current_tenant_id

        require_finflow_admin(request.user)
        ref = str(
            request.data.get("refDemande") or request.data.get("ref_demande") or ""
        ).strip()
        code = str(
            request.data.get("codeAdherent")
            or request.data.get("code_adherent")
            or ""
        ).strip()
        if not ref:
            raise ValidationError({"refDemande": "Obligatoire."})
        if not code:
            raise ValidationError({"codeAdherent": "Obligatoire."})

        logger = logging.getLogger("finflow")
        tenant_id = get_current_tenant_id()
        try:
            result = probe_credit_situation(
                tenant_id,
                ref_demande=ref,
                code_adherent=code,
            )
        except CoreBankingError as exc:
            logger.warning(
                "Probe situation CBS ref=%s code=%s : %s",
                ref,
                code,
                exc,
                exc_info=True,
            )
            raise ValidationError({"detail": str(exc)}) from exc

        def _jsonable(value):
            if isinstance(value, Decimal):
                return str(value)
            if isinstance(value, dict):
                return {k: _jsonable(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_jsonable(v) for v in value]
            return value

        return Response(_jsonable(result))

    @action(detail=True, methods=["post"], url_path="sync-referentials")
    def sync_referentials(self, request, pk=None):
        """Importe les référentiels Perfect (ref/*) dans FinFlow."""
        require_finflow_admin(request.user)
        connector = self.get_object()
        scopes = request.data.get("scopes")
        if scopes is not None and not isinstance(scopes, (list, tuple)):
            raise ValidationError(
                {"scopes": f"Liste attendue parmi : {', '.join(SYNC_SCOPES)}."}
            )
        try:
            report = sync_cbs_referentials(
                connector.tenant_id,
                connector=connector,
                scopes=scopes,
            )
        except CoreBankingError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(report)

    @action(detail=True, methods=["post"], url_path="import-portfolio")
    def import_portfolio(self, request, pk=None):
        """Importe les crédits CBS et constitue les dossiers de recouvrement."""
        require_finflow_admin(request.user)
        connector = self.get_object()
        upload = request.FILES.get("file") or request.FILES.get("fichier")
        loan_refs = loan_refs_from_upload(upload) if upload else None
        sync = str(request.query_params.get("sync", "")).lower() in (
            "1",
            "true",
            "yes",
        )
        if sync:
            try:
                stats = import_cbs_portfolio(
                    connector.tenant_id,
                    connector=connector,
                    user=request.user,
                    loan_refs=loan_refs,
                )
            except CoreBankingError as exc:
                raise ValidationError({"detail": str(exc)}) from exc
            return Response(stats)

        from .tasks import import_cbs_portfolio_task

        task = import_cbs_portfolio_task.delay(
            str(connector.tenant_id), str(connector.id), loan_refs
        )
        from apps.common.scoped import track_async_task

        track_async_task(task.id, request.user.id)
        return Response(
            {
                "detail": (
                    "Import des crédits CBS lancé : les dossiers de "
                    "recouvrement seront classés par tranche."
                ),
                "task_id": task.id,
                "status": "queued",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class IntegrationLogViewSet(TenantScopedReadOnlyViewSet):
    queryset = IntegrationLog.objects.select_related("connector").all()
    serializer_class = IntegrationLogSerializer
    action_perms = {
        "retry": ["corebanking.change_integrationlog"],
    }
    filterset_fields = ["connector", "status", "direction", "operation"]
    search_fields = ["operation", "external_reference", "idempotency_key"]
    ordering_fields = ["created_at", "status", "operation"]
    ordering = ["-created_at"]

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        """Rejoue une opération en échec."""
        log = self.get_object()
        if log.operation == "SUBMIT_CREDIT":
            raise ValidationError("Reprenez la mise en place depuis le dossier avec un contrôle final et une autorisation à jour. Le rejeu générique d'une création de crédit est interdit.")
        if log.status not in (IntegrationLog.Status.FAILED, IntegrationLog.Status.RETRY):
            raise ValidationError("Seule une opération en échec peut être rejouée.")
        new_log = send_operation(
            log.connector, log.operation, log.request_payload, log.idempotency_key
        )
        return Response(IntegrationLogSerializer(new_log).data)
