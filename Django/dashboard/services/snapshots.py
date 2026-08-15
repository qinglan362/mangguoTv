"""高频关键词快照：预计算入库 + 读取。

看板默认窗口（最近 7 天）的关键词由定时任务提前算好写入
TopicKeywordsSnapshot，接口直接读库秒回，不依赖内存缓存、
不因进程重启而重新等待 LLM。LLM 不可用/失败时快照同样
存入统计兜底结果，看板始终有数据。
"""
import logging

logger = logging.getLogger(__name__)

# 预计算的标准窗口：与看板默认「最近 7 天」一致
SNAPSHOT_WINDOWS = {"7d": 7}


def window_range(window: str) -> tuple:
    """标准窗口 → (start, end)，end 取当前时刻。未知窗口返回 (None, None)。"""
    from datetime import timedelta

    from django.utils import timezone

    days = SNAPSHOT_WINDOWS.get(window)
    if not days:
        return None, None
    now = timezone.now()
    return now - timedelta(days=days), now


def _snapshot_topic_id(topic_ids):
    """快照按单主题/全部主题存取；多主题组合（逗号列表）不支持快照。"""
    return topic_ids[0] if len(topic_ids or []) == 1 else None


def get_keyword_snapshot(topic_ids, window: str, limit: int):
    """读取快照；不存在或内容为空返回 None（调用方转为在线计算）。"""
    from dashboard.models import TopicKeywordsSnapshot

    if len(topic_ids or []) > 1:
        return None
    snap = TopicKeywordsSnapshot.objects.filter(
        topic_id=_snapshot_topic_id(topic_ids), window=window,
    ).first()
    if snap is None or not snap.keywords:
        return None
    return snap.keywords[:limit]


def store_snapshot(topic_ids, window: str, rows):
    """写入/更新快照（在线计算自愈：本次算完，下次直接读库）。

    空结果不落库：主题刚创建尚无帖子时会算出空列表，若此时写入，
    帖子采集进来后看板会一直命中空快照，要等下一轮定时刷新才更新。
    """
    from dashboard.models import TopicKeywordsSnapshot

    if not rows:
        return
    TopicKeywordsSnapshot.objects.update_or_create(
        topic_id=_snapshot_topic_id(topic_ids), window=window,
        defaults={"keywords": rows},
    )


def refresh_keyword_snapshots(limit: int = 30) -> int:
    """定时任务：为活跃主题与「全部主题」刷新标准窗口的关键词快照。

    仅重算快照时间之后窗口内有新帖子的目标，避免对无变化主题反复
    消耗 LLM 调用。返回本次实际重算的快照数。
    """
    from datetime import timedelta

    from django.utils import timezone

    from dashboard.models import TopicKeywordsSnapshot
    from dashboard.services.query import _refine_keywords
    from posts.models import PostTopicHit
    from topics.models import Topic

    now = timezone.now()
    refreshed = 0
    targets = [None] + list(Topic.objects.filter(status="active").values_list("id", flat=True))
    for topic_id in targets:
        topic_ids = [topic_id] if topic_id is not None else None
        for window, days in SNAPSHOT_WINDOWS.items():
            if not _has_new_posts(topic_id, window, days, now):
                continue
            start = now - timedelta(days=days) if days else None
            try:
                rows = _refine_keywords(topic_ids, start, now, limit)
            except Exception:
                logger.exception("keyword snapshot refresh failed: topic=%s window=%s", topic_id, window)
                continue
            if not rows:
                continue  # 空结果不落库，避免看板命中空快照
            TopicKeywordsSnapshot.objects.update_or_create(
                topic_id=topic_id, window=window, defaults={"keywords": rows},
            )
            refreshed += 1
    return refreshed


def _has_new_posts(topic_id, window, days, now) -> bool:
    """窗口内是否有新帖子：无快照时指窗口内任意帖子；有快照时指快照之后的新帖。"""
    from datetime import timedelta

    from dashboard.models import TopicKeywordsSnapshot
    from posts.models import PostTopicHit

    snap = TopicKeywordsSnapshot.objects.filter(topic_id=topic_id, window=window).first()
    hits = PostTopicHit.objects.all()
    if topic_id is not None:
        hits = hits.filter(topic_id=topic_id)
    if snap:
        hits = hits.filter(first_hit_at__gt=snap.computed_at)
    if days:
        hits = hits.filter(first_hit_at__gte=now - timedelta(days=days))
    return hits.exists()
