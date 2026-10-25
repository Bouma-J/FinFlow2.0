from django.contrib import admin

from .models import ContractTemplate, GeneratedContract


@admin.register(ContractTemplate)
class ContractTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "name", "category", "engine", "applies_to",
        "is_required", "is_active", "ordering", "tenant",
    )
    list_filter = ("category", "engine", "applies_to", "is_required", "is_active")
    search_fields = ("name", "code", "description")


@admin.register(GeneratedContract)
class GeneratedContractAdmin(admin.ModelAdmin):
    list_display = (
        "template_name", "application", "status", "signed_at", "created_at", "tenant",
    )
    list_filter = ("status", "category")
    search_fields = ("template_name",)
    autocomplete_fields = ()
