from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import redirect
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.common.storage_urls import file_download_url, is_s3_storage
from apps.common.tenancy import get_current_tenant_id
from apps.common.viewsets import TenantScopedViewSet

from .context import LOOP_HELP, VARIABLE_CATALOG, build_context
from .models import ContractCategory, ContractTemplate, GeneratedContract
from .rendering import ContractRenderError, render_template
from .serializers import (
    ContractTemplateSerializer,
    GeneratedContractSerializer,
    GenerateContractSerializer,
    SignedContractUploadSerializer,
)
from .services import refresh_contract_status
from .tasks import generate_contract_task


def _get_application(application_id):
    from apps.common.scoped import require_tenant_id
    from apps.credits.models import CreditApplication

    tenant_id = require_tenant_id()
    try:
        return CreditApplication.all_tenants.select_related(
            "client", "client__agency", "product", "agency", "tenant"
        ).prefetch_related("client__phones").get(pk=application_id, tenant_id=tenant_id)
    except (CreditApplication.DoesNotExist, ValueError, TypeError, ValidationError):
        raise Http404("Dossier introuvable.")


class ContractTemplateViewSet(TenantScopedViewSet):
    queryset = ContractTemplate.objects.select_related("product").all()
    serializer_class = ContractTemplateSerializer
    action_perms = {
        "variables": ["contracts.view_contracttemplate"],
        "applicable": ["contracts.view_contracttemplate"],
    }
    filterset_fields = ["category", "applies_to", "is_active", "is_required"]
    search_fields = ["name", "code", "description"]

    @action(detail=False, methods=["get"])
    def variables(self, request):
        """Catalogue documenté des variables utilisables dans les modèles."""
        return Response({"groups": VARIABLE_CATALOG, "loop_help": LOOP_HELP})

    @action(detail=False, methods=["get"])
    def applicable(self, request):
        """Modèles pertinents pour un dossier + statut de génération."""
        application_id = request.query_params.get("application")
        if not application_id:
            raise ValidationError({"application": "Paramètre requis."})
        application = _get_application(application_id)
        generated = {
            gc.template_id: gc
            for gc in application.generated_contracts.exclude(
                status=GeneratedContract.Status.CANCELLED
            )
        }
        result = []
        for tpl in self.get_queryset().filter(is_active=True):
            if tpl.category == ContractCategory.SURETY:
                continue
            if not tpl.applies_to_application(application):
                continue
            gc = generated.get(tpl.id)
            result.append({
                "template": ContractTemplateSerializer(
                    tpl, context=self.get_serializer_context()
                ).data,
                "generated": gc is not None,
                "generated_contract_id": str(gc.id) if gc else None,
            })
        return Response(result)


