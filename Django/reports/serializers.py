"""数据导出与报告 API 序列化器。"""
from rest_framework import serializers

from reports.models import DataExport, Report


class DataExportSerializer(serializers.ModelSerializer):
    requester_name = serializers.CharField(source="requester.username", read_only=True, default="")
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = DataExport
        fields = "__all__"
        read_only_fields = ("status", "file_path", "row_count", "created_at", "finished_at")

    def get_download_url(self, obj):
        if not obj.file_path:
            return None
        request = self.context.get("request")
        if request is None:
            return None
        return request.build_absolute_uri(f"/api/reports/exports/{obj.pk}/download/")


class ReportSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source="topic.name", read_only=True)
    period_type_label = serializers.CharField(source="get_period_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Report
        fields = "__all__"
        read_only_fields = ("status", "generated_at", "created_at")
