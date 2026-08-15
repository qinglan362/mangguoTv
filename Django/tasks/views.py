"""采集运行与调度状态 API。"""
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsAdmin
from tasks.models import CollectionRun
from tasks.serializers import CollectionRunSerializer


class CollectionRunViewSet(viewsets.ReadOnlyModelViewSet):
    """采集运行记录。"""

    queryset = CollectionRun.objects.select_related("topic").all()
    serializer_class = CollectionRunSerializer
    filterset_fields = ["topic", "status", "platform", "trigger_type"]

    def get_queryset(self):
        qs = super().get_queryset()
        topic = self.request.query_params.get("topic")
        if topic:
            qs = qs.filter(topic=topic)
        status_ = self.request.query_params.get("status")
        if status_:
            qs = qs.filter(status=status_)
        return qs.order_by("-created_at")


@api_view(["GET"])
@permission_classes([IsAdmin])
def scheduler_status(request):
    """调度器状态：运行状态、活动 job、队列深度、最近失败。"""
    result = {
        "scheduler_running": False,
        "dispatch_running": False,
        "active_jobs": [],
        "pending_queue": 0,
        "running_count": 0,
        "recent_failed": [],
    }
    try:
        from tasks.services.scheduler import get_scheduler
        scheduler = get_scheduler()
        result["scheduler_running"] = scheduler.running
        result["active_jobs"] = [
            {"id": job.id, "trigger": str(job.trigger), "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None}
            for job in scheduler.get_jobs()
        ]
    except Exception:
        pass

    try:
        from tasks.services.dispatch import dispatch_manager
        result["dispatch_running"] = dispatch_manager.running
    except Exception:
        pass

    result["pending_queue"] = CollectionRun.objects.filter(status="pending").count()
    result["running_count"] = CollectionRun.objects.filter(status="running").count()
    result["recent_failed"] = list(
        CollectionRun.objects.filter(status="failed").order_by("-created_at").values("id", "topic_id", "platform", "error_message")[:5]
    )
    return Response(result)
