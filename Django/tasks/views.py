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


def _describe_job(job) -> dict:
    """把一个 APScheduler job 转成前端可读的调度任务信息。

    包含任务名称（中文）、类型、关联主题、触发器、间隔分钟、上次/下次执行时间。
    """
    from topics.models import Topic

    info = {
        "id": job.id or "",
        "name": job.id or "",
        "kind": "unknown",
        "topic_id": None,
        "topic_name": None,
        "trigger": str(job.trigger),
        "interval_minutes": None,
        "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
        "last_run_at": None,
        "last_run_status": None,
    }
    # interval 触发器：换算分钟数（cron/date 触发器无 interval）
    try:
        td = getattr(job.trigger, "interval", None) or getattr(job.trigger, "interval_length", None)
        if td is not None:
            info["interval_minutes"] = int(td.total_seconds() // 60)
    except Exception:
        pass

    jid = info["id"]
    if jid == "topic_jobs_reconcile":
        info.update(kind="reconcile", name="调度任务对账")
    elif jid == "report_daily":
        info.update(kind="report", name="日报自动生成")
    elif jid == "report_weekly":
        info.update(kind="report", name="周报自动生成")
    elif jid == "keyword_snapshots":
        info.update(kind="snapshot", name="看板关键词快照刷新")
    elif jid == "alert_periodic_check":
        info.update(kind="alert", name="预警周期巡检")
    elif jid.startswith("retry_run_"):
        info.update(kind="retry", name="采集失败重试（运行#%s）" % jid.split("retry_run_", 1)[1])
    elif jid.startswith("topic_"):
        info["kind"] = "topic"
        try:
            topic_id = int(jid.split("_", 1)[1])
        except (ValueError, IndexError):
            topic_id = None
        if topic_id is not None:
            info["topic_id"] = topic_id
            topic = Topic.objects.filter(pk=topic_id).first()
            if topic is not None:
                info["topic_name"] = topic.name
                info["name"] = "主题定时采集：%s" % topic.name
            else:
                info["name"] = "主题定时采集（主题#%s 已删除）" % topic_id
            # 该主题最近一次采集运行（含手动/定时/导入），供「上次执行」展示
            last = CollectionRun.objects.filter(topic_id=topic_id).order_by("-created_at").values("status", "created_at").first()
            if last:
                info["last_run_at"] = last["created_at"].isoformat()
                info["last_run_status"] = last["status"]
    return info


@api_view(["GET"])
@permission_classes([IsAdmin])
def scheduler_status(request):
    """调度器状态：运行状态、全部调度任务（含名称/主题/下次执行等）、队列与最近失败。"""
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
        jobs = [_describe_job(job) for job in scheduler.get_jobs()]
        # 按下一次执行时间升序（无下次执行的排最后）
        jobs.sort(key=lambda j: (j["next_run_time"] is None, j["next_run_time"] or ""))
        result["active_jobs"] = jobs
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
