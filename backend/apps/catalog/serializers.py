from rest_framework import serializers

from .models import (
    CbsProductReference,
    CbsManager,
    CbsProfession,
    ChecklistItem,
    CreditProduct,
    Currency,
    DecisionMotif,
    FinancingObject,
    FinancingSource,
    LoanPeriodicity,
    ProductCategory,
    RejectReason,
    RepaymentMethod,
    ServicePoint,
)


class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ["id", "code", "label", "description", "is_active"]
        read_only_fields = ["id"]


class CreditProductSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="category.label", read_only=True)

    class Meta:
        model = CreditProduct
        fields = [
            "id", "code", "label", "description", "category", "category_label",
            "client_type", "currency", "amount_min", "amount_max",
            "duration_min_months", "duration_max_months", "interest_rate",
            "processing_fee_rate", "requires_guarantee",
            "cbs_product_code", "cbs_repayment_product_code",
            "cbs_credit_product", "cbs_repayment_product",
            "is_active",
        ]
        read_only_fields = ["id", "cbs_product_code", "cbs_repayment_product_code", "cbs_repayment_product"]

    def validate(self, attrs):
        for field in ("cbs_product_code", "cbs_repayment_product_code", "cbs_repayment_product"):
            attr = field + "_id" if field in {"cbs_credit_product", "cbs_repayment_product"} else field
            if field in self.initial_data and str(self.initial_data[field] or "") != str(getattr(self.instance, attr, "") or ""):
                raise serializers.ValidationError({field: "Sélectionnez un produit crédit CBS confirmé ; les codes historiques ne remplacent pas les correspondances du dossier."})
        from apps.common.tenancy import get_current_tenant_id
        from apps.corebanking.services import resolve_active_connector, CoreBankingError

        ref = attrs.get("cbs_credit_product", getattr(self.instance, "cbs_credit_product", None))
        if ref:
            tid = get_current_tenant_id()
            try:
                connector = resolve_active_connector(tid)
            except CoreBankingError:
                connector = None
            currency = attrs.get("currency", getattr(self.instance, "currency", ""))
            if (str(ref.tenant_id) != str(tid) or ref.kind != "CREDIT" or not ref.is_active
                    or ref.verification_status != "VERIFIED" or not ref.verified_at or not ref.verified_by_id
                    or not ref.source_reference.strip() or not connector or ref.connector_id != connector.pk
                    or (ref.currency and ref.currency != currency)):
                raise serializers.ValidationError({"cbs_credit_product": "Sélectionnez une référence crédit active, confirmée et compatible avec cette filiale, ce connecteur et cette devise."})
        amount_min = attrs.get("amount_min")
        amount_max = attrs.get("amount_max")
        if amount_min is not None and amount_max is not None and amount_min > amount_max:
            raise serializers.ValidationError(
                "Le montant minimum ne peut excéder le montant maximum."
            )
        return attrs

class CbsProductReferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = CbsProductReference
        fields = ["id", "connector", "kind", "cbs_code", "label", "currency", "source_reference", "is_active", "verification_status", "verified_at", "verified_by", "updated_at"]
        read_only_fields = ["id", "verification_status", "verified_at", "verified_by", "updated_at"]

    def validate(self, attrs):
        from apps.common.tenancy import get_current_tenant_id
        from .models import Currency

        tid = get_current_tenant_id()
        connector = attrs.get("connector", getattr(self.instance, "connector", None))
        if not connector or str(connector.tenant_id) != str(tid):
            raise serializers.ValidationError({"connector": "Le connecteur doit appartenir à la filiale sélectionnée."})
        currency = attrs.get("currency", getattr(self.instance, "currency", ""))
        if currency and not Currency.all_tenants.filter(tenant_id=tid, code=currency, is_active=True).exists():
            raise serializers.ValidationError({"currency": "Sélectionnez une devise active de cette filiale."})
        for field in ("cbs_code", "label", "source_reference"):
            value = attrs.get(field, getattr(self.instance, field, ""))
            if not value.strip():
                raise serializers.ValidationError({field: "Ce champ est obligatoire."})
        kind = attrs.get("kind", getattr(self.instance, "kind", None))
        cbs_code = attrs.get("cbs_code", getattr(self.instance, "cbs_code", ""))
        duplicates = CbsProductReference.all_tenants.filter(tenant_id=tid, connector=connector, kind=kind, cbs_code=cbs_code)
        if self.instance:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError({"cbs_code": "Cet identifiant existe déjà pour ce connecteur et ce type de produit."})
        return attrs

    def update(self, instance, validated_data):
        protected = ("connector", "kind", "cbs_code", "currency", "source_reference", "is_active")
        if any(k in validated_data and validated_data[k] != getattr(instance, k) for k in protected):
            validated_data.update(verification_status="PENDING", verified_at=None, verified_by=None)
        return super().update(instance, validated_data)


class RejectReasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = RejectReason
        fields = ["id", "code", "label", "description", "is_active"]
        read_only_fields = ["id"]


class LoanPeriodicitySerializer(serializers.ModelSerializer):
    class Meta:
        model = LoanPeriodicity
        fields = [
            "id", "code", "label", "description", "cbs_code",
            "periods_per_year", "sort_order", "is_active",
        ]
        read_only_fields = fields


class RepaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = RepaymentMethod
        fields = [
            "id", "code", "label", "description", "cbs_code",
            "sort_order", "is_active",
        ]
        read_only_fields = ["id"]


class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = [
            "id", "code", "label", "description", "cbs_code",
            "sort_order", "is_active",
        ]
        read_only_fields = fields


class FinancingObjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancingObject
        fields = [
            "id", "code", "label", "description", "cbs_code",
            "purpose_type", "sort_order", "is_active",
        ]
        read_only_fields = fields


class ServicePointSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServicePoint
        fields = [
            "id", "code", "label", "description", "cbs_code",
            "sort_order", "is_active",
        ]
        read_only_fields = fields


class CbsManagerSerializer(serializers.ModelSerializer):
    class Meta:
        model = CbsManager
        fields = [
            "id", "code", "label", "description", "cbs_code",
            "sort_order", "is_active",
        ]
        read_only_fields = fields


class FinancingSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancingSource
        fields = [
            "id", "code", "label", "description", "cbs_code",
            "sort_order", "is_active",
        ]
        read_only_fields = fields


class DecisionMotifSerializer(serializers.ModelSerializer):
    class Meta:
        model = DecisionMotif
        fields = [
            "id", "code", "label", "description", "cbs_code",
            "sort_order", "is_active",
        ]
        read_only_fields = fields


class CbsProfessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CbsProfession
        fields = [
            "id", "code", "label", "description", "cbs_code",
            "sort_order", "is_active",
        ]
        read_only_fields = fields


class ChecklistItemSerializer(serializers.ModelSerializer):
    product_label = serializers.CharField(
        source="product.label", read_only=True, default=""
    )

    class Meta:
        model = ChecklistItem
        fields = [
            "id", "product", "product_label", "label", "is_mandatory", "order",
        ]
        read_only_fields = ["id", "product_label"]
