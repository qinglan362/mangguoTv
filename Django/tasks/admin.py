from django.contrib import admin

from .models import CollectionRun


@admin.register(CollectionRun)
class CollectionRunAdmin(admin.ModelAdmin):
    list_display = ("id", "topic", "platform", "status", "trigger_type", "fetched_count", "new_count", "duplicate_count", "retry_count", "created_at")
    list_filter = ("status", "trigger_type", "platform")
    search_fields = ("topic__name",)
