"""MediaCrawler 集成 API：前端触发采集命令、查看状态/日志、手动导入。"""
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from topics.models import Topic

from ..models import MediaCrawlerRun


class MediaCrawlerRunSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source="topic.name", read_only=True, default="")
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = MediaCrawlerRun
        fields = [
            "id", "platform", "topic", "topic_name", "keywords", "status",
            "status_label", "pid", "exit_code", "fetched_count", "new_count",
            "duplicate_count", "updated_count", "comment_count", "error_message",
            "started_at", "finished_at",
        ]


def _topic_keywords(topic: Topic) -> str:
    """主题的核心+关联关键词（MediaCrawler 搜索词）。"""
    words = list(topic.keywords.filter(kind__in=["core", "related"]).values_list("word", flat=True))
    return ",".join(words)


def derive_platforms(topic: Topic) -> list:
    """主题平台 → MediaCrawler 平台标识：xiaohongshu→xhs，weibo→wb。"""
    result = []
    if "xiaohongshu" in (topic.platforms or []):
        result.append("xhs")
    if "weibo" in (topic.platforms or []):
        result.append("wb")
    return result


@api_view(["POST"])
def mediacrawler_run(request):
    """启动 MediaCrawler 采集：POST {topic_id, platform?, max_notes?}。

    未传 platform 时按主题平台推导：xiaohongshu→xhs，weibo→wb；
    多平台主题会为每个平台各建一条运行记录，顺序排队执行；
    命令为 uv run main.py --platform xhs/wb --lt qrcode --type search --keywords ...，
    MediaCrawler 会自己弹出浏览器显示二维码，扫码登录后开始抓取。
    """
    topic_id = request.data.get("topic_id")
    topic = Topic.objects.filter(pk=topic_id).first()
    if topic is None:
        return Response({"detail": "主题不存在"}, status=status.HTTP_404_NOT_FOUND)

    platform = request.data.get("platform")
    if platform:
        if platform not in ("xhs", "wb"):
            return Response({"detail": "platform 仅支持 xhs / wb"}, status=status.HTTP_400_BAD_REQUEST)
        platform_list = [platform]
    else:
        # 按主题平台推导 MediaCrawler 平台标识
        platform_list = derive_platforms(topic)
        if not platform_list:
            return Response({"detail": "该主题没有可用的真实平台（小红书/微博），模拟平台请用普通立即采集"}, status=status.HTTP_400_BAD_REQUEST)

    keywords = _topic_keywords(topic)
    if not keywords:
        return Response({"detail": "该主题没有核心/关联关键词，请先配置"}, status=status.HTTP_400_BAD_REQUEST)

    from .runner import reconcile_stale_runs, start_run

    reconcile_stale_runs()
    created = []
    for mc_platform in platform_list:
        run = MediaCrawlerRun.objects.create(
            platform=mc_platform, topic=topic, keywords=keywords, status="running",
        )
        try:
            proc = start_run(run)
        except Exception as exc:
            run.status = "failed"
            run.error_message = str(exc)[:500]
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "error_message", "finished_at"])
            created.append(run)
            continue
        created.append(run)
    if not created:
        return Response({"detail": "启动失败"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response(MediaCrawlerRunSerializer(created, many=True).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def mediacrawler_status(request):
    """最近一次运行状态 + 日志尾部（前端轮询展示进度/二维码提示）。

    支持 ?topic=<id> 只看某个主题的运行。"""
    from .runner import get_running_process, has_pending, reconcile_stale_runs

    reconcile_stale_runs()
    qs = MediaCrawlerRun.objects.all()
    topic_id = request.query_params.get("topic")
    if topic_id:
        qs = qs.filter(topic_id=topic_id)
    # 优先返回真正在执行的运行（running/importing）；排队中（queued）的任务没有日志，
    # 若按 id 倒序取第一条会盖住正在运行的记录，导致采集过程页日志空白。
    # 都没有时回退到最近一条有日志的运行（跳过无日志的导入记录），再退而求其次取最近一条。
    run = qs.filter(status__in=["running", "importing"]).order_by("-id").first()
    if run is None:
        run = qs.filter(status="queued").order_by("-id").first()
    if run is None:
        run = qs.exclude(log_path="").order_by("-id").first()
    if run is None:
        run = qs.order_by("-id").first()
    proc = get_running_process()
    running = (
        (proc is not None and run is not None and run.status in ("running", "importing"))
        or (run is not None and run.status in ("queued", "running", "importing"))
        or has_pending()
    )
    data = MediaCrawlerRunSerializer(run).data if run else None
    log_tail = ""
    if run and run.log_path:
        from .runner import read_log_tail

        log_tail = read_log_tail(run.log_path, lines=300)
    return Response({"running": bool(running), "run": data, "log_tail": log_tail})


@api_view(["POST"])
def mediacrawler_stop(request):
    """停止正在运行的 MediaCrawler 子进程。"""
    from .runner import stop_run

    stopped = stop_run()
    run = MediaCrawlerRun.objects.filter(status="running").order_by("-id").first()
    if run is not None and stopped:
        run.status = "stopped"
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at"])
    return Response({"stopped": bool(stopped)})


@api_view(["POST"])
def mediacrawler_import(request):
    """手动导入：POST {topic_id, platform?} —— 补导入该主题最近一次采集任务的数据。

    主题归属 = 任务来源：以该主题最近一次启动的 MediaCrawlerRun 行数快照为起点，
    导入其后新增的行（即该次任务爬到的数据）；没有采集记录时拒绝导入。
    未传 platform 时按主题平台推导（xiaohongshu→xhs，weibo→wb），逐个导入。
    """
    topic_id = request.data.get("topic_id")
    topic = Topic.objects.filter(pk=topic_id).first()
    if topic is None:
        return Response({"detail": "主题不存在"}, status=status.HTTP_404_NOT_FOUND)

    platform = request.data.get("platform")
    if platform:
        if platform not in ("xhs", "wb"):
            return Response({"detail": "platform 仅支持 xhs / wb"}, status=status.HTTP_400_BAD_REQUEST)
        platform_list = [platform]
    else:
        platform_list = derive_platforms(topic)
        if not platform_list:
            return Response({"detail": "该主题没有真实平台（小红书/微博）可导入"}, status=status.HTTP_400_BAD_REQUEST)

    from .importer import import_new_data

    created = []
    failed_msgs = []
    for mc_platform in platform_list:
        latest = (
            MediaCrawlerRun.objects.filter(topic=topic, platform=mc_platform)
            .exclude(snapshot_lines={})
            .order_by("-id")
            .first()
        )
        if latest is None:
            return Response(
                {"detail": "该主题还没有采集任务记录，请先启动一次采集（完成后数据会自动导入）"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        run = MediaCrawlerRun.objects.create(
            platform=mc_platform, topic=topic, keywords=_topic_keywords(topic), status="importing",
            snapshot_lines=latest.snapshot_lines,
        )
        try:
            summary = import_new_data(run)
            run.fetched_count = summary.get("fetched", 0)
            run.new_count = summary.get("new", 0)
            run.duplicate_count = summary.get("duplicate", 0)
            run.updated_count = summary.get("updated", 0)
            run.comment_count = summary.get("comments", 0)
            run.status = "finished"
            run.finished_at = timezone.now()
            run.save()
        except Exception as exc:
            run.status = "failed"
            run.error_message = str(exc)[:500]
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "error_message", "finished_at"])
            failed_msgs.append(f"{mc_platform}: {exc}")
        created.append(run)
    if failed_msgs and not any(r.status == "finished" for r in created):
        return Response({"detail": "导入失败：" + "；".join(failed_msgs)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response(MediaCrawlerRunSerializer(created, many=True).data)