from django.contrib import admin

from .models import Agency, Tenant, TenantOfficer


class TenantOfficerInline(admin.TabularInline):
    model = TenantOfficer
    extra = 0
    fields = ["title", "last_name", "first_name", "phone", "ordering"]


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    exclude = ["brand_secondary"]
    list_display = ["code", "name", "country", "zone", "currency", "is_active"]
    list_filter = ["is_active", "country", "zone"]
    search_fields = ["code", "name"]
    inlines = [TenantOfficerInline]

    def save_model(self, request, obj, form, change):
        if not change or "brand_primary" in form.changed_data:
            from .branding import secondary_from_primary
            obj.brand_secondary = secondary_from_primary(obj.brand_primary)
        super().save_model(request, obj, form, change)


@admin.register(Agency)
class AgencyAdmin(admin.ModelAdmin):
    list_display = [
        "code", "name", "tenant", "region",
        "manager_last_name", "is_active",
    ]
    list_filter = ["is_active", "tenant", "region"]
    search_fields = [
        "code", "name", "manager_last_name", "manager_first_name",
    ]
