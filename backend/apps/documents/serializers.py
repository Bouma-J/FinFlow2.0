from rest_framework import serializers

from apps.common.storage_urls import file_download_url, presign_file_fields

from .models import Document, DocumentCategory


class DocumentCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentCategory
        fields = ["id", "code", "label", "description", "tracks_expiry", "is_active"]
        read_only_fields = ["id"]


class DocumentSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="category.label", read_only=True)
    category_code = serializers.CharField(source="category.code", read_only=True)
    uploaded_by_name = serializers.SerializerMethodField()
    related_type = serializers.SerializerMethodField()
    related_kind = serializers.SerializerMethodField()
    related_label = serializers.SerializerMethodField()
    related_path = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "category",
            "category_label",
            "category_code",
            "name",
            "file",
            "file_url",
            "mime_type",
            "size_bytes",
            "sha256",
            "version",
            "verification_status", "verified_by", "verified_at", "verification_comment",
            "issue_date",
            "expiry_date",
            "content_type",
            "object_id",
            "related_type",
            "related_kind",
            "related_label",
            "related_path",
            "uploaded_by",
            "uploaded_by_name",
            "origin_key",
            "is_deleted",
            "deleted_at",
            "created_at",
        ]
        read_only_fields = [
            "verification_status", "verified_by", "verified_at", "verification_comment",
            "id",
            "mime_type",
            "size_bytes",
            "sha256",
            "uploaded_by",
            "created_at",
            "origin_key",
            "is_deleted",
            "deleted_at",
            "category_code",
            "category_label",
            "uploaded_by_name",
            "related_type",
            "related_kind",
            "related_label",
            "related_path",
            "file_url",
        ]

    def get_uploaded_by_name(self, obj) -> str:
        user = obj.uploaded_by
        if not user:
            return ""
        return user.get_full_name() or user.get_username()

    def get_related_type(self, obj) -> str:
        ct = obj.content_type
        if not ct:
            return ""
        return f"{ct.app_label}.{ct.model}"

    def get_related_kind(self, obj) -> str:
        from .list_filters import related_kind_for

        ct = obj.content_type
        if not ct:
            return "OTHER"
        return related_kind_for(ct.app_label, ct.model)

    def get_related_label(self, obj) -> str:
        related = obj.related_object
        if related is None:
            return ""
        for attr in ("reference", "display_name", "name"):
            val = getattr(related, attr, None)
            if val:
                return str(val)
        return str(related)

    def get_related_path(self, obj) -> str | None:
        """Chemin SPA vers l'objet lié (évite les deep links cassés côté front)."""
        ct = obj.content_type
        if not ct or not obj.object_id:
            return None
        oid = str(obj.object_id)
        key = f"{ct.app_label}.{ct.model}"
        if key == "credits.creditapplication":
            return f"/dossiers/{oid}"
        if key == "guarantees.guaranteereleaserequest":
            return f"/mains-levees/{oid}"
        if key == "guarantees.dationrequest":
            return f"/dations/{oid}"
        if key == "guarantees.dationasset":
            related = obj.related_object
            dation_id = getattr(related, "dation_id", None) if related else None
            if dation_id:
                return f"/dations/{dation_id}"
            return None
        if key == "guarantees.guaranteeformalizationrequest":
            return f"/formalisations/{oid}"
        if key == "guarantees.guarantee":
            return f"/garanties/{oid}"
        if key == "collections.litigationfile":
            related = obj.related_object
            case_id = getattr(related, "case_id", None) if related else None
            if case_id:
                return f"/recouvrement/{case_id}/contentieux/{oid}"
            return None
        if key == "collections.collectioncase":
            return f"/recouvrement/{oid}"
        if key == "clients.client":
            return f"/clients/{oid}"
        if key == "sureties.surety":
            return f"/cautions/{oid}"
        if key == "credits.loan":
            related = obj.related_object
            app_id = getattr(related, "application_id", None) if related else None
            if app_id:
                return f"/dossiers/{app_id}"
            return "/prets"
        return None

    def get_file_url(self, obj) -> str | None:
        return file_download_url(obj.file) if obj.file else None

    def to_representation(self, instance):
        return presign_file_fields(
            super().to_representation(instance), instance, "file"
        )

    def validate_file(self, value):
        from apps.common.upload_validation import (
            resolve_tenant_from_context,
            validate_uploaded_file,
        )

        return validate_uploaded_file(
            value,
            tenant=resolve_tenant_from_context(self.context),
            check_quota=True,
        )
