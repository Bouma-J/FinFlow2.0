from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.common.list_filters import query_param
from apps.common.scoped import get_for_tenant
from apps.common.tenancy import get_current_tenant_id
from apps.common.viewsets import AgencyScopedViewSet, TenantScopedViewSet
from apps.clients.models import Client
from apps.workflow.models import WorkflowInstance

from .models import (
    DationAsset,
    DationRequest,
    Guarantee,
    GuaranteeFormalizationRequest,
    GuaranteeMovement,
    GuaranteeReleaseRequest,
)

from .formalization_services import (
    add_formalization_fee,
    advance_legal_stage,
    cancel_formalization_request,
    complete_formalization_request,
    ensure_formalization_document_categories,
    formalization_documents,
    initiate_formalization_request,
    remove_formalization_fee,
    start_formalization_progress,
    submit_formalization_request,
    update_formalization_request,
)
from .process_services import (
    ProcessError,
    cbs_block_message,
    add_dation_asset,
    add_dation_fee,
    add_release_fee,
    cancel_dation_request,
    cancel_release_request,
    complete_dation_request,
    complete_release_request,
    dation_documents,
    ensure_dation_document_categories,
    ensure_release_document_categories,
    generate_release_acte,
    initiate_dation_request,
    initiate_release_request,
    preview_dation_cbs,
    refresh_dation_cbs,
    refresh_release_cbs,
    release_client_context,
    release_documents,
    remove_dation_asset,
    remove_dation_fee,
    remove_release_fee,
    submit_dation_request,
    submit_release_request,
    update_dation_request,
    update_release_request,
    upload_release_acte_signed,
    user_can_deposit_release_acte,
)
from .serializers import (
    DationAssetSerializer,
    DationDocumentUploadSerializer,
    DationFeeSerializer,
    DationRequestSerializer,
    FormalizationDocumentUploadSerializer,
    FormalizationFeeSerializer,
    GuaranteeFormalizationRequestSerializer,
    GuaranteeListSerializer,
    GuaranteeMovementSerializer,
    GuaranteeReleaseRequestSerializer,
    GuaranteeSerializer,
    ReleaseDocumentUploadSerializer,
    ReleaseFeeSerializer,
)

# Correspondance entre le type de mouvement et le nouveau statut de la garantie
_MOVEMENT_STATUS = {
    GuaranteeMovement.MovementType.RELEASE: Guarantee.Status.RELEASED,
    GuaranteeMovement.MovementType.REALIZATION: Guarantee.Status.REALIZED,
    GuaranteeMovement.MovementType.TRANSFER: Guarantee.Status.TRANSFERRED,
}


class GuaranteeViewSet(AgencyScopedViewSet):
    queryset = Guarantee.objects.select_related(
        "client",
        "application",
        "application__loan",
        "application__loan__collection_case",
        "agency",
        "surety",
        "renewed_from",
    ).all()
    serializer_class = GuaranteeSerializer
    action_perms = {
        "add_movement": ["guarantees.change_guarantee"],
        "initiate_release": ["guarantees.initiate_guaranteereleaserequest"],
        "initiate_formalization": [
            "guarantees.initiate_guaranteeformalizationrequest"
        ],
    }
    filterset_fields = ["guarantee_type", "status", "client", "application", "is_insured", "agency"]
    search_fields = [
        "reference",
        "description",
        "owners",
        "client__last_name",
        "client__first_name",
        "client__company_name",
        "client__reference",
    ]

    def get_serializer_class(self):
        if self.action == "list":
            return GuaranteeListSerializer
        return GuaranteeSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        formalized = query_param(self.request, "formalized")
        if formalized == "1":
            qs = qs.exclude(formalized_at__isnull=True)
        elif formalized == "0":
            qs = qs.filter(formalized_at__isnull=True)
        if self.action == "list":
            return qs
        return qs.select_related("surety").prefetch_related(
            "movements", "photos", "jewelry_items", "documents",
        )

    @staticmethod
    def _assert_application_allows_collateral(application, user):
        from apps.credits.access import can_attach_collateral

        if application is None:
            return
        if not can_attach_collateral(application, user):
            raise ValidationError(
                "Impossible de rattacher ou modifier une garantie sur un "
                f"dossier « {application.get_status_display()} »."
            )

    def perform_create(self, serializer):
        application = serializer.validated_data.get("application")
        self._assert_application_allows_collateral(
            application, self.request.user
        )
        super().perform_create(serializer)

    def perform_update(self, serializer):
        from .busy import guarantee_busy

        application = serializer.validated_data.get(
            "application", serializer.instance.application
        )
        self._assert_application_allows_collateral(
            application, self.request.user
        )
        busy = guarantee_busy(serializer.instance)
        if busy:
            raise ValidationError({"detail": busy["message"]})
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        from .busy import guarantee_busy

        busy = guarantee_busy(instance)
        if busy:
            raise ValidationError({"detail": busy["message"]})
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def add_movement(self, request, pk=None):
        """Enregistre un mouvement et met à jour l'état de la garantie."""
        from .busy import guarantee_busy

        guarantee = self.get_object()
        serializer = GuaranteeMovementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        movement_type = serializer.validated_data.get("movement_type")
        if movement_type in _MOVEMENT_STATUS:
            busy = guarantee_busy(guarantee)
            if busy:
                raise ValidationError({"detail": busy["message"]})
        with transaction.atomic():
            movement = serializer.save(guarantee=guarantee)
            if movement.movement_type == GuaranteeMovement.MovementType.REVALUATION:
                if movement.value is not None:
                    guarantee.current_value = movement.value
                    guarantee.last_valuation_date = movement.movement_date
            new_status = _MOVEMENT_STATUS.get(movement.movement_type)
            if new_status:
                guarantee.status = new_status
            guarantee.save()
        return Response(GuaranteeSerializer(guarantee).data)

    @action(detail=True, methods=["post"], url_path="initiate-release")
    def initiate_release(self, request, pk=None):
        """Démarre une main levée (contrôle CBS strict : prêt soldé)."""
        if not (
            request.user.is_superuser
            or request.user.has_perm("guarantees.initiate_guaranteereleaserequest")
        ):
            raise PermissionDenied(
                "Vous n'avez pas le droit d'initier une main levée."
            )
        guarantee = self.get_object()
        try:
            req = initiate_release_request(
                guarantee=guarantee,
                user=request.user,
                comment=request.data.get("comment", ""),
                cbs_loan_reference=request.data.get("cbs_loan_reference", ""),
                as_draft=True,
            )
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(GuaranteeReleaseRequestSerializer(req).data)

    @action(detail=True, methods=["post"], url_path="initiate-formalization")
    def initiate_formalization(self, request, pk=None):
        """Démarre une formalisation (ne bloque pas la mise en place)."""
        if not (
            request.user.is_superuser
            or request.user.has_perm(
                "guarantees.initiate_guaranteeformalizationrequest"
            )
        ):
            raise PermissionDenied(
                "Vous n'avez pas le droit d'initier une formalisation."
            )
        guarantee = self.get_object()
        fees = request.data.get("fees") or []
        if fees and not isinstance(fees, list):
            raise ValidationError({"fees": "Liste attendue."})
        try:
            req = initiate_formalization_request(
                guarantee=guarantee,
                user=request.user,
                comment=request.data.get("comment", ""),
                notary_name=request.data.get("notary_name", ""),
                notary_reference=request.data.get("notary_reference", ""),
                fees=fees,
                as_draft=True,
            )
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(GuaranteeFormalizationRequestSerializer(req).data)