class GeneratedContractViewSet(TenantScopedViewSet):
    queryset = GeneratedContract.objects.select_related(
        "application", "template", "created_by"
    ).all()
    serializer_class = GeneratedContractSerializer
    action_perms = {
        "generate": ["contracts.add_generatedcontract"],
        "upload_signed": ["contracts.change_generatedcontract"],
        "download": ["contracts.view_generatedcontract"],
    }
    filterset_fields = ["application", "status", "template"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def create(self, request, *args, **kwargs):
        raise ValidationError(
            "Utilisez l'action « generate » pour produire un contrat."
        )

    def perform_destroy(self, instance):
        files = []
        for field_name in ("file", "signed_file"):
            f = getattr(instance, field_name, None)
            if f and getattr(f, "name", None):
                files.append((f.storage, f.name))
        super().perform_destroy(instance)
        for storage, name in files:
            try:
                storage.delete(name)
            except Exception:  # noqa: BLE001
                import logging

                logging.getLogger("finflow").exception(
                    "Échec suppression contrat key=%s", name
                )

    @action(detail=False, methods=["post"])
    def generate(self, request):
        """Génère un contrat pour un dossier à partir d'un modèle."""
        payload = GenerateContractSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        application = _get_application(data["application"])
        from apps.common.scoped import require_tenant_id

        tenant_id = require_tenant_id()
        try:
            template = ContractTemplate.all_tenants.get(
                id=data["template"], tenant_id=tenant_id
            )
        except ContractTemplate.DoesNotExist:
            raise Http404("Modèle introuvable.")

        extra_values = data.get("extra_values") or {}
        primary_engagement = None
        engagement_id = data.get("surety_engagement")
        from .services import assert_surety_generation

        assert_surety_generation(template, engagement_id)
        if engagement_id:
            from apps.sureties.models import SuretyEngagement

            try:
                primary_engagement = SuretyEngagement.objects.select_related(
                    "surety"
                ).get(id=engagement_id, application=application)
            except SuretyEngagement.DoesNotExist:
                raise ValidationError(
                    {"surety_engagement": "Engagement introuvable pour ce dossier."}
                )

        async_mode = str(request.query_params.get("async", "1")).lower() not in (
            "0",
            "false",
            "no",
            "sync",
        )
        # ?sync=1 force le rendu dans la requête HTTP (debug / petits volumes)
        if str(request.query_params.get("sync", "")).lower() in (
            "1",
            "true",
            "yes",
        ):
            async_mode = False
        if async_mode:
            from apps.common.scoped import track_async_task

            task = generate_contract_task.delay(
                str(application.id),
                str(template.id),
                str(request.user.id),
                extra_values,
                str(get_current_tenant_id() or application.tenant_id or ""),
                str(engagement_id) if engagement_id else None,
            )
            track_async_task(task.id, request.user.id)
            return Response(
                {
                    "task_id": task.id,
                    "status": "queued",
                    "detail": "Génération du contrat en file d'attente.",
                },
                status=status.HTTP_202_ACCEPTED,
            )

        context = build_context(
            application,
            extra_values,
            primary_engagement=primary_engagement,
        )

        try:
            rendered = render_template(template, context)
        except ContractRenderError as exc:
            raise ValidationError({"detail": str(exc)})

        with transaction.atomic():
            # Un seul contrat actif par modèle et par dossier : on annule
            # l'éventuel précédent pour garder une trace tout en régénérant.
            # Si lié à un engagement, on limite l'annulation à cet engagement.
            cancel_qs = application.generated_contracts.filter(
                template=template
            ).exclude(status=GeneratedContract.Status.CANCELLED)
            if primary_engagement is not None:
                cancel_qs = cancel_qs.filter(
                    surety_engagement=primary_engagement
                )
            cancel_qs.update(status=GeneratedContract.Status.CANCELLED)
            # tenant AVANT file.save : upload_to utilise tenant_id pour le chemin S3.
            gc = GeneratedContract(
                tenant_id=application.tenant_id,
                application=application,
                template=template,
                template_name=template.name,
                category=template.category,
                surety_engagement=primary_engagement,
                context_snapshot=context,
                extra_values=extra_values,
                created_by=request.user,
                updated_by=request.user,
            )
            gc.file.save(rendered.name, rendered, save=False)
            gc.save()
            refresh_contract_status(application, request.user)

        serializer = self.get_serializer(gc)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        gc = self.get_object()
        if not gc.file:
            raise Http404("Aucun fichier.")
        if is_s3_storage() or request.query_params.get("presign") == "1":
            url = file_download_url(gc.file, expires=3600)
            if url and request.query_params.get("redirect") == "1":
                return redirect(url)
            if url:
                return Response({
                    "url": url,
                    "filename": gc.file.name.split("/")[-1],
                    "expires_in": 3600,
                })
        gc.file.open("rb")
        return FileResponse(
            gc.file, as_attachment=True, filename=gc.file.name.split("/")[-1]
        )

    @action(detail=True, methods=["post"])
    def upload_signed(self, request, pk=None):
        gc = self.get_object()
        serializer = SignedContractUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        gc.signed_file = serializer.validated_data["signed_file"]
        gc.notes = serializer.validated_data.get("notes", gc.notes)
        gc.status = GeneratedContract.Status.SIGNED
        gc.signed_at = timezone.now()
        gc.updated_by = request.user
        gc.save()
        return Response(self.get_serializer(gc).data)
