from django.contrib import admin

from .models import NotificationLog, TenantNotificationSettings


@admin.register(TenantNotificationSettings)
class TenantNotificationSettingsAdmin(admin.ModelAdmin):
    list_display = [
        "tenant",
        "enabled",
        "notify_on_step",
        "notify_on_completion",
        "notify_collection_email",
        "notify_collection_transfer",
        "from_email",
    ]
    list_filter = [
        "enabled",
        "notify_on_step",
        "notify_on_completion",
        "notify_collection_email",
        "notify_collection_transfer",
        "notify_collection_dialogue",
    ]


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ["subject", "kind", "status", "tenant", "created_at"]
    list_filter = ["kind", "status", "tenant"]
    search_fields = ["subject", "error_message"]
    readonly_fields = [
        "tenant",
        "kind",
        "status",
        "subject",
        "recipients",
        "body_preview",
        "error_message",
        "workflow_instance_id",
        "approval_task_id",
        "created_at",
        "updated_at",
    ]
