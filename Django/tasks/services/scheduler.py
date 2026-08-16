"""APScheduler 调度器管理器（M3 完整实现，当前为占位）。

规范启动方式：python manage.py runscheduler
进程重启后按 active 主题从 DB 重建调度任务（DB 为唯一事实源）。
"""
import logging

logger = logging.getLogger(__name__)

_scheduler = None


def get_scheduler():
    """返回全局调度器实例（首次调用创建 BackgroundScheduler）。"""
    global _scheduler
    if _scheduler is None:
        from apscheduler.schedulers.background import BackgroundScheduler
        from django.conf import settings

        _scheduler = BackgroundScheduler(
            timezone=settings.TIME_ZONE,
            job_defaults={"coalesce": True, "misfire_grace_time": 180},
        )
    return _scheduler


def ensure_started():
    """启动调度器 + 派发线程，并重建 active 主题的 job（供 runscheduler / auto_start 调用）。"""
    from .dispatch import dispatch_manager
    dispatch_manager.start()

    # 服务重启后对账：上次进程里卡住的 MediaCrawler 运行标记停止并自动导入数据
    try:
        from collectors.plugins.mediacrawler.runner import reconcile_stale_runs
        reconcile_stale_runs()
    except Exception:
        pass

    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        # 运行期对账 job：周期性按 DB 重建主题 job，使新建主题/改频率/窗口开关/暂停恢复实时生效（H4）
        from apscheduler.triggers.interval import IntervalTrigger
        scheduler.add_job(
            _reconcile_jobs,
            IntervalTrigger(minutes=1),
            id="topic_jobs_reconcile",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        from topics.models import Topic
        for topic in Topic.objects.filter(status="active"):
            sync_topic(topic)
        _sync_report_jobs(scheduler)
        _sync_keyword_snapshot_jobs(scheduler)
        _sync_alert_check_jobs(scheduler)
    else:
        # 调度器已在运行（如另起的 runscheduler 进程）→ 立即对账一次
        _reconcile_jobs()
    return scheduler


def _reconcile_jobs():
    """对账：DB 里的 active 主题 → 同步调度 job；已失效 job 移除。"""
    from topics.models import Topic
    scheduler = get_scheduler()
    if not scheduler.running:
        return
    active_ids = set()
    for topic in Topic.objects.filter(status="active"):
        active_ids.add(topic.id)
        sync_topic(topic)
    for job in scheduler.get_jobs():
        if not job.id.startswith("topic_"):
            continue
        try:
            tid = int(job.id.split("_")[1])
        except (ValueError, IndexError):
            continue
        if tid not in active_ids:
            try:
                scheduler.remove_job(job.id)
            except Exception:
                pass


def _sync_report_jobs(scheduler):
    """注册日报/周报自动生成任务（每日 9:00 / 每周一 9:05）。"""
    from apscheduler.triggers.cron import CronTrigger
    scheduler.add_job(
        generate_periodic_report,
        CronTrigger(hour=9, minute=0),
        args=["daily"],
        id="report_daily",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        generate_periodic_report,
        CronTrigger(day_of_week="mon", hour=9, minute=5),
        args=["weekly"],
        id="report_weekly",
        replace_existing=True,
        max_instances=1,
    )


def generate_periodic_report(period_type: str):
    """周期报告生成回调（为所有 active 主题生成）。"""
    try:
        from reports.services.report_service import generate_for_active_topics
        generate_for_active_topics(period_type)
    except Exception:
        logger.exception("periodic report generation failed: %s", period_type)


def _sync_keyword_snapshot_jobs(scheduler):
    """注册关键词快照预计算任务：启动即跑一次，之后每 30 分钟刷新。"""
    from apscheduler.triggers.interval import IntervalTrigger
    from django.utils import timezone

    scheduler.add_job(
        refresh_keyword_snapshots,
        IntervalTrigger(minutes=30),
        id="keyword_snapshots",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        next_run_time=timezone.now(),
    )


def _sync_alert_check_jobs(scheduler):
    """注册预警周期巡检任务（实现见 alerts/services/periodic.py）。"""
    from alerts.services.periodic import register
    register(scheduler)


def refresh_keyword_snapshots():
    """定时回调：刷新看板高频关键词快照（读库秒回，不再在线等 LLM）。"""
    try:
        from dashboard.services.snapshots import refresh_keyword_snapshots as _refresh
        _refresh()
    except Exception:
        logger.exception("keyword snapshot refresh failed")


def sync_topic(topic):
    """按主题状态同步调度 job：active 且在窗口内 → 注册/更新；否则移除。

    重要：对账线程（每分钟）会反复调用本函数。若每次都 replace_existing 重建 job，
    IntervalTrigger 的 next_run_time 会被重置为 now+interval，任务将永远无法触发
    （表现为「定时采集一直不运行」）。因此仅在 job 不存在或采集间隔实际变化时才
    重建/改期；间隔未变时保持原 job 不动。
    """
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler = get_scheduler()
    job_id = "topic_%d" % topic.id
    if topic.status == "active" and topic.is_in_monitor_window():
        interval = max(topic.collection_interval, 1)
        existing = scheduler.get_job(job_id)
        if existing is None:
            scheduler.add_job(
                enqueue_scheduled_run,
                IntervalTrigger(minutes=interval),
                args=[topic.id],
                id=job_id,
                replace_existing=True,
                max_instances=1,
            )
            return
        # 间隔未变 → 不动 job，保住 next_run_time
        current = None
        try:
            td = getattr(existing.trigger, "interval", None) or getattr(existing.trigger, "interval_length", None)
            if td is not None:
                current = int(td.total_seconds() // 60)
        except Exception:
            current = None
        if current != interval:
            # 用户改了采集频率 → 改期（next_run_time 从当前时刻重新起算，符合预期）
            scheduler.reschedule_job(job_id, trigger=IntervalTrigger(minutes=interval))
    else:
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass


def enqueue_scheduled_run(topic_id: int):
    """interval job 回调：只做入队，执行交给派发线程。"""
    from topics.models import Topic
    topic = Topic.objects.filter(pk=topic_id).first()
    if not topic or topic.status != "active" or not topic.is_in_monitor_window():
        return
    from .dispatcher import enqueue_run
    from tasks.models import CollectionRun

    for platform in topic.platforms:
        # 真实平台（小红书/微博）：定期任务交给 MediaCrawler 插件执行命令采集
        if platform in ("xiaohongshu", "weibo"):
            _enqueue_mediacrawler_scheduled(topic, platform)
            continue
        # 防队列堆积：同一主题同一平台已有 pending 运行（采集比频率慢）时跳过本轮入队（M18）
        exists = CollectionRun.objects.filter(
            topic=topic, platform=platform, status="pending",
        ).exists()
        if not exists:
            enqueue_run(topic, platform, trigger_type="schedule")


def _enqueue_mediacrawler_scheduled(topic, platform):
    """定期任务：为真实平台排一条 MediaCrawler 运行。

    MediaCrawler 保存了登录态后无需扫码即可静默采集；
    同一主题同一平台已有运行/排队任务时跳过，防止堆积。
    """
    try:
        from collectors.plugins.mediacrawler.runner import start_run
        from collectors.plugins.models import MediaCrawlerRun
    except ImportError:
        return  # 插件未安装
    mc_platform = "xhs" if platform == "xiaohongshu" else "wb"
    if MediaCrawlerRun.objects.filter(
        topic=topic, platform=mc_platform, status__in=["running", "queued"],
    ).exists():
        return
    keywords = ",".join(
        topic.keywords.filter(kind__in=["core", "related"]).values_list("word", flat=True)
    )
    if not keywords:
        return
    run = MediaCrawlerRun.objects.create(
        platform=mc_platform, topic=topic, keywords=keywords, status="running",
    )
    try:
        start_run(run)
    except Exception:
        from django.utils import timezone
        run.status = "failed"
        run.error_message = "定期任务启动失败"
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error_message", "finished_at"])


def shutdown():
    """优雅关闭：停止调度器与派发线程，把 in-flight 运行标记中断。"""
    global _scheduler
    from .dispatch import dispatch_manager
    if dispatch_manager.running:
        dispatch_manager.mark_interrupted()
        dispatch_manager.stop()
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
