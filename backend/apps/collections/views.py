import csv
import io

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q
from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.common.list_filters import apply_gestionnaire, query_param
from apps.common.viewsets import TenantScopedViewSet
from apps.documents.models import Document, DocumentCategory
from apps.documents.serializers import DocumentSerializer

from .access import (
    filter_qs_by_visible_case,
    is_collection_officer,
    is_finflow_admin,
    require_authored_edit,
    require_case_operate,
    require_dialogue_edit,
    require_finflow_admin,
    scoped_collection_cases,
    scoped_loan_decisions,
)
from .dation_bridge import require_financial_ops, require_loan_financial_ops
from .models import (
    CollectionAction,
    CollectionCase,
    CollectionDialogueMessage,
    CollectionEscalationRule,
    CollectionTranche,
    LegalParty,
    LitigationCost,
    LitigationEvent,
    LitigationFile,
    LitigationSeizure,
    LoanRestructure,
    PaymentPromise,
    Repayment,
    WriteOff,
)
from .serializers import (
    CaseAssignSerializer,
    CaseNextActionSerializer,
    CaseReminderSerializer,
    CaseRestructureSerializer,
    CaseStageSerializer,
    CaseWriteOffSerializer,
    CollectionActionSerializer,
    CollectionCaseListSerializer,
    CollectionCaseSerializer,
    CollectionDialogueMessageSerializer,
    CollectionEscalationRuleSerializer,
    CollectionTrancheSerializer,
    DecisionCommentSerializer,
    LegalPartySerializer,
    LitigationCostCreateSerializer,
    LitigationCostSerializer,
    LitigationDocumentUploadSerializer,
    LitigationEventCreateSerializer,
    LitigationEventSerializer,
    LitigationFileSerializer,
    LitigationFileWriteSerializer,
    LitigationSeizureCreateSerializer,
    LitigationSeizureSerializer,
    LitigationUpsertSerializer,
    LoanRestructureSerializer,
    PaymentPromiseSerializer,
    RepaymentSerializer,
    WriteOffSerializer,
)
from .services import (
    CBS_REPAYMENT_DENIED,
    agent_dashboard,
    approve_restructure,
    approve_write_off,
    cancel_restructure,
    cancel_write_off,
    change_case_stage,
    create_litigation,
    ensure_default_escalation_rules,
    ensure_default_tranches,
    ensure_litigation_document_categories,
    litigation_documents,
    propose_restructure,
    propose_write_off,
    refresh_loan_overdue,
    reject_restructure,
    reject_write_off,
    replace_collection_tranches,
    send_collection_reminder,
    upcoming_hearings,
    upsert_litigation,
)

User = get_user_model()

_CLOSED_LITIGATION_STATUSES = (
    LitigationFile.Status.CLOSED,
    LitigationFile.Status.ABANDONED,
    LitigationFile.Status.SETTLED,
)


def _tenant_from_request(request):
    """Filiale courante : contexte X-Tenant-Id (groupe) ou user.tenant_id."""
    from apps.common.tenancy import get_current_tenant_id
    from apps.tenants.models import Tenant

    tenant_id = get_current_tenant_id() or getattr(
        request.user, "tenant_id", None
    )
    if not tenant_id:
        return None
    return Tenant.objects.filter(pk=tenant_id).first()


def _litigation_write_payload(validated_data: dict) -> dict:
    """Normalise le payload serializer → services create/upsert."""
    data = dict(validated_data)
    data.pop("litigation_id", None)
    data.pop("case", None)
    guarantees = data.pop("related_guarantee_ids", None)
    if guarantees is not None:
        data["related_guarantee_ids"] = [g.pk for g in guarantees]
    return data


class RepaymentViewSet(TenantScopedViewSet):
    queryset = Repayment.objects.select_related("loan", "created_by").all()
    serializer_class = RepaymentSerializer
    filterset_fields = ["loan"]
    search_fields = ["reference"]

    def get_queryset(self):
        return filter_qs_by_visible_case(
            super().get_queryset(),
            self.request.user,
            case_field="loan__collection_case",
        )

    def create(self, request, *args, **kwargs):
        raise ValidationError({"detail": CBS_REPAYMENT_DENIED})


