from django.contrib import admin

from .models import (
    ChecklistItem,
    CreditProduct,
    Currency,
    LoanPeriodicity,
    ProductCategory,
    RejectReason,
    RepaymentMethod,
)


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ["code", "label", "tenant", "is_active"]
    list_filter = ["is_active", "tenant"]
    search_fields = ["code", "label"]


@admin.register(CreditProduct)
class CreditProductAdmin(admin.ModelAdmin):
    list_display = [
        "code", "label", "category", "currency", "cbs_product_code",
        "interest_rate", "is_active",
    ]
    list_filter = ["is_active", "client_type", "tenant"]
    search_fields = ["code", "label", "cbs_product_code"]


@admin.register(RejectReason)
class RejectReasonAdmin(admin.ModelAdmin):
    list_display = ["code", "label", "tenant", "is_active"]
    list_filter = ["is_active", "tenant"]


@admin.register(LoanPeriodicity)
class LoanPeriodicityAdmin(admin.ModelAdmin):
    list_display = [
        "code", "label", "cbs_code", "periods_per_year",
        "sort_order", "tenant", "is_active",
    ]
    list_filter = ["is_active", "tenant"]
    search_fields = ["code", "label", "cbs_code"]


@admin.register(RepaymentMethod)
class RepaymentMethodAdmin(admin.ModelAdmin):
    list_display = [
        "code", "label", "cbs_code", "sort_order", "tenant", "is_active",
    ]
    list_filter = ["is_active", "tenant"]
    search_fields = ["code", "label", "cbs_code"]


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = [
        "code", "label", "cbs_code", "sort_order", "tenant", "is_active",
    ]
    list_filter = ["is_active", "tenant"]
    search_fields = ["code", "label", "cbs_code"]


@admin.register(ChecklistItem)
class ChecklistItemAdmin(admin.ModelAdmin):
    list_display = ["label", "product", "is_mandatory", "order"]
    list_filter = ["is_mandatory", "tenant"]
