from django.contrib import admin

from .models import (
    DationAsset,
    DationFee,
    DationRequest,
    Guarantee,
    GuaranteeJewelryItem,
    GuaranteeMovement,
    GuaranteePhoto,
    GuaranteeReleaseRequest,
    ReleaseFee,
)


class MovementInline(admin.TabularInline):
    model = GuaranteeMovement
    extra = 0


class GuaranteePhotoInline(admin.TabularInline):
    model = GuaranteePhoto
    extra = 0
    fields = ["image", "caption"]


class JewelryItemInline(admin.TabularInline):
    model = GuaranteeJewelryItem
    extra = 0
    fields = ["nature", "weight", "description"]


@admin.register(Guarantee)
class GuaranteeAdmin(admin.ModelAdmin):
    list_display = [
        "reference", "guarantee_type", "pledge_category", "client",
        "current_value", "status", "tenant",
    ]
    list_filter = ["guarantee_type", "pledge_category", "status", "tenant"]
    search_fields = ["reference", "document_number", "registration", "isin_code"]
    readonly_fields = ["current_value", "ltv_ratio"]
    inlines = [JewelryItemInline, GuaranteePhotoInline, MovementInline]


class ReleaseFeeInline(admin.TabularInline):
    model = ReleaseFee
    extra = 0
    fields = ["fee_type", "label", "amount", "payer", "fee_date", "recoverable"]


@admin.register(GuaranteeReleaseRequest)
class GuaranteeReleaseRequestAdmin(admin.ModelAdmin):
    list_display = [
        "reference",
        "guarantee",
        "status",
        "acte_status",
        "cbs_settled",
        "cbs_loan_reference",
        "tenant",
    ]
    list_filter = ["status", "acte_status", "tenant"]
    search_fields = ["reference", "cbs_loan_reference"]
    inlines = [ReleaseFeeInline]


class DationAssetInline(admin.TabularInline):
    model = DationAsset
    extra = 0
    fields = ["source", "asset_type", "guarantee", "description", "value", "notes"]


class DationFeeInline(admin.TabularInline):
    model = DationFee
    extra = 0
    fields = [
        "fee_type", "label", "amount", "payer", "fee_date", "recoverable", "asset",
    ]


@admin.register(DationRequest)
class DationRequestAdmin(admin.ModelAdmin):
    list_display = [
        "reference",
        "client",
        "status",
        "cbs_total_outstanding",
        "claim_to_cover",
        "residual_balance",
        "tenant",
    ]
    list_filter = ["status", "tenant"]
    search_fields = ["reference", "cbs_client_id"]
    inlines = [DationAssetInline, DationFeeInline]
