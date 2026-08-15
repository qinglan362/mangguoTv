from django.contrib import admin

from .models import DataExport, Report


@admin.register(DataExport)
class DataExportAdmin(admin.ModelAdmin):
    list_display = ("id", "export_type", "status", "row_count", "requester", "created_at")
    list_filter = ("status", "export_type")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("id", "topic", "period_type", "report_date", "status", "generated_at")
    list_filter = ("period_type", "status")