class GuaranteeMovementViewSet(TenantScopedViewSet):
    queryset = GuaranteeMovement.objects.select_related("guarantee").all()
    serializer_class = GuaranteeMovementSerializer
    filterset_fields = ["guarantee", "movement_type"]


class GuaranteeReleaseRequestViewSet(TenantScopedViewSet):
    queryset = GuaranteeReleaseRequest.objects.select_related(
        "guarantee", "guarantee__client", "application", "loan", "agency"
    ).prefetch_related("fees").all()
    serializer_class = GuaranteeReleaseRequestSerializer
    action_perms = {
        "create": ["guarantees.initiate_guaranteereleaserequest"],
        "client_context": ["guarantees.initiate_guaranteereleaserequest"],
        "retry_cbs": ["guarantees.initiate_guaranteereleaserequest"],
        "submit": ["guarantees.initiate_guaranteereleaserequest"],
        "cancel": ["guarantees.initiate_guaranteereleaserequest"],
        "refresh_cbs": ["guarantees.initiate_guaranteereleaserequest"],
        "add_fee": ["guarantees.initiate_guaranteereleaserequest"],
        "remove_fee": ["guarantees.initiate_guaranteereleaserequest"],
        "update_draft": ["guarantees.initiate_guaranteereleaserequest"],
        "generate_acte": ["guarantees.initiate_guaranteereleaserequest"],
        # Initiateur ou approbateur du circuit — contrôle dans la méthode.
        "upload_acte_signe": [],
    }
    action_any_perms = {
        "list": [
            "guarantees.view_guaranteereleaserequest",
            "guarantees.initiate_guaranteereleaserequest",
        ],
        "retrieve": [
            "guarantees.view_guaranteereleaserequest",
            "guarantees.initiate_guaranteereleaserequest",
        ],
        "workflow": [
            "guarantees.view_guaranteereleaserequest",
            "guarantees.initiate_guaranteereleaserequest",
        ],
    }
    action_method_any_perms = {
        "documents": {
            "GET": [
                "guarantees.view_guaranteereleaserequest",
                "guarantees.initiate_guaranteereleaserequest",
            ],
        },
    }
    action_method_perms = {
        "documents": {
            "POST": ["guarantees.initiate_guaranteereleaserequest"],
        },
    }
    filterset_fields = ["status", "guarantee", "application", "agency"]
    search_fields = [
        "reference",
        "cbs_loan_reference",
        "cbs_client_id",
        "comment",
        "guarantee__client__last_name",
        "guarantee__client__first_name",
        "guarantee__client__company_name",
    ]
    http_method_names = ["get", "head", "options", "post"]

    def get_queryset(self):
        qs = super().get_queryset()
        client = query_param(self.request, "client")
        if client:
            qs = qs.filter(guarantee__client_id=client)
        return qs

    def _can_initiate(self, user):
        return user.is_superuser or user.has_perm(
            "guarantees.initiate_guaranteereleaserequest"
        )

    def _can_deposit_acte(self, user, req):
        return user_can_deposit_release_acte(user, req)

    @action(detail=False, methods=["get"], url_path="client-context")
    def client_context(self, request):
        if not self._can_initiate(request.user):
            raise PermissionDenied(
                "Vous n'avez pas le droit d'initier une main levée."
            )
        client_id = request.query_params.get("client")
        if not client_id:
            raise ValidationError({"client": "Obligatoire."})
        client = get_for_tenant(Client, client_id, error_field="client")
        try:
            data = release_client_context(
                client=client,
                tenant_id=get_current_tenant_id()
                or getattr(request.user, "tenant_id", None)
                or client.tenant_id,
            )
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(data)

    def create(self, request, *args, **kwargs):
        if not self._can_initiate(request.user):
            raise PermissionDenied(
                "Vous n'avez pas le droit d'initier une main levée."
            )
        guarantee_id = request.data.get("guarantee")
        if not guarantee_id:
            raise ValidationError({"guarantee": "Obligatoire."})
        guarantee = get_for_tenant(Guarantee, guarantee_id, error_field="guarantee")

        loan = None
        loan_id = request.data.get("loan")
        if loan_id:
            from apps.credits.models import Loan

            loan = get_for_tenant(Loan, loan_id, error_field="loan")

        fees = request.data.get("fees") or []
        if fees and not isinstance(fees, list):
            raise ValidationError({"fees": "Liste attendue."})

        as_draft_raw = request.data.get("as_draft", True)
        if isinstance(as_draft_raw, str):
            as_draft = as_draft_raw.strip().lower() not in {"0", "false", "no"}
        else:
            as_draft = bool(as_draft_raw)

        try:
            req = initiate_release_request(
                guarantee=guarantee,
                user=request.user,
                comment=request.data.get("comment", ""),
                cbs_loan_reference=request.data.get("cbs_loan_reference", ""),
                loan=loan,
                request_date=request.data.get("request_date") or None,
                release_fees=request.data.get("release_fees"),
                cbs_client_id=request.data.get("cbs_client_id", ""),
                fees=fees,
                as_draft=as_draft,
            )
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(GuaranteeReleaseRequestSerializer(req).data, status=201)

    @action(detail=True, methods=["post"], url_path="update-draft")
    def update_draft(self, request, pk=None):
        if not self._can_initiate(request.user):
            raise PermissionDenied()
        req = self.get_object()
        loan = None
        kwargs = {
            "user": request.user,
            "comment": request.data.get("comment"),
            "request_date": request.data.get("request_date"),
            "cbs_loan_reference": request.data.get("cbs_loan_reference"),
        }
        if "loan" in request.data:
            loan_id = request.data.get("loan")
            if loan_id:
                from apps.credits.models import Loan

                loan = get_for_tenant(Loan, loan_id, error_field="loan")
            kwargs["loan"] = loan
        try:
            updated = update_release_request(req, **kwargs)
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(GuaranteeReleaseRequestSerializer(updated).data)

    @action(detail=True, methods=["post"], url_path="add-fee")
    def add_fee(self, request, pk=None):
        if not self._can_initiate(request.user):
            raise PermissionDenied()
        req = self.get_object()
        try:
            fee = add_release_fee(req, request.data, user=request.user)
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(
            {
                "fee": ReleaseFeeSerializer(fee).data,
                "release": GuaranteeReleaseRequestSerializer(req).data,
            },
            status=201,
        )

    @action(
        detail=True,
        methods=["post"],
        url_path=r"remove-fee/(?P<fee_id>[^/.]+)",
    )
    def remove_fee(self, request, pk=None, fee_id=None):
        if not self._can_initiate(request.user):
            raise PermissionDenied()
        req = self.get_object()
        try:
            updated = remove_release_fee(req, fee_id, user=request.user)
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(GuaranteeReleaseRequestSerializer(updated).data)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        if not self._can_initiate(request.user):
            raise PermissionDenied()
        req = self.get_object()
        try:
            updated = submit_release_request(req, user=request.user)
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(GuaranteeReleaseRequestSerializer(updated).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        if not self._can_initiate(request.user):
            raise PermissionDenied()
        req = self.get_object()
        try:
            updated = cancel_release_request(
                req,
                user=request.user,
                comment=request.data.get("comment", ""),
            )
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(GuaranteeReleaseRequestSerializer(updated).data)

    @action(detail=True, methods=["post"], url_path="refresh-cbs")
    def refresh_cbs(self, request, pk=None):
        if not self._can_initiate(request.user):
            raise PermissionDenied()
        req = self.get_object()
        try:
            updated = refresh_release_cbs(req, user=request.user)
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(GuaranteeReleaseRequestSerializer(updated).data)

    @action(detail=True, methods=["post"], url_path="generate-acte")
    def generate_acte(self, request, pk=None):
        if not self._can_initiate(request.user):
            raise PermissionDenied()
        req = self.get_object()
        try:
            updated = generate_release_acte(req, user=request.user)
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(GuaranteeReleaseRequestSerializer(updated).data)

    @action(detail=True, methods=["post"], url_path="upload-acte-signe")
    def upload_acte_signe(self, request, pk=None):
        req = self.get_object()
        if not self._can_deposit_acte(request.user, req):
            raise PermissionDenied(
                "Seul l'initiateur ou un validateur du circuit peut "
                "déposer l'acte signé."
            )
        upload = request.FILES.get("file")
        if not upload:
            raise ValidationError({"file": "Fichier obligatoire."})
        from apps.common.upload_validation import validate_uploaded_file

        upload = validate_uploaded_file(
            upload, tenant=req.tenant, check_quota=True
        )
        try:
            updated = upload_release_acte_signed(
                req, upload, user=request.user
            )
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(
            GuaranteeReleaseRequestSerializer(
                updated, context={"request": request}
            ).data
        )

    @action(detail=True, methods=["get", "post"])
    def documents(self, request, pk=None):
        req = self.get_object()
        if request.method == "GET":
            from apps.documents.serializers import DocumentSerializer

            return Response(
                DocumentSerializer(release_documents(req), many=True).data
            )
        if not self._can_initiate(request.user):
            raise PermissionDenied()
        if req.status in (
            GuaranteeReleaseRequest.Status.COMPLETED,
            GuaranteeReleaseRequest.Status.CANCELLED,
            GuaranteeReleaseRequest.Status.REJECTED,
        ):
            raise ValidationError(
                "Impossible d'ajouter des pièces sur ce statut."
            )

        from django.contrib.contenttypes.models import ContentType

        from apps.documents.models import Document, DocumentCategory
        from apps.documents.serializers import DocumentSerializer

        ensure_release_document_categories(req.tenant)
        serializer = ReleaseDocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]
        name = (serializer.validated_data.get("name") or "").strip() or upload.name
        category_code = (
            serializer.validated_data.get("category") or ""
        ).strip() or "ML_OTHER"
        category = DocumentCategory.objects.filter(
            tenant_id=req.tenant_id, code=category_code, is_active=True
        ).first()
        if category is None:
            category = DocumentCategory.objects.filter(
                tenant_id=req.tenant_id, code="ML_OTHER"
            ).first()
        if category is None:
            raise ValidationError(
                {"category": "Catégorie documentaire introuvable."}
            )
        ct = ContentType.objects.get_for_model(GuaranteeReleaseRequest)
        doc = Document(
            tenant_id=req.tenant_id,
            category=category,
            name=name,
            file=upload,
            content_type=ct,
            object_id=req.id,
            uploaded_by=request.user,
        )
        doc.mime_type = getattr(upload, "content_type", "") or ""
        doc.save()
        doc.compute_hash()
        doc.save(update_fields=["mime_type", "sha256", "size_bytes"])
        from apps.documents.quotas import bump_ged_usage

        bump_ged_usage(doc.tenant_id, doc.size_bytes)
        return Response(DocumentSerializer(doc).data, status=201)

    @action(detail=True, methods=["post"])
    def retry_cbs(self, request, pk=None):
        req = self.get_object()
        if req.status != GuaranteeReleaseRequest.Status.BLOCKED:
            raise ValidationError(
                "Seule une demande bloquée par le CBS peut être relancée."
            )
        try:
            updated = complete_release_request(req)
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        if updated.status == GuaranteeReleaseRequest.Status.BLOCKED:
            raise ValidationError(cbs_block_message(updated))
        return Response(GuaranteeReleaseRequestSerializer(updated).data)

    @action(detail=True, methods=["get"])
    def workflow(self, request, pk=None):
        req = self.get_object()
        ct = ContentType.objects.get_for_model(GuaranteeReleaseRequest)
        inst = (
            WorkflowInstance.objects.filter(content_type=ct, object_id=req.pk)
            .select_related("definition")
            .prefetch_related("tasks", "tasks__step")
            .order_by("-created_at")
            .first()
        )
        if inst is None:
            return Response({"instance": None})
        from apps.workflow.serializers import WorkflowInstanceSerializer

        return Response({"instance": WorkflowInstanceSerializer(inst).data})


