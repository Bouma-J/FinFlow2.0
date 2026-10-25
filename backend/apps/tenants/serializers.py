import json

from rest_framework import serializers

from .models import Agency, Tenant, TenantOfficer


class TenantOfficerSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantOfficer
        fields = [
            "id", "title", "last_name", "first_name", "phone", "ordering",
        ]
        read_only_fields = ["id"]


class OfficersField(serializers.Field):
    """Accepte une liste de responsables (JSON) via multipart ou JSON."""

    def to_representation(self, value):
        return TenantOfficerSerializer(value.all(), many=True).data

    def to_internal_value(self, data):
        if isinstance(data, str):
            data = data.strip()
            if not data:
                return []
            try:
                data = json.loads(data)
            except json.JSONDecodeError as exc:
                raise serializers.ValidationError(
                    "Format des responsables invalide."
                ) from exc
        if not isinstance(data, list):
            raise serializers.ValidationError(
                "Une liste de responsables est attendue."
            )
        items = []
        for idx, raw in enumerate(data):
            if not isinstance(raw, dict):
                continue
            title = str(raw.get("title") or "").strip()
            last_name = str(raw.get("last_name") or "").strip()
            first_name = str(raw.get("first_name") or "").strip()
            phone = str(raw.get("phone") or "").strip()
            if not (title or last_name or first_name or phone):
                continue
            if not title:
                raise serializers.ValidationError(
                    "L'intitulé du poste est obligatoire pour chaque responsable."
                )
            if not last_name:
                raise serializers.ValidationError(
                    f"Le nom est obligatoire pour « {title} »."
                )
            items.append(
                {
                    "title": title,
                    "last_name": last_name,
                    "first_name": first_name,
                    "phone": phone,
                    "ordering": idx,
                }
            )
        return items


class TenantSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    officers = OfficersField(required=False)

    class Meta:
        model = Tenant
        fields = [
            "id", "code", "name", "country", "zone", "currency",
            "timezone", "is_active", "address", "phone", "email",
            "logo", "logo_url", "brand_primary", "brand_secondary",
            "brand_accent", "brand_sidebar", "brand_sidebar_text", "ged_quota_bytes", "ged_used_bytes",
            "officers", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "logo_url", "ged_used_bytes", "created_at", "updated_at",
        ]

    def get_logo_url(self, obj):
        from apps.common.storage_urls import tenant_logo_url

        return tenant_logo_url(obj, self.context.get("request"))

    def validate(self, attrs):
        # Les anciennes variantes foncées sont conservées tant que la couleur
        # principale ne change pas. Les nouvelles chartes dérivent leur nuance.
        primary = attrs.get("brand_primary")
        if primary and "brand_secondary" not in attrs and (
            self.instance is None or primary.lower() != self.instance.brand_primary.lower()
        ):
            from .branding import secondary_from_primary
            attrs["brand_secondary"] = secondary_from_primary(primary)
        return attrs

    def validate_logo(self, value):
        if not value:
            return value
        from apps.common.upload_validation import validate_uploaded_file

        return validate_uploaded_file(
            value, tenant=self.instance, check_quota=False
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Évite l'URL MinIO brute (AccessDenied) : même proxy que logo_url.
        data["logo"] = self.get_logo_url(instance)
        return data

    def _save_officers(self, tenant, officers):
        if officers is None:
            return
        tenant.officers.all().delete()
        for item in officers:
            TenantOfficer.objects.create(tenant=tenant, **item)

    def create(self, validated_data):
        officers = validated_data.pop("officers", None)
        tenant = super().create(validated_data)
        self._save_officers(tenant, officers)
        return tenant

    def update(self, instance, validated_data):
        officers = validated_data.pop("officers", None)
        tenant = super().update(instance, validated_data)
        self._save_officers(tenant, officers)
        return tenant


class PublicTenantBrandingSerializer(serializers.ModelSerializer):
    """Données publiques pour l'écran de connexion (logo + charte)."""

    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = [
            "id",
            "code",
            "name",
            "logo_url",
            "brand_primary",
            "brand_secondary",
            "brand_accent",
            "brand_sidebar",
            "brand_sidebar_text",
        ]
        read_only_fields = fields

    def get_logo_url(self, obj):
        from apps.common.storage_urls import tenant_logo_url

        return tenant_logo_url(obj, self.context.get("request"))


class AgencySerializer(serializers.ModelSerializer):
    manager_display_name = serializers.CharField(read_only=True)

    class Meta:
        model = Agency
        fields = [
            "id", "tenant", "code", "name", "region",
            "address", "is_active",
            "manager_last_name", "manager_first_name", "manager_phone",
            "manager_display_name",
            "cbs_point_of_service_id",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "tenant", "manager_display_name", "created_at", "updated_at",
        ]

    def validate_cbs_point_of_service_id(self, value):
        from apps.catalog.cbs_validation import validate_service_point_id

        tenant_id = None
        if self.instance is not None:
            tenant_id = self.instance.tenant_id
        return validate_service_point_id(value, tenant_id=tenant_id)
