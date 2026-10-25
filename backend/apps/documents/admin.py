from django.contrib import admin

from .models import Document, DocumentCategory


@admin.register(DocumentCategory)
class DocumentCategoryAdmin(admin.ModelAdmin):
    list_display = ["code", "label", "tracks_expiry", "tenant", "is_active"]
    list_filter = ["tracks_expiry", "is_active", "tenant"]


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "version", "expiry_date", "tenant"]
    list_filter = ["category", "tenant"]
    search_fields = ["name"]
