from django.contrib import admin

from .models import Client, ClientPhone


class ClientPhoneInline(admin.TabularInline):
    model = ClientPhone
    extra = 0
    fields = ["number", "label"]


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = [
        "display_name", "client_type", "reference",
        "tenant", "kyc_status", "is_active",
    ]
    list_filter = ["client_type", "kyc_status", "is_active", "tenant"]
    search_fields = ["reference", "first_name", "last_name", "company_name"]
    readonly_fields = ["reference"]
    inlines = [ClientPhoneInline]
