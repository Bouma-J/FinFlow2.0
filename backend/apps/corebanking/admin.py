from django.contrib import admin

from .models import CoreBankingConnector, IntegrationLog


@admin.register(CoreBankingConnector)
class CoreBankingConnectorAdmin(admin.ModelAdmin):
    list_display = ["name", "protocol", "tenant", "is_active"]
    list_filter = ["protocol", "is_active", "tenant"]
    search_fields = ["name"]


@admin.register(IntegrationLog)
class IntegrationLogAdmin(admin.ModelAdmin):
    list_display = ["operation", "connector", "status", "attempts", "created_at", "tenant"]
    list_filter = ["status", "direction", "tenant"]
    search_fields = ["operation", "external_reference"]
