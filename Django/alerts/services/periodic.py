"""预警周期巡检（独立于采集回调）。

需求：平台按 10 分钟至 1 小时频率自动监测，命中预警条件立即提醒。
预警原先只挂在「采集运行结束」后触发——采集间隔长或手动采集场景下，
规则（尤其按时间窗口统计的 negative_spike / coordinated_posting）会漏报。
本任务由调度器每 ALERT_CHECK_INTERVAL_MINUTES 调度一次，对有启用规则的
active 主题各做一次检查；冷却期防重复，无规则的主题零开销跳过。
"""
import logging

from django.conf import settings

from alerts.models import AlertRule
from alerts.services.engine import check_after_collection

logger = logging.getLogger(__name__)

ALERT_CHECK_INTERVAL_MINUTES = settings.SCHEDULER.get("alert_check_interval_minutes", 10)


def run_periodic_check():
    """调度回调：巡检所有配置了启用规则的 active 主题。"""
    from django.db import close_old_connections

    from topics.models import Topic

    try:
        topic_ids = set(
            AlertRule.objects.filter(enabled=True).values_list("topic_id", flat=True)
        )
        if not topic_ids:
            return
        checked = 0
        for topic in Topic.objects.filter(id__in=topic_ids, status="active"):
            try:
                check_after_collection(topic, run=None, post_ids=None)
                checked += 1
            except Exception:
                logger.exception("periodic alert check failed (topic=%s)", topic.id)
        if checked:
            logger.info("periodic alert check done: %s topics", checked)
    finally:
        # 调度线程长驻，主动释放过期连接避免 sqlite/长连接占用
        close_old_connections()


def register(scheduler):
    """在共享调度器上注册巡检 job（幂等）。"""
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler.add_job(
        run_periodic_check,
        IntervalTrigger(minutes=max(ALERT_CHECK_INTERVAL_MINUTES, 1)),
        id="alert_periodic_check",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )


def unregister(scheduler):
    """移除巡检 job（主题对账只管 topic_ 前缀，不影响本 job）。"""
    try:
        scheduler.remove_job("alert_periodic_check")
    except Exception:
        pass
