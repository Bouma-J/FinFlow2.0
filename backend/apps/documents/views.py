import uuid
from datetime import timedelta

from django.http import FileResponse, Http404
from django.shortcuts import redirect
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.common.storage_urls import (
    file_download_url,
    generate_presigned_upload,
    is_s3_storage,
)
from apps.common.tenancy import get_current_tenant_id
from apps.common.viewsets import TenantScopedViewSet

from .list_filters import apply_document_list_filters
from .models import Document, DocumentCategory
from .serializers import DocumentCategorySerializer, DocumentSerializer


class DocumentCategoryViewSet(TenantScopedViewSet):
    queryset = DocumentCategory.objects.all()
    serializer_class = DocumentCategorySerializer
    filterset_fields = ["tracks_expiry", "is_active"]
    search_fields = ["code", "label"]


class DocumentViewSet(TenantScopedViewSet):
    queryset = Document.objects.select_related(
        "category", "uploaded_by", "content_type"
    ).all()
    serializer_class = DocumentSerializer
    action_perms = {
        "download": ["documents.view_document"],
        "upload_url": ["documents.add_document"],
        "expiring_soon": ["documents.view_document"],
        "restore": ["documents.change_document"],
        "verify": ["documents.change_document"],
    }
    filterset_fields = ["category", "content_type", "object_id", "category__code"]
    search_fields = [
        "name",
        "category__label",
        "category__code",
        "uploaded_by__first_name",
        "uploaded_by__last_name",
        "uploaded_by__username",
        "origin_key",
    ]
    ordering_fields = ["created_at", "name", "expiry_date", "size_bytes"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        if getattr(self, "action", None) in (None, "list", "expiring_soon"):
            qs = apply_document_list_filters(qs, self.request)
        return qs

    def perform_create(self, serializer):
        instance = serializer.save(uploaded_by=self.request.user)
        instance.mime_type = getattr(instance.file.file, "content_type", "") or ""
        instance.compute_hash()
        instance.save(update_fields=["mime_type", "sha256", "size_bytes"])
        from .quotas import bump_ged_usage

        bump_ged_usage(instance.tenant_id, instance.size_bytes)

    def perform_destroy(self, instance):
        # Soft-delete : rétention fichier + quota jusqu'à purge hard.
        instance.soft_delete(user=self.request.user)

    def perform_update(self, serializer):
        doc = serializer.save()
        doc.verification_status = "PENDING"
        doc.verified_by = None
        doc.verified_at = None
        doc.verification_comment = ""
        doc.compute_hash()
        doc.save()

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        from django.db import transaction

        with transaction.atomic():
            doc = self.get_object()
            doc = Document.objects.select_for_update().get(pk=doc.pk)
            state = request.data.get("status")
            comment = str(request.data.get("comment") or "").strip()
            if state not in ("VERIFIED", "REJECTED") or not comment:
                raise ValidationError("Choisissez vérifié ou rejeté et précisez les contrôles effectués.")
            if state == "VERIFIED" and (not doc.file or (doc.expiry_date and doc.expiry_date < timezone.now().date())):
                raise ValidationError("Un document absent ou expiré ne peut être vérifié.")
            doc.verification_status = state
            doc.verified_by = request.user
            doc.verified_at = timezone.now()
            doc.verification_comment = comment
            doc.save()
            return Response(self.get_serializer(doc).data)

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        """Restaure un document soft-deleted (droit change_document)."""
        doc = (
            Document.including_deleted.filter(pk=pk)
            .filter(tenant_id=get_current_tenant_id())
            .first()
        )
        if doc is None:
            raise Http404()
        if not doc.is_deleted:
            return Response({"detail": "Document déjà actif."})
        doc.restore(user=request.user)
        return Response(DocumentSerializer(doc, context={"request": request}).data)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """URL de téléchargement (présignée S3) ou redirection locale."""
        doc = self.get_object()
        if not doc.file:
            raise Http404("Aucun fichier.")
        url = file_download_url(doc.file, expires=3600)
        if not url:
            raise Http404("Aucun fichier.")
        if request.query_params.get("redirect") == "1":
            return redirect(url)
        return Response({"url": url, "name": doc.name, "expires_in": 3600})

    @action(detail=False, methods=["post"])
    def upload_url(self, request):
        """
        URL PUT présignée pour upload direct vers MinIO/S3.
        Corps : {filename, size, content_type?, category?}. La taille exacte est
        exigée et signée pour que S3/MinIO refuse un PUT d'une autre taille.
        """
        if not is_s3_storage():
            raise ValidationError(
                "L'upload présigné n'est disponible qu'avec STORAGE_BACKEND=s3."
            )
        filename = (request.data.get("filename") or "upload.bin").strip()
        size = request.data.get("size")
        try:
            if isinstance(size, bool) or size is None or str(size).strip() == "":
                raise ValueError
            size_int = int(size)
            if str(size_int) != str(size).strip() or size_int <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise ValidationError(
                {"size": "Indiquez la taille exacte du fichier en octets."}
            )
        from apps.common.upload_validation import assert_upload_meta

        filename = assert_upload_meta(filename=filename, size=size_int)
        tenant_id = get_current_tenant_id() or "group"
        from apps.documents.quotas import assert_ged_quota
        from apps.tenants.models import Tenant

        tenant = (
            Tenant.objects.filter(pk=tenant_id).first()
            if tenant_id != "group"
            else None
        )
        assert_ged_quota(tenant, size_int)
        content_type = (
            request.data.get("content_type") or "application/octet-stream"
        )
        from apps.common.files import safe_filename

        raw_category = (request.data.get("category") or "misc").strip()
        category = safe_filename(raw_category.replace("/", "_")) or "misc"
        key = f"documents/{tenant_id}/{category}/{uuid.uuid4().hex}_{filename}"
        payload = generate_presigned_upload(
            key=key, content_type=content_type, size_bytes=size_int, expires=900
        )
        if not payload:
            raise ValidationError("Impossible de générer l'URL présignée.")
        return Response(payload, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def expiring_soon(self, request):
        """Documents dont l'expiration approche (30 jours) ou est dépassée."""
        horizon = timezone.now().date() + timedelta(days=30)
        qs = self.get_queryset().filter(
            category__tracks_expiry=True,
            expiry_date__isnull=False,
            expiry_date__lte=horizon,
        ).order_by("expiry_date")
        page = self.paginate_queryset(qs)
        serializer = self.get_serializer(page or qs, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)
