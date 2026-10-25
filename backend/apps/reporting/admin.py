from django.contrib import admin

from .models import ReportingSnapshot


@admin.register(ReportingSnapshot)
class ReportingSnapshotAdmin(admin.ModelAdmin):
    list_display = ["scope", "kind", "tenant", "params_hash", "computed_at"]
    list_filter = ["scope", "kind"]
    readonly_fields = ["id", "computed_at", "payload"]
