from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.common.access import apply_related_data_scope
from apps.common.list_filters import query_param
from apps.common.viewsets import AgencyScopedViewSet
from apps.contracts.serializers import (
    GeneratedContractSerializer,
    SignedContractUploadSerializer,
)

from .models import Surety, SuretyEngagement
from .serializers import (
    SuretyEngagementSerializer,
    SuretyListSerializer,
    SuretySerializer,
)
from .services import (
    call_engagement,
    generate_engagement_contract,
    release_engagement,
    upload_engagement_signed_contract,
)


class SuretyViewSet(AgencyScopedViewSet):
    queryset = Surety.objects.select_related("agency").all()
    serializer_class = SuretySerializer
    filterset_fields = ["surety_type", "is_active", "agency"]
    search_fields = [
        "name", "first_name", "last_name", "identifier",
        "national_id", "phone", "email", "activity",
        "company_name", "ifu", "rccm",
        "manager_last_name", "manager_first_name",
    ]
    ordering_fields = ["created_at", "name", "last_name"]

    def get_serializer_class(self):
        if self.action == "list":
            return SuretyListSerializer
        return SuretySerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "list":
            return qs.prefetch_related(
                "engagements__application__client",
            )
        return qs.prefetch_related(
            "engagements__application__client",
            "engagements__generated_contracts",
            "phones",
            "documents",
        )


class SuretyEngagementViewSet(AgencyScopedViewSet):
    queryset = SuretyEngagement.objects.select_related(
        "surety", "application", "application__client"
    ).prefetch_related("generated_contracts")
    serializer_class = SuretyEngagementSerializer
    filterset_fields = ["surety", "application", "status", "engagement_type"]
    agency_field = ""
    owner_field = ""
    action_perms = {
        "release": ["sureties.change_suretyengagement"],
        "call": ["sureties.change_suretyengagement"],
        "generate_contract": ["contracts.add_generatedcontract"],
        "upload_signed": ["contracts.change_generatedcontract"],
        "contract_templates": ["contracts.view_contracttemplate"],
    }

    def get_queryset(self):
        qs = super(AgencyScopedViewSet, self).get_queryset()
        user = self.request.user
        if user and user.is_authenticated:
            qs = apply_related_data_scope(qs, user, "application__agency")
        client = query_param(self.request, "client")
        if client:
            qs = qs.filter(application__client_id=client)
        return qs

    def _assert_application_allows_collateral(self, application):
        from apps.credits.access import can_attach_collateral

        if application is None:
            return
        if not can_attach_collateral(application, self.request.user):
            raise ValidationError(
                "Impossible de rattacher ou modifier une caution sur un "
                f"dossier « {application.get_status_display()} »."
            )

    def perform_create(self, serializer):
        surety = serializer.validated_data["surety"]
        amount = serializer.validated_data["amount"]
        application = serializer.validated_data.get("application")
        self._assert_application_allows_collateral(application)
        if surety.commitment_ceiling and amount > surety.available_ceiling:
            raise ValidationError(
                "Le montant dépasse le plafond disponible de la caution."
            )
        serializer.save()

    def perform_update(self, serializer):
        application = serializer.validated_data.get(
            "application", serializer.instance.application
        )
        self._assert_application_allows_collateral(application)
        amount = serializer.validated_data.get(
            "amount", serializer.instance.amount
        )
        surety = serializer.validated_data.get(
            "surety", serializer.instance.surety
        )
        if surety.commitment_ceiling:
            other = surety.total_committed
            if serializer.instance.status in (
                SuretyEngagement.Status.ACTIVE,
                SuretyEngagement.Status.CALLED,
            ):
                other = other - serializer.instance.amount
            if amount > (surety.commitment_ceiling - other):
                raise ValidationError(
                    "Le montant dépasse le plafond disponible de la caution."
                )
        super().perform_update(serializer)

    @action(detail=True, methods=["post"])
    def release(self, request, pk=None):
        engagement = self.get_object()
        comment = (request.data.get("comment") or "").strip()
        updated = release_engagement(
            engagement, user=request.user, comment=comment
        )
        return Response(self.get_serializer(updated).data)

    @action(detail=True, methods=["post"])
    def call(self, request, pk=None):
        engagement = self.get_object()
        comment = (request.data.get("comment") or "").strip()
        updated = call_engagement(
            engagement, user=request.user, comment=comment
        )
        return Response(self.get_serializer(updated).data)

    @action(detail=True, methods=["get"])
    def contract_templates(self, request, pk=None):
        """Modèles SURETY applicables au dossier de l'engagement."""
        from apps.contracts.models import ContractCategory, ContractTemplate
        from apps.contracts.serializers import ContractTemplateSerializer

        engagement = self.get_object()
        application = engagement.application
        result = []
        for tpl in ContractTemplate.objects.filter(
            is_active=True, category=ContractCategory.SURETY
        ).order_by("ordering", "name"):
            if tpl.applies_to_application(application):
                result.append(
                    ContractTemplateSerializer(
                        tpl, context=self.get_serializer_context()
                    ).data
                )
        return Response(result)

    @action(detail=True, methods=["post"])
    def generate_contract(self, request, pk=None):
        engagement = self.get_object()
        template_id = request.data.get("template")
        extra_values = request.data.get("extra_values") or {}
        if isinstance(extra_values, str):
            import json

            try:
                extra_values = json.loads(extra_values or "{}")
            except json.JSONDecodeError:
                extra_values = {}

        sync = str(request.query_params.get("sync", "")).lower() in (
            "1",
            "true",
            "yes",
        )
        if not sync:
            from apps.contracts.tasks import generate_contract_task
            from apps.sureties.services import _pick_surety_template

            template = _pick_surety_template(
                engagement.application,
                str(template_id) if template_id else None,
            )
            task = generate_contract_task.delay(
                str(engagement.application_id),
                str(template.id),
                str(request.user.id),
                extra_values,
                str(engagement.tenant_id or engagement.application.tenant_id),
                str(engagement.id),
            )
            from apps.common.scoped import track_async_task

            track_async_task(task.id, request.user.id)
            return Response(
                {
                    "task_id": task.id,
                    "status": "queued",
                    "detail": "Génération du contrat de caution en file d'attente.",
                },
                status=status.HTTP_202_ACCEPTED,
            )

        gc = generate_engagement_contract(
            engagement,
            user=request.user,
            template_id=str(template_id) if template_id else None,
            extra_values=extra_values,
        )
        return Response(
            GeneratedContractSerializer(
                gc, context=self.get_serializer_context()
            ).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def upload_signed(self, request, pk=None):
        engagement = self.get_object()
        serializer = SignedContractUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        gc = upload_engagement_signed_contract(
            engagement,
            signed_file=serializer.validated_data["signed_file"],
            user=request.user,
            notes=serializer.validated_data.get("notes", ""),
        )
        return Response(
            GeneratedContractSerializer(
                gc, context=self.get_serializer_context()
            ).data
        )