class CollectionCaseViewSet(TenantScopedViewSet):
    queryset = CollectionCase.objects.select_related(
        "loan",
        "loan__application",
        "loan__application__client",
        "loan__application__agency",
        "loan__application__product",
        "assigned_to",
        "tranche",
    ).prefetch_related(
        "actions",
        "actions__created_by",
        "actions__updated_by",
        "actions__dialogue_messages",
        "actions__dialogue_messages__created_by",
        "promises",
        "promises__created_by",
        "dialogue_messages",
        "dialogue_messages__created_by",
        "stage_history",
        "stage_history__changed_by",
        "write_offs",
        "write_offs__approved_by",
        "write_offs__requested_by",
        "loan__restructures",
        "loan__restructures__applied_by",
        "loan__restructures__requested_by",
        "litigations__events",
        "litigations__events__performed_by",
        "litigations__costs",
        "litigations__costs__party",
        "litigations__seizures",
        "litigations__seizures__bailiff",
        "litigations__law_firm",
        "litigations__lawyer_party",
        "litigations__bailiff_party",
        "litigations__related_guarantees",
        "loan__installments",
        "loan__repayments",
        "loan__application__guarantees",
        "loan__application__dation_requests",
        "loan__application__surety_engagements",
        "loan__application__surety_engagements__surety",
    ).all()
    # Actions sensibles : pas le fallback HTTP→add_collectioncase.
    # Pilotage opérationnel (stade / prochaine action / relance) → change_collectioncase.
    action_perms = {
        "agent_dashboard_view": ["collections.view_collectioncase"],
        "hearings_agenda": ["collections.view_collectioncase"],
        "export_csv": ["collections.view_collectioncase"],
        "add_repayment": ["collections.add_repayment"],
        "refresh_cbs": ["collections.view_collectioncase"],
        "assign": ["collections.change_collectioncase"],
        "set_stage": ["collections.change_collectioncase"],
        "set_next_action_view": ["collections.change_collectioncase"],
        "send_reminder": ["collections.change_collectioncase"],
        "refresh_overdue": ["collections.change_collectioncase"],
        "import_cbs_portfolio": ["collections.view_collectioncase"],
        "restructure": ["collections.add_loanrestructure"],
        "preview_restructure": ["collections.add_loanrestructure"],
        "write_off": ["collections.add_writeoff"],
        # create/update contrôlés finement dans la méthode.
        "litigation": [],
        "litigation_events": ["collections.add_litigationevent"],
        "add_dialogue": ["collections.view_collectioncase"],
    }
    filterset_fields = ["stage", "par_class", "assigned_to", "tranche"]
    ordering_fields = [
        "days_overdue", "overdue_amount", "created_at", "next_action_date",
    ]
    search_fields = [
        "loan__application__reference",
        "loan__application__client__last_name",
        "loan__application__client__first_name",
        "loan__core_banking_reference",
    ]

    def get_serializer_class(self):
        if self.action == "list":
            return CollectionCaseListSerializer
        return CollectionCaseSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user or not user.is_authenticated:
            return qs.none()
        qs = scoped_collection_cases(qs, user)
        # TENANT : toute la filiale (déjà scopée par tenant)
        mine = self.request.query_params.get("mine")
        if mine in {"1", "true", "True"}:
            from .access import mine_collection_cases

            qs = mine_collection_cases(qs, user)
        unassigned = self.request.query_params.get("unassigned")
        if unassigned in {"1", "true", "True"}:
            qs = qs.filter(assigned_to__isnull=True)
        open_only = self.request.query_params.get("open")
        if open_only in {"1", "true", "True"}:
            qs = qs.exclude(stage=CollectionCase.Stage.CLOSED)
        followup_due = self.request.query_params.get("followup_due")
        if followup_due in {"1", "true", "True"}:
            from django.utils import timezone

            qs = qs.filter(
                next_action_date__isnull=False,
                next_action_date__lte=timezone.localdate(),
            )
        broken_promises = self.request.query_params.get("broken_promises")
        if broken_promises in {"1", "true", "True"}:
            qs = qs.filter(
                promises__status=PaymentPromise.Status.BROKEN,
            ).distinct()
        client = query_param(self.request, "client")
        if client:
            qs = qs.filter(loan__application__client_id=client)
        agency = query_param(self.request, "agency")
        if agency:
            qs = qs.filter(loan__application__agency_id=agency)
        product = query_param(self.request, "product")
        if product:
            qs = qs.filter(loan__application__product_id=product)
        owner_kind = query_param(self.request, "owner_kind")
        if owner_kind:
            qs = qs.filter(tranche__owner_kind=owner_kind)
        qs = apply_gestionnaire(
            qs,
            self.request,
            "loan__application__submitted_by_id",
            "loan__application__created_by_id",
        )
        if query_param(self.request, "cbs_error") in {"1", "true", "True"}:
            qs = qs.exclude(cbs_sync_error="")
        if self.action == "list":
            qs = qs.annotate(
                pending_promises_count=Count(
                    "promises",
                    filter=Q(promises__status=PaymentPromise.Status.PENDING),
                )
            )
            if not self.request.query_params.get("ordering"):
                qs = qs.order_by("-days_overdue", "-pk")
        return qs

    @action(detail=False, methods=["get"], url_path="agent-dashboard")
    def agent_dashboard_view(self, request):
        """Indicateurs portefeuille (mine) ou équipe / filiale (team)."""
        from apps.common.tenancy import get_current_tenant_id

        tenant_id = get_current_tenant_id() or getattr(
            request.user, "tenant_id", None
        )
        scope = request.query_params.get("scope", "mine")
        data = agent_dashboard(
            user=request.user, tenant_id=tenant_id, scope=scope
        )
        return Response(data)

    @action(detail=False, methods=["post"], url_path="refresh-overdue")
    def refresh_overdue(self, request):
        """Enqueue le recalcul des retards (Celery) — ne bloque pas le worker HTTP."""
        from apps.common.tenancy import get_current_tenant_id

        from .tasks import refresh_tenant_overdue_loans

        tenant_id = get_current_tenant_id() or getattr(
            request.user, "tenant_id", None
        )
        if not tenant_id:
            return Response(
                {"detail": "Sélectionnez une filiale."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not (
            is_finflow_admin(request.user) or is_collection_officer(request.user)
        ):
            raise PermissionDenied(
                "Recalcul CBS réservé au recouvrement et aux administrateurs."
            )
        # sync=1 réservé debug / petits volumes
        sync = str(request.query_params.get("sync", "")).lower() in (
            "1",
            "true",
            "yes",
        )
        if sync:
            result = refresh_tenant_overdue_loans(str(tenant_id))
            return Response(result)

        task = refresh_tenant_overdue_loans.delay(str(tenant_id))
        from apps.common.scoped import track_async_task

        track_async_task(task.id, request.user.id)
        return Response(
            {
                "detail": "Recalcul des retards lancé en arrière-plan.",
                "task_id": task.id,
                "status": "queued",
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=False, methods=["post"], url_path="import-cbs-portfolio")
    def import_cbs_portfolio(self, request):
        """Première constitution / relance : crédits CBS → dossiers + tranches."""
        from apps.common.tenancy import get_current_tenant_id
        from apps.corebanking.portfolio_import import (
            import_cbs_portfolio,
            loan_refs_from_upload,
        )
        from apps.corebanking.services import (
            CoreBankingError,
            resolve_active_connector,
        )
        from apps.corebanking.tasks import import_cbs_portfolio_task

        tenant_id = get_current_tenant_id() or getattr(
            request.user, "tenant_id", None
        )
        if not tenant_id:
            return Response(
                {"detail": "Sélectionnez une filiale."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        require_finflow_admin(request.user)
        try:
            connector = resolve_active_connector(tenant_id)
        except Exception as exc:  # noqa: BLE001
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
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
                    tenant_id,
                    connector=connector,
                    user=request.user,
                    loan_refs=loan_refs,
                )
            except CoreBankingError as exc:
                raise ValidationError({"detail": str(exc)}) from exc
            return Response(stats)

        task = import_cbs_portfolio_task.delay(
            str(tenant_id), str(connector.id), loan_refs
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

    @action(detail=False, methods=["get"], url_path="hearings-agenda")
    def hearings_agenda(self, request):
        """Agenda des prochaines audiences contentieux."""
        from apps.common.tenancy import get_current_tenant_id

        tenant_id = get_current_tenant_id() or getattr(
            request.user, "tenant_id", None
        )
        try:
            within_days = int(request.query_params.get("within_days", 30))
        except (TypeError, ValueError):
            within_days = 30
        try:
            limit = int(request.query_params.get("limit", 50))
        except (TypeError, ValueError):
            limit = 50
        return Response(
            upcoming_hearings(
                tenant_id=tenant_id,
                within_days=max(1, min(within_days, 365)),
                limit=max(1, min(limit, 200)),
                user=request.user,
            )
        )

    @action(detail=True, methods=["post"], url_path="refresh-cbs")
    def refresh_cbs(self, request, pk=None):
        """Relit l'impayé / le solde de ce prêt depuis le CBS."""
        case = self.get_object()
        if not (
            is_finflow_admin(request.user) or is_collection_officer(request.user)
        ):
            require_case_operate(request.user, case)
        refreshed = refresh_loan_overdue(case.loan)
        if refreshed is None:
            raise ValidationError({
                "detail": "Impossible de lire la situation CBS de ce prêt."
            })
        refreshed.refresh_from_db()
        if refreshed.cbs_sync_error:
            raise ValidationError({"detail": refreshed.cbs_sync_error})
        return Response(
            CollectionCaseSerializer(
                refreshed, context={"request": request}
            ).data
        )

    @action(detail=True, methods=["post"], url_path="repayments")
    def add_repayment(self, request, pk=None):
        """Les encaissements sont gérés par le CBS — saisie locale refusée."""
        raise ValidationError({"detail": CBS_REPAYMENT_DENIED})

    @action(detail=True, methods=["post"], url_path="assign")
    def assign(self, request, pk=None):
        """Affecte (ou retire) l'agent de recouvrement."""
        case = self.get_object()
        require_case_operate(request.user, case)
        serializer = CaseAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_id = serializer.validated_data.get("assigned_to")
        if user_id is None:
            case.assigned_to = None
        else:
            try:
                agent = User.objects.get(pk=user_id)
            except User.DoesNotExist as exc:
                raise ValidationError({
                    "assigned_to": "Utilisateur introuvable."
                }) from exc
            if agent.tenant_id and agent.tenant_id != case.tenant_id:
                raise ValidationError({
                    "assigned_to": "L'agent doit appartenir à la filiale."
                })
            case.assigned_to = agent
        case.save(update_fields=["assigned_to"])
        return Response(
            CollectionCaseSerializer(case, context={"request": request}).data
        )

    @action(detail=True, methods=["post"], url_path="set-stage")
    def set_stage(self, request, pk=None):
        """Change le stade du dossier (amiable / précontentieux / …)."""
        case = self.get_object()
        require_case_operate(request.user, case)
        serializer = CaseStageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        change_case_stage(
            case,
            serializer.validated_data["stage"],
            user=request.user,
            reason=serializer.validated_data.get("reason", ""),
            automatic=False,
        )
        case.refresh_from_db()
        return Response(
            CollectionCaseSerializer(case, context={"request": request}).data
        )

    @action(detail=True, methods=["post"], url_path="set-next-action")
    def set_next_action_view(self, request, pk=None):
        """Planifie la prochaine action / visite."""
        case = self.get_object()
        require_case_operate(request.user, case)
        serializer = CaseNextActionSerializer(
            data=request.data, context={"case": case}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        case.refresh_from_db()
        return Response(
            CollectionCaseSerializer(case, context={"request": request}).data
        )

    @action(detail=True, methods=["post"], url_path="preview-restructure")
    def preview_restructure(self, request, pk=None):
        """Calcule l'échéancier proposé sans enregistrer."""
        from .services import build_restructure_preview

        case = self.get_object()
        require_financial_ops(request.user, case)
        serializer = CaseRestructureSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data.pop("request_kind", None)
        data.pop("reason", None)
        try:
            preview = build_restructure_preview(case.loan, **data)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(preview)

    @action(detail=True, methods=["post"], url_path="restructure")
    def restructure(self, request, pk=None):
        """Enregistre une demande d'analyse de restructuration."""
        case = self.get_object()
        require_financial_ops(request.user, case)
        serializer = CaseRestructureSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        request_kind = data.pop(
            "request_kind", LoanRestructure.RequestKind.INTERNAL
        )
        try:
            propose_restructure(
                case.loan,
                user=request.user,
                origin=LoanRestructure.Origin.COLLECTION,
                request_kind=request_kind,
                case=case,
                **data,
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        case.refresh_from_db()
        return Response(
            CollectionCaseSerializer(case, context={"request": request}).data
        )

    @action(detail=True, methods=["post"], url_path="write-off")
    def write_off(self, request, pk=None):
        """Enregistre une demande de passage en perte."""
        case = self.get_object()
        require_financial_ops(request.user, case)
        serializer = CaseWriteOffSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            propose_write_off(
                case,
                user=request.user,
                **serializer.validated_data,
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        case.refresh_from_db()
        return Response(
            CollectionCaseSerializer(case, context={"request": request}).data
        )

    @action(detail=True, methods=["post"], url_path="send-reminder")
    def send_reminder(self, request, pk=None):
        """Envoie immédiatement une relance EMAIL ou SMS (force)."""
        case = self.get_object()
        require_case_operate(request.user, case)
        serializer = CaseReminderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = send_collection_reminder(
            case,
            channel=serializer.validated_data["channel"],
            force=True,
        )
        case.refresh_from_db()
        return Response({
            "reminder": result,
            "case": CollectionCaseSerializer(
                case, context={"request": request}
            ).data,
        })

    @action(detail=True, methods=["post", "put", "patch"], url_path="litigation")
    def litigation(self, request, pk=None):
        """Crée / met à jour une procédure contentieuse (optionnel : litigation_id)."""
        user = request.user
        if not user.is_superuser:
            has_add = user.has_perm("collections.add_litigationfile")
            has_change = user.has_perm("collections.change_litigationfile")
            if not (has_add or has_change):
                raise PermissionDenied(
                    "Droit insuffisant pour gérer le contentieux."
                )
        case = self.get_object()
        require_case_operate(request.user, case)
        serializer = LitigationUpsertSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        litigation_id = serializer.validated_data.get("litigation_id")
        if (
            not user.is_superuser
            and litigation_id
            and not user.has_perm("collections.change_litigationfile")
        ):
            raise PermissionDenied(
                "Droit insuffisant pour modifier une procédure contentieuse."
            )
        if (
            not user.is_superuser
            and not litigation_id
            and not user.has_perm("collections.add_litigationfile")
        ):
            raise PermissionDenied(
                "Droit insuffisant pour ouvrir une procédure contentieuse."
            )
        payload = _litigation_write_payload(serializer.validated_data)
        try:
            upsert_litigation(
                case, data=payload, litigation_id=litigation_id
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        case.refresh_from_db()
        return Response(
            CollectionCaseSerializer(case, context={"request": request}).data
        )

    @action(detail=True, methods=["post"], url_path="litigation-events")
    def litigation_events(self, request, pk=None):
        """Ajoute un événement à une procédure (optionnel : litigation_id)."""
        case = self.get_object()
        require_case_operate(request.user, case)
        serializer = LitigationEventCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        litigation_id = data.pop("litigation_id", None)
        lit = None
        if litigation_id:
            lit = LitigationFile.objects.filter(case=case, pk=litigation_id).first()
            if lit is None:
                raise ValidationError({
                    "litigation_id": "Dossier contentieux introuvable."
                })
        if lit is None:
            lit = (
                case.litigations.exclude(status__in=_CLOSED_LITIGATION_STATUSES)
                .order_by("-created_at")
                .first()
            )
        if lit is None:
            raise ValidationError(
                {
                    "detail": (
                        "Aucun dossier contentieux ouvert. "
                        "Ouvrez d'abord une procédure."
                    )
                }
            )
        event = LitigationEvent.objects.create(
            tenant_id=case.tenant_id,
            litigation=lit,
            **data,
        )
        if event.event_type == LitigationEvent.EventType.HEARING:
            lit.recompute_next_hearing()
        return Response(
            LitigationEventSerializer(event).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="dialogue")
    def add_dialogue(self, request, pk=None):
        """Message de dialogue (question / demande / recommandation)."""
        case = self.get_object()
        payload = request.data.copy()
        payload["case"] = str(case.id)
        serializer = CollectionDialogueMessageSerializer(
            data=payload,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(
            tenant_id=case.tenant_id,
            case=case,
            created_by=request.user,
            updated_by=request.user,
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="export")
    def export_csv(self, request):
        """Export CSV du portefeuille filtré (max 5000 lignes)."""
        qs = self.filter_queryset(self.get_queryset()).select_related(
            "loan__application__client",
            "loan__application__product",
            "assigned_to",
            "tranche",
        )[:5000]
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";")
        writer.writerow([
            "id",
            "reference",
            "client",
            "produit",
            "stade",
            "tranche",
            "par",
            "jours_retard",
            "montant_impaye",
            "prochaine_action",
            "type_action",
            "agent",
        ])
        for c in qs:
            app = getattr(c.loan, "application", None)
            client = getattr(app, "client", None) if app else None
            product = getattr(app, "product", None) if app else None
            agent = c.assigned_to
            writer.writerow([
                str(c.id),
                (app.reference or "") if app else "",
                client.display_name if client else "",
                product.label if product else "",
                c.stage,
                c.tranche.name if c.tranche_id else "",
                c.par_class,
                c.days_overdue,
                str(c.overdue_amount),
                c.next_action_date.isoformat() if c.next_action_date else "",
                c.next_action_type or "",
                (agent.get_full_name() or agent.username) if agent else "",
            ])
        response = HttpResponse(
            buffer.getvalue().encode("utf-8-sig"),
            content_type="text/csv; charset=utf-8",
        )
        response["Content-Disposition"] = (
            'attachment; filename="recouvrement.csv"'
        )
        return response


class CollectionActionViewSet(TenantScopedViewSet):
    queryset = CollectionAction.objects.select_related(
        "case", "created_by", "updated_by"
    ).all()
    serializer_class = CollectionActionSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filterset_fields = ["case", "action_type"]

    def get_queryset(self):
        return filter_qs_by_visible_case(super().get_queryset(), self.request.user)

    def perform_create(self, serializer):
        case = serializer.validated_data["case"]
        require_case_operate(self.request.user, case)
        super().perform_create(serializer)

    def perform_update(self, serializer):
        require_authored_edit(self.request.user, serializer.instance)
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        require_authored_edit(self.request.user, instance)
        super().perform_destroy(instance)


class PaymentPromiseViewSet(TenantScopedViewSet):
    queryset = PaymentPromise.objects.select_related("case", "created_by").all()
    serializer_class = PaymentPromiseSerializer
    filterset_fields = ["case", "status"]

    def get_queryset(self):
        return filter_qs_by_visible_case(super().get_queryset(), self.request.user)

    def perform_create(self, serializer):
        case = serializer.validated_data["case"]
        require_case_operate(self.request.user, case)
        super().perform_create(serializer)

    def perform_update(self, serializer):
        require_authored_edit(self.request.user, serializer.instance)
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        require_authored_edit(self.request.user, instance)
        super().perform_destroy(instance)


class CollectionDialogueMessageViewSet(TenantScopedViewSet):
    queryset = CollectionDialogueMessage.objects.select_related(
        "case", "action", "created_by", "updated_by"
    ).all()
    serializer_class = CollectionDialogueMessageSerializer
    filterset_fields = ["case", "action", "kind"]
    action_perms = {
        "create": ["collections.view_collectioncase"],
        "list": ["collections.view_collectioncase"],
        "retrieve": ["collections.view_collectioncase"],
        "update": ["collections.view_collectioncase"],
        "partial_update": ["collections.view_collectioncase"],
        "destroy": ["collections.view_collectioncase"],
    }

    def get_queryset(self):
        return filter_qs_by_visible_case(super().get_queryset(), self.request.user)

    def perform_create(self, serializer):
        case = serializer.validated_data["case"]
        visible = scoped_collection_cases(
            CollectionCase.objects.all(), self.request.user
        )
        if not visible.filter(pk=case.pk).exists():
            raise PermissionDenied("Dossier introuvable.")
        super().perform_create(serializer)

    def perform_update(self, serializer):
        require_dialogue_edit(self.request.user, serializer.instance)
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        require_dialogue_edit(self.request.user, instance)
        super().perform_destroy(instance)


class CollectionTrancheViewSet(TenantScopedViewSet):
    queryset = CollectionTranche.objects.all()
    serializer_class = CollectionTrancheSerializer
    filterset_fields = ["is_active", "owner_kind"]
    ordering_fields = ["position", "min_days_overdue"]
    action_perms = {
        "list": ["collections.view_collectiontranche"],
        "retrieve": ["collections.view_collectiontranche"],
        "replace": ["collections.change_collectiontranche"],
    }

    def list(self, request, *args, **kwargs):
        tenant = _tenant_from_request(request)
        if tenant is not None:
            ensure_default_tranches(tenant)
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        require_finflow_admin(self.request.user)
        super().perform_create(serializer)

    def perform_update(self, serializer):
        require_finflow_admin(self.request.user)
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        require_finflow_admin(self.request.user)
        super().perform_destroy(instance)

    @action(detail=False, methods=["post"], url_path="replace")
    def replace(self, request):
        tenant = _tenant_from_request(request)
        if tenant is None:
            return Response(
                {"detail": "Sélectionnez une filiale."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        require_finflow_admin(request.user)
        items = request.data.get("tranches")
        if items is None and isinstance(request.data, list):
            items = request.data
        if not isinstance(items, list):
            raise ValidationError(
                {"tranches": "Envoyez la liste complète des tranches."}
            )
        created = replace_collection_tranches(tenant=tenant, items=items)
        return Response(CollectionTrancheSerializer(created, many=True).data)


class CollectionEscalationRuleViewSet(TenantScopedViewSet):
    queryset = CollectionEscalationRule.objects.all()
    serializer_class = CollectionEscalationRuleSerializer
    filterset_fields = ["is_active", "target_stage"]
    ordering_fields = ["min_days_overdue"]

    def list(self, request, *args, **kwargs):
        tenant = _tenant_from_request(request)
        if tenant is not None:
            ensure_default_escalation_rules(tenant)
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        require_finflow_admin(self.request.user)
        super().perform_create(serializer)

    def perform_update(self, serializer):
        require_finflow_admin(self.request.user)
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        require_finflow_admin(self.request.user)
        super().perform_destroy(instance)


class LegalPartyViewSet(TenantScopedViewSet):
    queryset = LegalParty.objects.all()
    serializer_class = LegalPartySerializer
    filterset_fields = ["party_type", "is_active"]
    search_fields = ["name", "contact_name", "registration_no", "email", "phone"]
    ordering_fields = ["name", "party_type", "created_at"]


class LitigationFileViewSet(TenantScopedViewSet):
    queryset = LitigationFile.objects.select_related(
        "case",
        "case__loan",
        "case__loan__application",
        "law_firm",
        "lawyer_party",
        "bailiff_party",
    ).prefetch_related(
        "events",
        "events__performed_by",
        "costs",
        "costs__party",
        "seizures",
        "seizures__bailiff",
        "related_guarantees",
    ).all()
    serializer_class = LitigationFileSerializer
    # GET+POST partagés : entrée lecture, écriture vérifiée dans la méthode.
    action_perms = {
        "events": ["collections.view_litigationfile"],
        "seizures": ["collections.view_litigationfile"],
        "costs": ["collections.view_litigationfile"],
        "documents": ["collections.view_litigationfile"],
        "ensure_categories": ["collections.change_litigationfile"],
    }
    filterset_fields = ["case", "status", "action_type", "law_firm"]
    search_fields = ["title", "case_reference", "court_name", "lawyer", "bailiff"]
    ordering_fields = ["hearing_date", "filing_date", "created_at", "status"]

    @staticmethod
    def _require_perm(user, codename, message):
        if user.is_superuser or user.has_perm(codename):
            return
        raise PermissionDenied(message)

    def get_queryset(self):
        return filter_qs_by_visible_case(super().get_queryset(), self.request.user)

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return LitigationFileWriteSerializer
        return LitigationFileSerializer

    def create(self, request, *args, **kwargs):
        serializer = LitigationFileWriteSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        case = serializer.validated_data.get("case")
        if case is None:
            raise ValidationError({"case": "Dossier de recouvrement requis."})
        require_case_operate(request.user, case)
        payload = _litigation_write_payload(serializer.validated_data)
        try:
            lit = create_litigation(case, data=payload)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(
            LitigationFileSerializer(lit, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        lit = self.get_object()
        require_case_operate(request.user, lit.case)
        serializer = LitigationFileWriteSerializer(
            data=request.data,
            partial=partial,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        payload = _litigation_write_payload(serializer.validated_data)
        try:
            lit = upsert_litigation(
                lit.case, data=payload, litigation_id=lit.pk
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(
            LitigationFileSerializer(lit, context={"request": request}).data
        )

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @action(detail=True, methods=["get", "post"], url_path="events")
    def events(self, request, pk=None):
        lit = self.get_object()
        if request.method == "GET":
            qs = lit.events.select_related("performed_by").all()
            return Response(LitigationEventSerializer(qs, many=True).data)
        require_case_operate(request.user, lit.case)
        self._require_perm(
            request.user,
            "collections.add_litigationevent",
            "Droit insuffisant pour ajouter un événement contentieux.",
        )
        serializer = LitigationEventCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data.pop("litigation_id", None)
        event = LitigationEvent.objects.create(
            tenant_id=lit.tenant_id,
            litigation=lit,
            **data,
        )
        if event.event_type == LitigationEvent.EventType.HEARING:
            lit.recompute_next_hearing()
        return Response(
            LitigationEventSerializer(event).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get", "post"], url_path="seizures")
    def seizures(self, request, pk=None):
        lit = self.get_object()
        if request.method == "GET":
            qs = lit.seizures.select_related("bailiff", "guarantee").all()
            return Response(LitigationSeizureSerializer(qs, many=True).data)
        require_case_operate(request.user, lit.case)
        self._require_perm(
            request.user,
            "collections.add_litigationseizure",
            "Droit insuffisant pour enregistrer une saisie.",
        )
        serializer = LitigationSeizureCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        seizure = LitigationSeizure.objects.create(
            tenant_id=lit.tenant_id,
            litigation=lit,
            **serializer.validated_data,
        )
        return Response(
            LitigationSeizureSerializer(seizure).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get", "post"], url_path="costs")
    def costs(self, request, pk=None):
        lit = self.get_object()
        if request.method == "GET":
            qs = lit.costs.select_related("party").all()
            return Response(LitigationCostSerializer(qs, many=True).data)
        require_case_operate(request.user, lit.case)
        self._require_perm(
            request.user,
            "collections.add_litigationcost",
            "Droit insuffisant pour enregistrer un frais contentieux.",
        )
        serializer = LitigationCostCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cost = LitigationCost.objects.create(
            tenant_id=lit.tenant_id,
            litigation=lit,
            **serializer.validated_data,
        )
        return Response(
            LitigationCostSerializer(cost).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get", "post"], url_path="documents")
    def documents(self, request, pk=None):
        lit = self.get_object()
        if request.method == "GET":
            docs = litigation_documents(lit).select_related(
                "category", "uploaded_by"
            )
            return Response(DocumentSerializer(docs, many=True).data)

        require_case_operate(request.user, lit.case)
        self._require_perm(
            request.user,
            "collections.change_litigationfile",
            "Droit insuffisant pour joindre une pièce au contentieux.",
        )
        ensure_litigation_document_categories(lit.tenant)
        serializer = LitigationDocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]
        name = (serializer.validated_data.get("name") or "").strip() or upload.name
        category_code = (
            serializer.validated_data.get("category") or ""
        ).strip() or "LIT_OTHER"
        category = DocumentCategory.objects.filter(
            tenant_id=lit.tenant_id, code=category_code, is_active=True
        ).first()
        if category is None:
            category = DocumentCategory.objects.filter(
                tenant_id=lit.tenant_id, code="LIT_OTHER"
            ).first()
        if category is None:
            raise ValidationError({
                "category": "Catégorie documentaire introuvable."
            })
        ct = ContentType.objects.get_for_model(LitigationFile)
        doc = Document(
            tenant_id=lit.tenant_id,
            category=category,
            name=name,
            file=upload,
            content_type=ct,
            object_id=lit.id,
            uploaded_by=request.user,
        )
        doc.mime_type = getattr(upload, "content_type", "") or ""
        doc.save()
        doc.compute_hash()
        doc.save(update_fields=["mime_type", "sha256", "size_bytes"])
        from apps.documents.quotas import bump_ged_usage

        bump_ged_usage(doc.tenant_id, doc.size_bytes)
        return Response(
            DocumentSerializer(doc).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="ensure-categories")
    def ensure_categories(self, request, pk=None):
        lit = self.get_object()
        created = ensure_litigation_document_categories(lit.tenant)
        return Response({"created": created})


def _decision_error(exc):
    if isinstance(exc, PermissionDenied):
        raise exc
    raise ValidationError({"detail": str(exc)}) from exc


class LoanRestructureViewSet(TenantScopedViewSet):
    queryset = LoanRestructure.objects.select_related(
        "loan", "case", "requested_by", "applied_by"
    ).all()
    serializer_class = LoanRestructureSerializer
    http_method_names = ["get", "post", "head", "options"]
    action_perms = {
        "approve": ["collections.change_loanrestructure"],
        "reject": ["collections.change_loanrestructure"],
        "cancel": [],
    }

    def get_queryset(self):
        return scoped_loan_decisions(super().get_queryset(), self.request.user)

    def create(self, request, *args, **kwargs):
        raise PermissionDenied("Utilisez la fiche prêt ou le dossier de recouvrement.")

    def _record(self):
        return self.get_object()

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        serializer = DecisionCommentSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        record = self._record()
        require_loan_financial_ops(record.loan, user=request.user)
        try:
            record = approve_restructure(
                self._record(),
                user=request.user,
                comment=serializer.validated_data.get("comment") or "",
            )
        except ValueError as exc:
            _decision_error(exc)
        return Response(LoanRestructureSerializer(record).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        serializer = DecisionCommentSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        try:
            record = reject_restructure(
                self._record(),
                user=request.user,
                comment=serializer.validated_data.get("comment") or "",
            )
        except ValueError as exc:
            _decision_error(exc)
        return Response(LoanRestructureSerializer(record).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        try:
            record = cancel_restructure(self._record(), user=request.user)
        except ValueError as exc:
            _decision_error(exc)
        return Response(LoanRestructureSerializer(record).data)


class WriteOffViewSet(TenantScopedViewSet):
    queryset = WriteOff.objects.select_related(
        "loan", "case", "requested_by", "approved_by"
    ).all()
    serializer_class = WriteOffSerializer
    http_method_names = ["get", "post", "head", "options"]
    action_perms = {
        "approve": ["collections.change_writeoff"],
        "reject": ["collections.change_writeoff"],
        "cancel": [],
    }

    def get_queryset(self):
        return scoped_loan_decisions(super().get_queryset(), self.request.user)

    def create(self, request, *args, **kwargs):
        raise PermissionDenied("Utilisez le dossier de recouvrement.")

    def _record(self):
        return self.get_object()

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        serializer = DecisionCommentSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        record = self._record()
        require_loan_financial_ops(record.loan, user=request.user)
        try:
            record = approve_write_off(
                self._record(),
                user=request.user,
                comment=serializer.validated_data.get("comment") or "",
            )
        except ValueError as exc:
            _decision_error(exc)
        return Response(WriteOffSerializer(record).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        serializer = DecisionCommentSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        try:
            record = reject_write_off(
                self._record(),
                user=request.user,
                comment=serializer.validated_data.get("comment") or "",
            )
        except ValueError as exc:
            _decision_error(exc)
        return Response(WriteOffSerializer(record).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        try:
            record = cancel_write_off(self._record(), user=request.user)
        except ValueError as exc:
            _decision_error(exc)
        return Response(WriteOffSerializer(record).data)

