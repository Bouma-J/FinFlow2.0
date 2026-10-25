from django.contrib import admin

from .models import (
    AnalysisThreshold,
    CreditApplication,
    CreditDocument,
    CreditInstructionPolicy,
    FieldVisit,
    FinancialAnalysis,
    Installment,
    Loan,
    StockPhoto,
)


class FinancialAnalysisInline(admin.StackedInline):
    model = FinancialAnalysis
    extra = 0


class StockPhotoInline(admin.TabularInline):
    model = StockPhoto
    extra = 0
    fields = ["image", "caption"]


class CreditDocumentInline(admin.TabularInline):
    model = CreditDocument
    extra = 0
    fields = ["label", "file"]


@admin.register(CreditApplication)
class CreditApplicationAdmin(admin.ModelAdmin):
    list_display = [
        "reference", "client", "product", "amount_requested",
        "status", "tenant", "created_at",
    ]
    list_filter = ["status", "currency", "periodicity", "tenant"]
    search_fields = ["reference"]
    readonly_fields = ["reference", "last_due_date"]
    inlines = [FinancialAnalysisInline, StockPhotoInline, CreditDocumentInline]


class InstallmentInline(admin.TabularInline):
    model = Installment
    extra = 0


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = [
        "application", "principal", "interest_rate",
        "duration_months", "status", "tenant",
    ]
    list_filter = ["status", "tenant"]
    inlines = [InstallmentInline]


@admin.register(FieldVisit)
class FieldVisitAdmin(admin.ModelAdmin):
    list_display = ["application", "visit_date", "visited_by", "tenant"]
    list_filter = ["tenant"]


class PublishedConfigurationReadOnlyAdmin(admin.ModelAdmin):
    """Toute évolution des paramètres passe par le centre et ses quatre yeux."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AnalysisThreshold)
class AnalysisThresholdAdmin(PublishedConfigurationReadOnlyAdmin):
    list_display = [
        "tenant", "max_debt_ratio", "min_dscr", "max_gearing",
        "min_guarantee_coverage", "stress_pct",
        "haircut_mortgage", "haircut_vehicle", "haircut_jewelry",
    ]
    list_filter = ["tenant"]
    fields = [
        "tenant",
        "max_debt_ratio", "min_dscr", "max_leverage_ratio",
        "min_living_wage_per_capita", "min_interest_coverage",
        "max_gearing", "min_financial_autonomy", "min_current_ratio",
        "min_guarantee_coverage", "stress_pct",
        "transferable_quota_fraction", "informal_income_weight",
        "haircut_mortgage", "haircut_vehicle", "haircut_jewelry",
        "haircut_financial_deposit", "haircut_financial_security",
        "haircut_other",
    ]


@admin.register(CreditInstructionPolicy)
class CreditInstructionPolicyAdmin(PublishedConfigurationReadOnlyAdmin):
    list_display = [
        "tenant",
        "collateral_coverage_mode",
        "require_field_visit",
        "kyc_gate",
        "amount_approved_mode",
        "enable_cancel_status",
    ]
    list_filter = ["tenant", "collateral_coverage_mode"]