class DationRequestViewSet(TenantScopedViewSet):
    queryset = DationRequest.objects.select_related(
        "client",
        "application",
        "application__loan",
        "application__loan__collection_case",
        "agency",
        "resulting_guarantee",
    ).prefetch_related("assets", "assets__guarantee", "fees", "fees__asset").all()
    serializer_class = DationRequestSerializer
    action_perms = {
        "create": ["guarantees.initiate_dationrequest"],
        "preview_cbs": ["guarantees.initiate_dationrequest"],
        "retry_cbs": ["guarantees.initiate_dationrequest"],
        "submit": ["guarantees.initiate_dationrequest"],
        "cancel": ["guarantees.initiate_dationrequest"],
        "refresh_cbs": ["guarantees.initiate_dationrequest"],
        "add_asset": ["guarantees.initiate_dationrequest"],
        "remove_asset": ["guarantees.initiate_dationrequest"],
        "add_fee": ["guarantees.initiate_dationrequest"],
        "remove_fee": ["guarantees.initiate_dationrequest"],
        "update_draft": ["guarantees.initiate_dationrequest"],
        "ensure_categories": ["guarantees.initiate_dationrequest"],
    }
    action_any_perms = {
        "list": ["guarantees.view_dationrequest", "guarantees.initiate_dationrequest"],
        "retrieve": ["guarantees.view_dationrequest", "guarantees.initiate_dationrequest"],
        "workflow": ["guarantees.view_dationrequest", "guarantees.initiate_dationrequest"],
    }
    action_method_any_perms = {
        "documents": {
            "GET": ["guarantees.view_dationrequest", "guarantees.initiate_dationrequest"],
        },
    }
    action_method_perms = {
        "documents": {"POST": ["guarantees.initiate_dationrequest"]},
    }
    filterset_fields = ["status", "client", "application", "agency"]
    search_fields = [
        "reference",
        "cbs_client_id",
        "asset_description",
        "comment",
        "client__last_name",
        "client__first_name",
        "client__company_name",
    ]
    http_method_names = ["get", "head", "options", "post"]

    def _can_initiate(self, user):
        return user.is_superuser or user.has_perm(
            "guarantees.initiate_dationrequest"
        )

    @action(detail=False, methods=["get"], url_path="preview-cbs")
    def preview_cbs(self, request):
        """
        Interroge le CBS pour le montant de créance (encours client)
        sans créer de demande — utilisé à la sélection du client.
        """
        if not self._can_initiate(request.user):
            raise PermissionDenied(
                "Vous n'avez pas le droit d'initier une dation en paiement."
            )
        cbs_id = (
            request.query_params.get("cbs_client_id")
            or request.query_params.get("cbs_client")
            or ""
        ).strip()
        tenant_id = get_current_tenant_id() or getattr(
            request.user, "tenant_id", None
        )
        if not tenant_id:
            raise ValidationError("Contexte filiale manquant.")
        from apps.tenants.currency import tenant_currency

        currency = (
            request.query_params.get("currency") or ""
        ).strip().upper() or tenant_currency(tenant_id)
        try:
            cbs = preview_dation_cbs(
                tenant_id=tenant_id,
                cbs_client_id=cbs_id,
                currency=currency,
            )
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(
            {
                "cbs_client_id": cbs_id,
                "total_outstanding": str(cbs["total_outstanding"]),
                "currency": cbs["currency"],
                "breakdown": cbs.get("breakdown") or [],
                "checked_at": None,
            }
        )

    def create(self, request, *args, **kwargs):
        if not self._can_initiate(request.user):
            raise PermissionDenied(
                "Vous n'avez pas le droit d'initier une dation en paiement."
            )
        client_id = request.data.get("client")
        if not client_id:
            raise ValidationError({"client": "Obligatoire."})
        client = get_for_tenant(Client, client_id, error_field="client")

        application = None
        app_id = request.data.get("application")
        if app_id:
            from apps.credits.models import CreditApplication

            application = get_for_tenant(CreditApplication, app_id, error_field="application")
            if application.client_id != client.pk:
                raise ValidationError(
                    {"application": "Ce dossier n'appartient pas au client indiqué."}
                )

        guarantee_ids = request.data.get("guarantee_ids") or []
        if isinstance(guarantee_ids, str):
            guarantee_ids = [guarantee_ids]
        if not isinstance(guarantee_ids, list):
            raise ValidationError({"guarantee_ids": "Liste attendue."})

        additional_assets = request.data.get("additional_assets") or []
        if not isinstance(additional_assets, list):
            raise ValidationError({"additional_assets": "Liste attendue."})

        fees = request.data.get("fees") or []
        if fees and not isinstance(fees, list):
            raise ValidationError({"fees": "Liste attendue."})

        # as_draft=True par défaut (pièces / frais avant circuit).
        as_draft_raw = request.data.get("as_draft", True)
        if isinstance(as_draft_raw, str):
            as_draft = as_draft_raw.strip().lower() not in {"0", "false", "no"}
        else:
            as_draft = bool(as_draft_raw)

        asset_value = request.data.get("asset_value")
        try:
            req = initiate_dation_request(
                client=client,
                user=request.user,
                asset_description=request.data.get("asset_description", ""),
                asset_value=asset_value if asset_value not in (None, "") else None,
                application=application,
                comment=request.data.get("comment", ""),
                cbs_client_id=request.data.get("cbs_client_id", ""),
                guarantee_ids=guarantee_ids,
                additional_assets=additional_assets,
                fees=fees,
                as_draft=as_draft,
                require_full_coverage=bool(
                    request.data.get("require_full_coverage", False)
                ),
                settlement_notes=request.data.get("settlement_notes", "") or "",
            )
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(DationRequestSerializer(req).data, status=201)

    @action(detail=True, methods=["post"], url_path="update-draft")
    def update_draft(self, request, pk=None):
        if not self._can_initiate(request.user):
            raise PermissionDenied("Droit initiate_dationrequest requis.")
        req = self.get_object()
        application = None
        if "application" in request.data:
            app_id = request.data.get("application")
            if app_id:
                from apps.credits.models import CreditApplication

                application = get_for_tenant(CreditApplication, app_id, error_field="application")
        kwargs = {
            "user": request.user,
            "comment": request.data.get("comment"),
            "settlement_notes": request.data.get("settlement_notes"),
            "require_full_coverage": request.data.get("require_full_coverage"),
        }
        if "application" in request.data:
            kwargs["application"] = application
        try:
            updated = update_dation_request(req, **kwargs)
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(DationRequestSerializer(updated).data)

    @action(detail=True, methods=["post"], url_path="add-asset")
    def add_asset(self, request, pk=None):
        if not self._can_initiate(request.user):
            raise PermissionDenied("Droit initiate_dationrequest requis.")
        req = self.get_object()
        try:
            asset = add_dation_asset(
                req,
                guarantee_id=request.data.get("guarantee")
                or request.data.get("guarantee_id"),
                description=request.data.get("description", ""),
                value=request.data.get("value"),
                asset_type=request.data.get("asset_type"),
                notes=request.data.get("notes", ""),
                user=request.user,
            )
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(
            {
                "asset": DationAssetSerializer(asset).data,
                "dation": DationRequestSerializer(req).data,
            },
            status=201,
        )

    @action(
        detail=True,
        methods=["post"],
        url_path=r"remove-asset/(?P<asset_id>[^/.]+)",
    )
    def remove_asset(self, request, pk=None, asset_id=None):
        if not self._can_initiate(request.user):
            raise PermissionDenied("Droit initiate_dationrequest requis.")
        req = self.get_object()
        try:
            updated = remove_dation_asset(req, asset_id, user=request.user)
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(DationRequestSerializer(updated).data)

    @action(detail=True, methods=["post"], url_path="add-fee")
    def add_fee(self, request, pk=None):
        if not self._can_initiate(request.user):
            raise PermissionDenied("Droit initiate_dationrequest requis.")
        req = self.get_object()
        try:
            fee = add_dation_fee(req, request.data, user=request.user)
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(
            {
                "fee": DationFeeSerializer(fee).data,
                "dation": DationRequestSerializer(req).data,
            },
            status=201,
        )

    @action(
        detail=True,
        methods=["post"],
        url_path=r"remove-fee/(?P<fee_id>[^/.]+)",
    )
    def remove_fee(self, request, pk=None, fee_id=None):
        if not self._can_initiate(request.user):
            raise PermissionDenied("Droit initiate_dationrequest requis.")
        req = self.get_object()
        try:
            updated = remove_dation_fee(req, fee_id, user=request.user)
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(DationRequestSerializer(updated).data)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        if not self._can_initiate(request.user):
            raise PermissionDenied("Droit initiate_dationrequest requis.")
        req = self.get_object()
        try:
            updated = submit_dation_request(req, user=request.user)
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(DationRequestSerializer(updated).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        if not self._can_initiate(request.user):
            raise PermissionDenied("Droit initiate_dationrequest requis.")
        req = self.get_object()
        try:
            updated = cancel_dation_request(
                req,
                user=request.user,
                comment=request.data.get("comment", ""),
            )
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(DationRequestSerializer(updated).data)

    @action(detail=True, methods=["post"], url_path="refresh-cbs")
    def refresh_cbs(self, request, pk=None):
        if not self._can_initiate(request.user):
            raise PermissionDenied("Droit initiate_dationrequest requis.")
        req = self.get_object()
        try:
            updated = refresh_dation_cbs(req, user=request.user)
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(DationRequestSerializer(updated).data)

    @action(detail=True, methods=["get", "post"])
    def documents(self, request, pk=None):
        """Pièces GED (documents / photos) liées au dossier ou à un bien."""
        req = self.get_object()
        if request.method == "GET":
            if not (
                request.user.is_superuser
                or request.user.has_perm("guarantees.view_dationrequest")
                or request.user.has_perm("guarantees.initiate_dationrequest")
            ):
                raise PermissionDenied()
            from apps.documents.serializers import DocumentSerializer

            docs = dation_documents(req)
            return Response(DocumentSerializer(docs, many=True).data)

        if not self._can_initiate(request.user):
            raise PermissionDenied("Droit initiate_dationrequest requis.")
        if req.status in (
            DationRequest.Status.COMPLETED,
            DationRequest.Status.CANCELLED,
            DationRequest.Status.REJECTED,
        ):
            raise ValidationError(
                "Impossible d'ajouter des pièces sur ce statut."
            )

        from django.contrib.contenttypes.models import ContentType

        from apps.documents.models import Document, DocumentCategory
        from apps.documents.serializers import DocumentSerializer

        ensure_dation_document_categories(req.tenant)
        serializer = DationDocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]
        name = (serializer.validated_data.get("name") or "").strip() or upload.name
        category_code = (
            serializer.validated_data.get("category") or ""
        ).strip() or "DAT_OTHER"
        asset_id = serializer.validated_data.get("asset")
        target = req
        ct = ContentType.objects.get_for_model(DationRequest)
        if asset_id:
            try:
                target = req.assets.get(pk=asset_id)
            except DationAsset.DoesNotExist as exc:
                raise ValidationError(
                    {"asset": "Bien introuvable sur ce dossier."}
                ) from exc
            ct = ContentType.objects.get_for_model(DationAsset)

        category = DocumentCategory.objects.filter(
            tenant_id=req.tenant_id, code=category_code, is_active=True
        ).first()
        if category is None:
            category = DocumentCategory.objects.filter(
                tenant_id=req.tenant_id, code="DAT_OTHER"
            ).first()
        if category is None:
            raise ValidationError(
                {"category": "Catégorie documentaire introuvable."}
            )

        doc = Document(
            tenant_id=req.tenant_id,
            category=category,
            name=name,
            file=upload,
            content_type=ct,
            object_id=target.id,
            uploaded_by=request.user,
        )
        doc.mime_type = getattr(upload, "content_type", "") or ""
        doc.save()
        doc.compute_hash()
        doc.save(update_fields=["mime_type", "sha256", "size_bytes"])
        from apps.documents.quotas import bump_ged_usage

        bump_ged_usage(doc.tenant_id, doc.size_bytes)
        return Response(DocumentSerializer(doc).data, status=201)

    @action(detail=True, methods=["post"], url_path="ensure-categories")
    def ensure_categories(self, request, pk=None):
        req = self.get_object()
        created = ensure_dation_document_categories(req.tenant)
        return Response({"created": created})

    @action(detail=True, methods=["post"])
    def retry_cbs(self, request, pk=None):
        req = self.get_object()
        if req.status != DationRequest.Status.BLOCKED:
            raise ValidationError(
                "Seule une demande bloquée par le CBS peut être relancée."
            )
        try:
            updated = complete_dation_request(req)
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        if updated.status == DationRequest.Status.BLOCKED:
            raise ValidationError(cbs_block_message(updated))
        return Response(DationRequestSerializer(updated).data)

    @action(detail=True, methods=["get"])
    def workflow(self, request, pk=None):
        req = self.get_object()
        ct = ContentType.objects.get_for_model(DationRequest)
        inst = (
            WorkflowInstance.objects.filter(content_type=ct, object_id=req.pk)
            .select_related("definition")
            .prefetch_related("tasks", "tasks__step")
            .order_by("-created_at")
            .first()
        )
        if inst is None:
            return Response({"instance": None})
        from apps.workflow.serializers import WorkflowInstanceSerializer

        return Response({"instance": WorkflowInstanceSerializer(inst).data})


