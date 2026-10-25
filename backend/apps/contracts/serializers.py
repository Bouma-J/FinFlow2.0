import json

from rest_framework import serializers

from apps.common.storage_urls import presign_file_fields

from .models import ContractTemplate, GeneratedContract


class JSONOrStringField(serializers.JSONField):
    """JSONField tolérant : accepte aussi une chaîne JSON (envois multipart)."""

    def to_internal_value(self, data):
        if isinstance(data, str):
            if data.strip() == "":
                return []
            try:
                return json.loads(data)
            except ValueError:
                self.fail("invalid")
        return super().to_internal_value(data)


class ContractTemplateSerializer(serializers.ModelSerializer):
    extra_fields = JSONOrStringField(required=False)
    category_display = serializers.CharField(
        source="get_category_display", read_only=True
    )
    applies_to_display = serializers.CharField(
        source="get_applies_to_display", read_only=True
    )
    product_label = serializers.CharField(
        source="product.label", read_only=True
    )

    class Meta:
        model = ContractTemplate
        fields = [
            "id", "code", "name", "category", "category_display",
            "description", "engine", "file",
            "applies_to", "applies_to_display", "product", "product_label",
            "amount_min", "amount_max", "extra_fields",
            "is_required", "is_active", "ordering", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

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
            check_quota=False,
            allowed_extensions=["docx", "xlsx"],
        )

    def validate(self, attrs):
        # Déduit le moteur à partir de l'extension du fichier importé.
        file = attrs.get("file")
        if file is not None:
            name = (file.name or "").lower()
            attrs["engine"] = (
                ContractTemplate.Engine.XLSX
                if name.endswith(".xlsx")
                else ContractTemplate.Engine.DOCX
            )
        return attrs


class GeneratedContractSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )
    created_by_name = serializers.CharField(
        source="created_by.get_full_name", read_only=True
    )

    class Meta:
        model = GeneratedContract
        fields = [
            "id", "application", "surety_engagement", "template", "template_name",
            "category", "file", "status", "status_display", "signed_file",
            "signed_at", "notes", "extra_values", "created_by_name", "created_at",
        ]
        read_only_fields = [
            "id", "template_name", "category", "file", "context_snapshot",
            "created_by_name", "created_at",
        ]

    def to_representation(self, instance):
        return presign_file_fields(
            super().to_representation(instance),
            instance,
            "file",
            "signed_file",
        )


class GenerateContractSerializer(serializers.Serializer):
    """Payload de génération d'un contrat pour un dossier."""

    application = serializers.UUIDField()
    template = serializers.UUIDField()
    extra_values = serializers.DictField(required=False, default=dict)
    surety_engagement = serializers.UUIDField(required=False, allow_null=True)


class SignedContractUploadSerializer(serializers.Serializer):
    signed_file = serializers.FileField()
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_signed_file(self, value):
        from apps.common.upload_validation import (
            resolve_tenant_from_context,
            validate_uploaded_file,
        )

        return validate_uploaded_file(
            value,
            tenant=resolve_tenant_from_context(self.context),
            check_quota=True,
            allowed_extensions=["pdf", "jpg", "jpeg", "png"],
        )
