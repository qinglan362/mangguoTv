"""数据导出与舆情报告 API 视图。"""
from django.http import FileResponse
from django.utils import timezone
from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from reports.models import DataExport, Report
from reports.serializers import DataExportSerializer, ReportSerializer
from reports.services.exporter import export_absolute_path, export_posts_csv
from reports.services.report_service import generate_report


class DataExportViewSet(viewsets.ModelViewSet):
    """数据导出任务：POST 创建后同步生成 CSV 并可下载。"""

    queryset = DataExport.objects.all()
    serializer_class = DataExportSerializer
    filterset_fields = ("export_type", "status")

    def get_queryset(self):
        return super().get_queryset().order_by("-created_at")

    def create(self, request, *args, **kwargs):
        export_type = request.data.get("export_type", "post")
        if export_type not in ("post", "full"):
            return Response({"detail": "export_type 仅支持 post/full"}, status=http_status.HTTP_400_BAD_REQUEST)

        filters = request.data.get("filters") or {}
        topic_names = filters.get("topic_names")
        if not topic_names:
            from topics.models import Topic
            topic_ids = filters.get("topic_ids") or []
            names = list(Topic.objects.filter(id__in=topic_ids).values_list("name", flat=True))
            topic_names = "、".join(names)

        export = DataExport.objects.create(
            requester=request.user if request.user.is_authenticated else None,
            export_type=export_type,
            filters=filters,
            status="running",
        )
        try:
            path, rows = export_posts_csv(filters, export_type)
            export.file_path = str(path)
            export.row_count = rows
            export.status = "done"
        except Exception as exc:
            export.status = "failed"
            export.save(update_fields=["status"])
            return Response(
                {"detail": f"导出失败：{exc}"},
                status=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        export.finished_at = timezone.now()
        export.save()
        return Response(self.get_serializer(export, context={"request": request}).data, status=http_status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """下载已生成的 CSV 文件。"""
        obj = self.get_object()
        if not obj.file_path or obj.status != "done":
            return Response({"detail": "文件未生成"}, status=http_status.HTTP_404_NOT_FOUND)
        path = export_absolute_path(obj.file_path)
        if not path.exists():
            return Response({"detail": "文件不存在"}, status=http_status.HTTP_404_NOT_FOUND)
        # as_attachment + filename 由 Django 按 RFC 5987 编码中文文件名（filename*=utf-8''...）
        return FileResponse(
            open(path, "rb"), content_type="text/csv; charset=utf-8",
            as_attachment=True, filename=path.name,
        )


class ReportViewSet(viewsets.ReadOnlyModelViewSet):
    """舆情日报/周报。POST /api/reports/generate/ 触发指定主题生成。"""

    queryset = Report.objects.all()
    serializer_class = ReportSerializer
    filterset_fields = ("topic", "period_type", "status")

    def get_queryset(self):
        return super().get_queryset().select_related("topic").order_by("-report_date", "-created_at")

    @action(detail=False, methods=["post"])
    def generate(self, request):
        """手动触发生成：POST {topic, period_type=daily|weekly}。"""
        from topics.models import Topic

        topic_id = request.data.get("topic")
        period_type = request.data.get("period_type", "daily")
        if not topic_id:
            return Response({"detail": "缺少 topic 参数"}, status=http_status.HTTP_400_BAD_REQUEST)
        if period_type not in ("daily", "weekly"):
            return Response({"detail": "period_type 仅支持 daily/weekly"}, status=http_status.HTTP_400_BAD_REQUEST)
        topic = Topic.objects.filter(pk=topic_id).first()
        if topic is None:
            return Response({"detail": "主题不存在"}, status=http_status.HTTP_404_NOT_FOUND)

        report = generate_report(topic, period_type)
        return Response(self.get_serializer(report, context={"request": request}).data, status=http_status.HTTP_201_CREATED)
