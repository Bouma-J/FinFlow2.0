import json
from copy import copy

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone

from rest_framework import serializers

from .models import Client, ClientPhone


class ClientPhoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientPhone
        fields = ["id", "number", "label"]


class PhonesInputField(serializers.Field):
    """
    Accepte une liste de numéros additionnels, transmise soit en JSON natif
    (application/json), soit sous forme de chaîne JSON (multipart/form-data).
    Chaque élément peut être une chaîne ("+225…") ou un objet
    {"number": "+225…", "label": "Mobile"}.
    """

    def to_representation(self, value):
        return value

    def to_internal_value(self, data):
        if isinstance(data, str):
            try:
                data = json.loads(data or "[]")
            except json.JSONDecodeError:
                raise serializers.ValidationError("Format JSON invalide.")
        if not isinstance(data, list):
            raise serializers.ValidationError("Une liste est attendue.")
        result = []
        for item in data:
            if isinstance(item, str):
                number = item.strip()
                label = ""
            elif isinstance(item, dict):
                number = str(item.get("number", "")).strip()
                label = str(item.get("label", "")).strip()
            else:
                continue
            if number:
                result.append({"number": number, "label": label})
        return result


class ClientListSerializer(serializers.ModelSerializer):
    """Liste allégée — sans scans ni détails KYC complets."""

    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = Client
        fields = [
            "id", "reference", "client_type", "display_name", "agency",
            "phone", "email", "city", "kyc_status", "is_active",
            "cbs_client_id", "cbs_account_number",
            "cbs_point_of_service_name", "cbs_credit_limit",
            "created_at",
        ]
        read_only_fields = fields


class ClientSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)
    phones = ClientPhoneSerializer(many=True, read_only=True)
    additional_phones = PhonesInputField(write_only=True, required=False)
    configuration_application = serializers.UUIDField(write_only=True, required=False)

    def get_fields(self):
        fields = super().get_fields()
        for key in ("civility", "marital_status", "id_document_type", "manager_id_document_type", "legal_form"):
            fields[key] = serializers.CharField(required=False, allow_blank=True, max_length=Client._meta.get_field(key).max_length)
        return fields

    class Meta:
        model = Client
        fields = [
            "id", "reference", "client_type", "display_name", "agency",
            # Personne physique
            "civility", "first_name", "last_name", "birth_date",
            "birth_country", "country", "marital_status", "nationality",
            "profession",
            "id_document_type", "national_id", "id_document_issue_date",
            "id_document_expiry_date", "id_document_scan", "photo",
            # Conjoint
            "spouse_last_name", "spouse_first_name", "spouse_phone",
            "spouse_profession",
            # Parents
            "father_last_name", "father_first_name",
            "mother_last_name", "mother_first_name",
            # Personne morale
            "company_name", "sigle", "legal_form", "ifu", "rccm",
            "ifu_scan", "rccm_scan",
            "manager_last_name", "manager_first_name", "manager_phone",
            "manager_email", "manager_address", "manager_id_document_type",
            "manager_id_document_number", "manager_id_document_issue_date",
            "manager_id_document_expiry_date", "manager_id_document_scan",
            "manager_position", "manager_birth_date", "manager_birth_country",
            "manager_birth_city",
            # Coordonnées communes
            "phone", "email", "address", "city", "postal_box", "head_office",
            "phones", "additional_phones",
            # Core Banking (mapping 1:1 situation adhérent)
            "cbs_client_id", "cbs_account_number", "cbs_full_name",
            "cbs_order_number", "cbs_profession_id", "cbs_nationality_id",
            "cbs_sector_id", "cbs_client_type_id", "cbs_zone_id",
            "cbs_savings_product_id", "cbs_signature_count", "cbs_distance",
            "cbs_registration_date", "cbs_creation_date", "cbs_credit_limit",
            "cbs_est_valide", "cbs_point_of_service_id",
            "cbs_point_of_service_name", "cbs_external_id",
            "cbs_context", "cbs_message", "cbs_synced_at", "cbs_situation",
            # KYC / statut
            "kyc_status", "kyc_validated_at", "is_active", "custom_fields", "configuration_application",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "reference", "is_active", "created_at", "updated_at", "kyc_validated_at",
            "cbs_full_name", "cbs_order_number", "cbs_profession_id",
            "cbs_nationality_id", "cbs_sector_id", "cbs_client_type_id",
            "cbs_zone_id", "cbs_savings_product_id", "cbs_signature_count",
            "cbs_distance", "cbs_registration_date", "cbs_creation_date",
            "cbs_credit_limit", "cbs_est_valide",
            "cbs_point_of_service_id", "cbs_point_of_service_name",
            "cbs_external_id", "cbs_context", "cbs_message",
            "cbs_synced_at", "cbs_situation",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Remplace les URLs MinIO brutes (AccessDenied navigateur) par le proxy API.
        from apps.common.storage_urls import CLIENT_FILE_FIELDS, client_file_url

        request = self.context.get("request")
        for field in CLIENT_FILE_FIELDS:
            data[field] = client_file_url(instance, field, request=request)
        return data

    def validate(self, attrs):
        from apps.common.upload_validation import validate_attrs_uploads

        attrs = validate_attrs_uploads(attrs, self.context, check_quota=True)
        client_type = attrs.get("client_type") or getattr(
            self.instance, "client_type", None
        )
        if client_type in (
            Client.ClientType.CORPORATE,
            Client.ClientType.PROFESSIONAL,
        ):
            if not (
                attrs.get("company_name")
                or getattr(self.instance, "company_name", "")
            ):
                raise serializers.ValidationError(
                    {
                        "company_name": (
                            "Obligatoire pour une personne morale ou un groupement."
                        )
                    }
                )
        else:
            has_name = attrs.get("last_name") or getattr(
                self.instance, "last_name", ""
            )
            if not has_name:
                raise serializers.ValidationError(
                    {"last_name": "Obligatoire pour une personne physique."}
                )
        from apps.common.tenancy import get_current_tenant_id
        from apps.configuration.forms_catalog import validate_custom_values
        from .compliance import client_configuration, dossier_configuration, kyc_failures

        configuration_application = attrs.pop("configuration_application", None)
        candidate = copy(self.instance) if self.instance else Client(tenant_id=get_current_tenant_id())
        for key, value in attrs.items():
            if key != "additional_phones":
                setattr(candidate, key, value)
        if not candidate.agency_id:
            candidate.agency = getattr(getattr(self.context.get("request"), "user", None), "agency", None)
        config = dossier_configuration(self.context.get("request"), getattr(self.instance, "pk", None), configuration_application) if configuration_application else client_configuration(candidate)
        for key in ("civility", "marital_status", "id_document_type", "manager_id_document_type", "legal_form"):
            if key not in attrs or not attrs[key] or self.instance and attrs[key] == getattr(self.instance, key):
                continue
            reference = "id_document_type" if key == "manager_id_document_type" else key
            if attrs[key] not in {entry["code"] for entry in config["references"][reference] if entry["active"]}:
                raise serializers.ValidationError({key: "Code inconnu ou désactivé dans les référentiels applicables."})
        if "custom_fields" in attrs:
            try:
                attrs["custom_fields"] = validate_custom_values(config["forms"]["client_fields"], attrs["custom_fields"],
                    previous=getattr(self.instance, "custom_fields", {}) or {})
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"custom_fields": exc.messages}) from exc
            candidate.custom_fields = attrs["custom_fields"]
        if candidate.kyc_status == "VALIDATED":
            if not self.instance or self.instance.kyc_status != "VALIDATED" or attrs.get("kyc_status") == "VALIDATED":
                candidate.kyc_validated_at = timezone.localdate()
                attrs["kyc_validated_at"] = candidate.kyc_validated_at
            failures = kyc_failures(candidate, configuration=config)
            if failures:
                raise serializers.ValidationError({"kyc_status": failures})
        return attrs

    def _sync_phones(self, client, phones):
        for entry in phones:
            ClientPhone.objects.create(
                client=client, number=entry["number"], label=entry.get("label", "")
            )

    def create(self, validated_data):
        phones = validated_data.pop("additional_phones", None)
        client = super().create(validated_data)
        if phones:
            self._sync_phones(client, phones)
        return client

    def update(self, instance, validated_data):
        phones = validated_data.pop("additional_phones", None)
        client = super().update(instance, validated_data)
        if phones is not None:
            instance.phones.all().delete()
            self._sync_phones(client, phones)
        return client
