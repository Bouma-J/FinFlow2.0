from django.contrib import admin

from .models import (
    CollectionAction,
    CollectionCase,
    CollectionDialogueMessage,
    CollectionEscalationRule,
    CollectionStageHistory,
    CollectionTranche,
    LegalParty,
    LitigationCost,
    LitigationEvent,
    LitigationFile,
    LitigationSeizure,
    LoanRestructure,
    PaymentPromise,
    Repayment,
    WriteOff,
)


class ActionInline(admin.TabularInline):
    model = CollectionAction
    extra = 0
    readonly_fields = ["created_by", "updated_by", "created_at"]


class DialogueInline(admin.TabularInline):
    model = CollectionDialogueMessage
    extra = 0
    readonly_fields = ["created_by", "updated_by", "created_at"]
    fields = ["action", "kind", "body", "created_by", "created_at"]


class PromiseInline(admin.TabularInline):
    model = PaymentPromise
    extra = 0


class StageHistoryInline(admin.TabularInline):
    model = CollectionStageHistory
    extra = 0
    readonly_fields = [
        "from_stage", "to_stage", "reason", "automatic", "changed_by", "created_at",
    ]
    can_delete = False


@admin.register(CollectionCase)
class CollectionCaseAdmin(admin.ModelAdmin):
    list_display = [
        "loan", "tranche", "stage", "par_class", "days_overdue", "overdue_amount",
        "next_action_date", "assigned_to", "tenant",
    ]
    list_filter = ["tranche", "stage", "par_class", "tenant"]
    search_fields = [
        "loan__application__reference",
        "loan__core_banking_reference",
        "id",
    ]
    inlines = [ActionInline, DialogueInline, PromiseInline, StageHistoryInline]


@admin.register(Repayment)
class RepaymentAdmin(admin.ModelAdmin):
    list_display = ["loan", "amount", "payment_date", "created_by", "tenant"]
    list_filter = ["tenant"]


@admin.register(CollectionDialogueMessage)
class CollectionDialogueMessageAdmin(admin.ModelAdmin):
    list_display = ["case", "action", "kind", "created_by", "created_at", "tenant"]
    list_filter = ["kind", "tenant"]
    search_fields = ["body"]
    readonly_fields = ["created_by", "updated_by", "created_at", "updated_at"]


@admin.register(CollectionTranche)
class CollectionTrancheAdmin(admin.ModelAdmin):
    list_display = [
        "tenant",
        "position",
        "name",
        "min_days_overdue",
        "max_days_overdue",
        "owner_kind",
        "is_active",
    ]
    list_filter = ["tenant", "owner_kind", "is_active"]


@admin.register(CollectionEscalationRule)
class CollectionEscalationRuleAdmin(admin.ModelAdmin):
    list_display = [
        "tenant", "min_days_overdue", "target_stage", "is_active", "label",
    ]
    list_filter = ["tenant", "is_active", "target_stage"]


@admin.register(CollectionStageHistory)
class CollectionStageHistoryAdmin(admin.ModelAdmin):
    list_display = [
        "case", "from_stage", "to_stage", "automatic", "changed_by", "created_at",
    ]
    list_filter = ["automatic", "to_stage", "tenant"]


@admin.register(LegalParty)
class LegalPartyAdmin(admin.ModelAdmin):
    list_display = [
        "name", "party_type", "contact_name", "phone", "email", "is_active", "tenant",
    ]
    list_filter = ["party_type", "is_active", "tenant"]
    search_fields = ["name", "contact_name", "registration_no", "email"]


class LitigationEventInline(admin.TabularInline):
    model = LitigationEvent
    extra = 0
    autocomplete_fields = ["performed_by"]


class LitigationSeizureInline(admin.TabularInline):
    model = LitigationSeizure
    extra = 0
    autocomplete_fields = ["bailiff", "guarantee"]


class LitigationCostInline(admin.TabularInline):
    model = LitigationCost
    extra = 0
    autocomplete_fields = ["party"]


@admin.register(LitigationFile)
class LitigationFileAdmin(admin.ModelAdmin):
    list_display = [
        "title", "case", "case_reference", "court_name", "status",
        "hearing_date", "law_firm", "tenant",
    ]
    list_filter = ["status", "action_type", "tenant"]
    search_fields = ["title", "case_reference", "court_name", "lawyer", "bailiff"]
    autocomplete_fields = ["case", "law_firm", "lawyer_party", "bailiff_party"]
    filter_horizontal = ["related_guarantees"]
    inlines = [LitigationEventInline, LitigationSeizureInline, LitigationCostInline]


@admin.register(LitigationEvent)
class LitigationEventAdmin(admin.ModelAdmin):
    list_display = [
        "litigation", "event_type", "event_date", "location", "postponed", "tenant",
    ]
    list_filter = ["event_type", "postponed", "tenant"]
    search_fields = ["litigation__case_reference", "location", "comment"]
    autocomplete_fields = ["litigation", "performed_by"]


@admin.register(LitigationSeizure)
class LitigationSeizureAdmin(admin.ModelAdmin):
    list_display = [
        "litigation", "seizure_type", "status", "seizure_date", "amount", "bailiff",
        "tenant",
    ]
    list_filter = ["seizure_type", "status", "tenant"]
    search_fields = ["report_reference", "notes"]
    autocomplete_fields = ["litigation", "bailiff", "guarantee"]


@admin.register(LitigationCost)
class LitigationCostAdmin(admin.ModelAdmin):
    list_display = [
        "litigation", "cost_type", "label", "amount", "cost_date", "is_paid",
        "party", "tenant",
    ]
    list_filter = ["cost_type", "is_paid", "recoverable", "tenant"]
    search_fields = ["label", "notes"]
    autocomplete_fields = ["litigation", "party"]


@admin.register(LoanRestructure)
class LoanRestructureAdmin(admin.ModelAdmin):
    list_display = [
        "loan", "status", "origin", "request_kind", "effective_date",
        "new_duration_months", "outstanding_principal", "tenant",
    ]
    list_filter = ["status", "origin", "request_kind", "tenant"]


@admin.register(WriteOff)
class WriteOffAdmin(admin.ModelAdmin):
    list_display = [
        "loan", "status", "amount", "write_off_date", "approved_by", "tenant",
    ]
    list_filter = ["status", "tenant"]
