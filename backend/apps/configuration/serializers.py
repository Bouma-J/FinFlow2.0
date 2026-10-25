from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .catalog import validate_overrides
from .models import ConfigurationProfile
from .governance import validate_locks


class ConfigurationProfileSerializer(serializers.ModelSerializer):
    product_label = serializers.CharField(source="product.label", read_only=True, default="")
    agency_label = serializers.CharField(source="agency.name", read_only=True, default="")
    updated_by_display = serializers.SerializerMethodField()
    published_by_display = serializers.SerializerMethodField()

    def get_updated_by_display(self, obj):
        return str(obj.updated_by) if obj.updated_by_id else ""

    def get_published_by_display(self, obj):
        return str(obj.published_by) if obj.published_by_id else ""

    class Meta:
        model = ConfigurationProfile
        fields = ["id", "code", "name", "version", "status", "locked_keys", "product", "product_label",
                  "agency", "agency_label", "client_type", "individual_profile", "effective_from",
                  "overrides", "reason", "submitted_at", "published_at", "published_by_display",
                  "retired_at", "retirement_reason", "updated_by_display", "created_at", "updated_at"]
        read_only_fields = ["id", "version", "status", "submitted_at", "published_at", "retired_at",
                            "retirement_reason", "created_at", "updated_at"]
        validators = []  # L'unicité et l'allocation des versions sont gérées sous verrou.

    def validate_overrides(self, value):
        try:
            return validate_overrides(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc

    def validate(self, attrs):
        tenant_id = self.context["tenant_id"]
        for key in ("product", "agency"):
            obj = attrs.get(key, getattr(self.instance, key, None))
            if obj and tenant_id is None:
                raise serializers.ValidationError({key: "Le socle Groupe ne référence pas les produits ou agences d'une filiale."})
            if obj and str(obj.tenant_id) != str(tenant_id):
                raise serializers.ValidationError({key: "Cette référence appartient à une autre filiale."})
        client_type = attrs.get("client_type", getattr(self.instance, "client_type", ""))
        profile = attrs.get("individual_profile", getattr(self.instance, "individual_profile", ""))
        if profile and client_type != "INDIVIDUAL":
            raise serializers.ValidationError({"individual_profile": "Sélectionnez le type Personne physique."})
        overrides = attrs.get("overrides", getattr(self.instance, "overrides", {}))
        attrs["locked_keys"] = validate_locks(attrs.get("locked_keys", getattr(self.instance, "locked_keys", [])),
                                              overrides, group=tenant_id is None)
        return attrs
