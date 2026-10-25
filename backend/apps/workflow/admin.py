from django.contrib import admin

from .models import (
    ApprovalCondition,
    ApprovalStep,
    ApprovalTask,
    WorkflowDefinition,
    WorkflowInstance,
)


class ApprovalStepInline(admin.TabularInline):
    model = ApprovalStep
    extra = 1


@admin.register(WorkflowDefinition)
class WorkflowDefinitionAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "version", "target_type", "tenant", "is_active"]
    list_filter = ["is_active", "target_type", "tenant"]
    inlines = [ApprovalStepInline]


@admin.register(WorkflowInstance)
class WorkflowInstanceAdmin(admin.ModelAdmin):
    list_display = ["definition", "status", "current_order", "amount", "tenant"]
    list_filter = ["status", "tenant"]


@admin.register(ApprovalTask)
class ApprovalTaskAdmin(admin.ModelAdmin):
    list_display = ["instance", "step", "status", "opinion", "acted_by", "acted_at", "due_at"]
    list_filter = ["status", "opinion", "tenant"]


@admin.register(ApprovalCondition)
class ApprovalConditionAdmin(admin.ModelAdmin):
    list_display = ["application", "description", "status", "issued_by", "issued_at"]
    list_filter = ["status", "tenant"]