class GuaranteeFormalizationRequestViewSet(TenantScopedViewSet):
    queryset = GuaranteeFormalizationRequest.objects.select_related(
        "guarantee", "guarantee__client", "application", "agency"
    ).prefetch_related("fees").all()
    serializer_class = GuaranteeFormalizationRequestSerializer
    action_perms = {
        "create": ["guarantees.initiate_guaranteeformalizationrequest"],
        "compose_context": ["guarantees.initiate_guaranteeformalizationrequest"],
        "update_draft": ["guarantees.initiate_guaranteeformalizationrequest"],
        "advance_stage": ["guarantees.initiate_guaranteeformalizationrequest"],
        "start": ["guarantees.initiate_guaranteeformalizationrequest"],
        "submit": ["guarantees.initiate_guaranteeformalizationrequest"],
        "cancel": ["guarantees.initiate_guaranteeformalizationrequest"],
        "complete": ["guarantees.initiate_guaranteeformalizationrequest"],
        "add_fee": ["guarantees.initiate_guaranteeformalizationrequest"],
        "remove_fee": ["guarantees.initiate_guaranteeformalizationrequest"],
        "ensure_categories": [
            "guarantees.initiate_guaranteeformalizationrequest"
        ],
    }
    action_any_perms = {
        "list": [
            "guarantees.view_guaranteeformalizationrequest",
            "guarantees.initiate_guaranteeformalizationrequest",
        ],
        "retrieve": [
            "guarantees.view_guaranteeformalizationrequest",
            "guarantees.initiate_guaranteeformalizationrequest",
        ],
        "workflow": [
            "guarantees.view_guaranteeformalizationrequest",
            "guarantees.initiate_guaranteeformalizationrequest",
        ],
    }
    action_method_any_perms = {
        "documents": {
            "GET": [
                "guarantees.view_guaranteeformalizationrequest",
                "guarantees.initiate_guaranteeformalizationrequest",
            ],
        },
    }
    action_method_perms = {
        "documents": {
            "POST": ["guarantees.initiate_guaranteeformalizationrequest"],
        },
    }
    filterset_fields = [
        "status", "legal_stage", "guarantee", "application", "agency",
    ]
    search_fields = [
        "reference",
        "notary_name",
        "notary_reference",
        "registration_number",
        "comment",
        "guarantee__client__last_name",
        "guarantee__client__first_name",
        "guarantee__client__company_name",
    ]
    http_method_names = ["get", "head", "options", "post"]

    def get_queryset(self):
        qs = super().get_queryset()
        client = query_param(self.request, "client")
        if client:
            qs = qs.filter(guarantee__client_id=client)
        return qs

    def _can_initiate(self, user):
        return user.is_superuser or user.has_perm(
            "guarantees.initiate_guaranteeformalizationrequest"
        )

    @action(detail=False, methods=["get"], url_path="compose-context")
    def compose_context(self, request):
        """
        Recherche par client ou dossier → garanties attachées au crédit.
        Query: ?client=<id> ou ?application=<id>
        """
        from apps.clients.models import Client
        from apps.credits.models import CreditApplication
        from apps.guarantees.formalization_services import (
            formalization_compose_context,
        )

        if not self._can_initiate(request.user):
            raise PermissionDenied(
                "Droit initiate_guaranteeformalizationrequest requis."
            )
        client_id = (request.query_params.get("client") or "").strip()
        app_id = (request.query_params.get("application") or "").strip()
        if not client_id and not app_id:
            raise ValidationError(
                {"detail": "Indiquez client ou application."}
            )
        application = None
        client = None
        if app_id:
            application = get_for_tenant(
                CreditApplication, app_id, error_field="application"
            )
        else:
            client = get_for_tenant(Client, client_id, error_field="client")
        try:
            payload = formalization_compose_context(
                client=client, application=application
            )
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(payload)

    def create(self, request, *args, **kwargs):
        if not self._can_initiate(request.user):
            raise PermissionDenied(
                "Vous n'avez pas le droit d'initier une formalisation."
            )
        guarantee_id = request.data.get("guarantee")
        if not guarantee_id:
            raise ValidationError({"guarantee": "Obligatoire."})
        guarantee = get_for_tenant(Guarantee, guarantee_id, error_field="guarantee")

        fees = request.data.get("fees") or []
        if fees and not isinstance(fees, list):
            raise ValidationError({"fees": "Liste attendue."})

        as_draft_raw = request.data.get("as_draft", True)
        if isinstance(as_draft_raw, str):
            as_draft = as_draft_raw.strip().lower() not in {
                "0", "false", "no",
            }
        else:
            as_draft = bool(as_draft_raw)

        try:
            req = initiate_formalization_request(
                guarantee=guarantee,
                user=request.user,
                comment=request.data.get("comment", ""),
                notary_name=request.data.get("notary_name", ""),
                notary_reference=request.data.get("notary_reference", ""),
                fees=fees,
                as_draft=as_draft,
            )
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(
            GuaranteeFormalizationRequestSerializer(req).data, status=201
        )

    @action(detail=True, methods=["post"], url_path="update-draft")
    def update_draft(self, request, pk=None):
        if not self._can_initiate(request.user):
            raise PermissionDenied(
                "Droit initiate_guaranteeformalizationrequest requis."
            )
        req = self.get_object()
        kwargs = {"user": request.user}
        for key in (
            "comment",
            "notary_name",
            "notary_reference",
            "registration_number",
            "registration_authority",
        ):
            if key in request.data:
                kwargs[key] = request.data.get(key)
        for key in (
            "sent_to_notary_at",
            "expected_return_date",
            "registration_date",
        ):
            if key in request.data:
                kwargs[key] = request.data.get(key)
        try:
            updated = update_formalization_request(req, **kwargs)
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(GuaranteeFormalizationRequestSerializer(updated).data)

    @action(detail=True, methods=["post"], url_path="advance-stage")
    def advance_stage(self, request, pk=None):
        if not self._can_initiate(request.user):
            raise PermissionDenied(
                "Droit initiate_guaranteeformalizationrequest requis."
            )
        req = self.get_object()
        legal_stage = request.data.get("legal_stage")
        if not legal_stage:
            raise ValidationError({"legal_stage": "Obligatoire."})
        extra = {
            k: request.data.get(k)
            for k in (
                "notary_name",
                "notary_reference",
                "registration_number",
                "registration_date",
                "registration_authority",
            )
            if k in request.data
        }
        try:
            updated = advance_legal_stage(
                req, legal_stage, user=request.user, **extra
            )
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(GuaranteeFormalizationRequestSerializer(updated).data)

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        if not self._can_initiate(request.user):
            raise PermissionDenied(
                "Droit initiate_guaranteeformalizationrequest requis."
            )
        req = self.get_object()
        try:
            updated = start_formalization_progress(req, user=request.user)
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(GuaranteeFormalizationRequestSerializer(updated).data)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        if not self._can_initiate(request.user):
            raise PermissionDenied(
                "Droit initiate_guaranteeformalizationrequest requis."
            )
        req = self.get_object()
        try:
            updated = submit_formalization_request(req, user=request.user)
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(GuaranteeFormalizationRequestSerializer(updated).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        if not self._can_initiate(request.user):
            raise PermissionDenied(
                "Droit initiate_guaranteeformalizationrequest requis."
            )
        req = self.get_object()
        try:
            updated = cancel_formalization_request(
                req,
                user=request.user,
                comment=request.data.get("comment", ""),
            )
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(GuaranteeFormalizationRequestSerializer(updated).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        if not self._can_initiate(request.user):
            raise PermissionDenied(
                "Droit initiate_guaranteeformalizationrequest requis."
            )
        req = self.get_object()
        try:
            updated = complete_formalization_request(req, user=request.user)
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(GuaranteeFormalizationRequestSerializer(updated).data)

    @action(detail=True, methods=["post"], url_path="add-fee")
    def add_fee(self, request, pk=None):
        if not self._can_initiate(request.user):
            raise PermissionDenied(
                "Droit initiate_guaranteeformalizationrequest requis."
            )
        req = self.get_object()
        try:
            fee = add_formalization_fee(req, request.data, user=request.user)
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(
            {
                "fee": FormalizationFeeSerializer(fee).data,
                "formalization": GuaranteeFormalizationRequestSerializer(
                    req
                ).data,
            },
            status=201,
        )

    @action(
        detail=True,
        methods=["post"],
        url_path=r"remove-fee/(?P<fee_id>[^/.]+)",
    )
    def remove_fee(self, request, pk=None, fee_id=None):
        if not self._can_initiate(request.user):
            raise PermissionDenied(
                "Droit initiate_guaranteeformalizationrequest requis."
            )
        req = self.get_object()
        try:
            updated = remove_formalization_fee(
                req, fee_id, user=request.user
            )
        except ProcessError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(GuaranteeFormalizationRequestSerializer(updated).data)

    @action(detail=True, methods=["get", "post"])
    def documents(self, request, pk=None):
        """Pièces GED liées au dossier de formalisation."""
        req = self.get_object()
        if request.method == "GET":
            if not (
                request.user.is_superuser
                or request.user.has_perm(
                    "guarantees.view_guaranteeformalizationrequest"
                )
                or request.user.has_perm(
                    "guarantees.initiate_guaranteeformalizationrequest"
                )
            ):
                raise PermissionDenied()
            from apps.documents.serializers import DocumentSerializer

            return Response(
                DocumentSerializer(
                    formalization_documents(req), many=True
                ).data
            )

        if not self._can_initiate(request.user):
            raise PermissionDenied(
                "Droit initiate_guaranteeformalizationrequest requis."
            )
        if req.status in (
            GuaranteeFormalizationRequest.Status.COMPLETED,
            GuaranteeFormalizationRequest.Status.CANCELLED,
            GuaranteeFormalizationRequest.Status.REJECTED,
        ):
            raise ValidationError(
                "Impossible d'ajouter des pièces sur ce statut."
            )

        from django.contrib.contenttypes.models import ContentType

        from apps.documents.models import Document, DocumentCategory
        from apps.documents.serializers import DocumentSerializer

        ensure_formalization_document_categories(req.tenant)
        serializer = FormalizationDocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]
        name = (
            (serializer.validated_data.get("name") or "").strip()
            or upload.name
        )
        category_code = (
            serializer.validated_data.get("category") or ""
        ).strip() or "FORM_OTHER"

        category = DocumentCategory.objects.filter(
            tenant_id=req.tenant_id, code=category_code, is_active=True
        ).first()
        if category is None:
            category = DocumentCategory.objects.filter(
                tenant_id=req.tenant_id, code="FORM_OTHER"
            ).first()
        if category is None:
            raise ValidationError(
                {"category": "Catégorie documentaire introuvable."}
            )

        ct = ContentType.objects.get_for_model(GuaranteeFormalizationRequest)
        doc = Document(
            tenant_id=req.tenant_id,
            category=category,
            name=name,
            file=upload,
            content_type=ct,
            object_id=req.id,
            uploaded_by=request.user,
        )
        doc.mime_type = getattr(upload, "content_type", "") or ""
        doc.save()
        doc.compute_hash()
        doc.save(update_fields=["mime_type", "sha256", "size_bytes"])
        from apps.documents.quotas import bump_ged_usage

        bump_ged_usage(doc.tenant_id, doc.size_bytes)
        return Response(DocumentSerializer(doc).data, status=201)

    @action(detail=True, methods=["post"], url_path="ensure-categories")
    def ensure_categories(self, request, pk=None):
        if not self._can_initiate(request.user):
            raise PermissionDenied(
                "Droit initiate_guaranteeformalizationrequest requis."
            )
        req = self.get_object()
        created = ensure_formalization_document_categories(req.tenant)
        return Response({"created": created})

    @action(detail=True, methods=["get"])
    def workflow(self, request, pk=None):
        req = self.get_object()
        ct = ContentType.objects.get_for_model(GuaranteeFormalizationRequest)
        inst = (
            WorkflowInstance.objects.filter(content_type=ct, object_id=req.pk)
            .select_related("definition")
            .prefetch_related("tasks", "tasks__step")
            .order_by("-created_at")
            .first()
        )
        if inst is None:
            return Response({"instance": None})
        from apps.workflow.serializers import WorkflowInstanceSerializer

        return Response({"instance": WorkflowInstanceSerializer(inst).data})
