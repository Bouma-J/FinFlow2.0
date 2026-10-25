from django.contrib import admin

from .models import Surety, SuretyEngagement, SuretyPhone


class EngagementInline(admin.TabularInline):
    model = SuretyEngagement
    extra = 0


class SuretyPhoneInline(admin.TabularInline):
    model = SuretyPhone
    extra = 0
    fields = ["number", "label"]


@admin.register(Surety)
class SuretyAdmin(admin.ModelAdmin):
    list_display = ["name", "surety_type", "phone", "tenant", "is_active"]
    list_filter = ["surety_type", "is_active", "tenant"]
    search_fields = [
        "name", "first_name", "last_name", "identifier", "national_id",
        "company_name", "ifu", "rccm",
    ]
    inlines = [SuretyPhoneInline, EngagementInline]
