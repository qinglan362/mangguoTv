"""采集运行派发与执行。

两段式：enqueue_run 只创建 pending 记录；execute_run 真正执行。
调度器(APScheduler)在 M3 接入；本模块对 API 手动触发同样可用。
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from collectors.registry import get_collector
from collectors.schemas import CollectQuery
from posts.services.ingest import ingest_batch
from tasks.models import CollectionRun

logger = logging.getLogger(__name__)


@transaction.atomic
def enqueue_run(topic, platform, trigger_type="schedule") -> CollectionRun:
    """创建待执行采集运行记录。"""
    return CollectionRun.objects.create(
        topic=topic,
        platform=platform,
        trigger_type=trigger_type,
    )


def _retry_delay(run) -> int | None:
    """返回下次重试延迟（分钟），超限返回 None。"""
    max_retries = settings.SCHEDULER.get("max_retries", 3)
    backoffs = settings.SCHEDULER.get("retry_backoff_minutes", [1, 5, 15])
    if run.retry_count >= max_retries:
        return None
    return backoffs[min(run.retry_count, len(backoffs) - 1)]


def _schedule_retry(run):
    """失败后安排重试（依赖 APScheduler，未启动则仅标记）。"""
    delay = _retry_delay(run)
    if delay is None:
        return
    try:
        from tasks.services.scheduler import get_scheduler
        scheduler = get_scheduler()
        if scheduler.running:
            scheduler.add_job(
                retry_run,
                "date",
                run_date=timezone.now() + timedelta(minutes=delay),
                args=[run.id],
                id="retry_run_%d" % run.id,
                replace_existing=True,
                misfire_grace_time=180,
            )
            return
    except Exception as exc:  # 调度器未就绪
        logger.warning("scheduler unavailable for retry: %s", exc)


def _run_analysis_batches(topic, batch: int = 500):
    """分批运行分析流水线，直到主题内新帖全部处理完。"""
    from analysis.services.pipeline import run_for_topic
    total = 0
    while True:
        processed = run_for_topic(topic, limit=batch)
        if processed <= 0:
            break
        total += processed
        if processed < batch:
            break


def retry_run(run_id: int):
    """APScheduler 重试回调。"""
    from .dispatch import claim_specific_run, release_run

    run = CollectionRun.objects.filter(pk=run_id).first()
    if not run:
        return
    if run.status in ("success", "canceled"):
        return
    run.retry_count += 1
    run.status = "pending"
    run.save(update_fields=["retry_count", "status"])
    # 抢占成功才执行，避免与派发线程双重执行同一 run（H5 竞态）
    if not claim_specific_run(run_id):
        return
    try:
        execute_run(run_id)
    finally:
        release_run(run_id)


def execute_run(run_id: int) -> CollectionRun:
    """执行一次采集运行（同步）。"""
    run = CollectionRun.objects.filter(pk=run_id).first()
    if not run:
        raise ValueError("run %s not found" % run_id)

    run.status = "running"
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])

    try:
        topic = run.topic
        if topic.status != "active" or not topic.is_in_monitor_window():
            run.status = "canceled"
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "finished_at"])
            return run

        collector = get_collector(run.platform)
        if collector is None:
            raise RuntimeError("collector %s 未启用或未注册" % run.platform)

        keywords = list(topic.keywords.filter(kind__in=["core", "related"]).values_list("word", flat=True))
        query = CollectQuery(
            topic_id=topic.id,
            keywords=keywords,
            platform=run.platform,
            since=None,
            until=None,
            limit=200,
            cursor=run.cursor,
        )
        result = collector.search(query)

        ingest_result = ingest_batch(topic, result.posts, run=run)

        # 内容识别流水线（规则 + LLM），对新入库帖子分批执行直至处理完
        if ingest_result.new_count > 0:
            try:
                from analysis.services.pipeline import run_for_topic
                _run_analysis_batches(topic)
            except Exception:
                logger.exception("analysis pipeline failed for topic %s", topic.id)

        # 预警引擎：按「本次采集实际涉及的帖子」扫描，重复采集（去重更新）也能触发规则
        try:
            from alerts.services.engine import check_after_collection
            check_after_collection(topic, run=run, post_ids=list(ingest_result.touched_post_ids))
        except ImportError:
            pass  # 预警模块未实现
        except Exception:
            logger.exception("alert engine failed for topic %s", topic.id)

        # 持续监测：刷新互动数据（H8：fetch_interactions 结果真正写库，识别热度快速增长）
        if run.platform != "mock":
            stats_map = {}
            try:
                post_ids = [p.post_id for p in result.posts]
                stats_map = collector.fetch_interactions(post_ids) or {}
            except NotImplementedError:
                stats_map = {}
            if stats_map:
                from posts.services.ingest import refresh_interactions
                for raw in result.posts:
                    stats = stats_map.get(raw.post_id)
                    if stats:
                        try:
                            refresh_interactions(raw.platform, raw.post_id, stats)
                        except Exception:
                            logger.exception("refresh interactions failed pid=%s", raw.post_id)

        run.fetched_count = ingest_result.fetched_count
        run.new_count = ingest_result.new_count
        run.updated_count = ingest_result.updated_count
        run.duplicate_count = ingest_result.duplicate_count
        run.cursor = result.next_cursor
        run.status = "success"
        run.error_message = None
    except Exception as exc:
        logger.exception("collection run %s failed", run_id)
        run.status = "failed"
        run.error_message = str(exc)[:2000]
        _schedule_retry(run)
    finally:
        run.finished_at = timezone.now()
        run.save()

    return run
