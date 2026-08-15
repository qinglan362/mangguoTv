"""预警规则引擎。

每次采集运行后调用 check_after_collection(topic, run)：
1. 遍历主题下启用的预警规则；
2. 按规则类型执行对应 checker；
3. 通过冷却期防抖（cooldown_minutes）；
4. 触发则创建 AlertEvent 并按渠道发送通知。

规则配置（rule.config，均可缺省，使用内置默认）：
- negative_keyword:  keywords(额外负面词), min_count
- like_threshold:     threshold(点赞阈值)
- negative_spike:     window_minutes, growth_ratio, min_count
- coordinated_posting: window_minutes, min_posts, min_accounts
- interaction_spike:  growth_ratio, min_abs
- key_author_negative: (无)
"""
import logging
from collections import Counter, defaultdict
from datetime import timedelta

from django.utils import timezone

from alerts.models import AlertEvent, AlertRule
from analysis.models import AnalysisResult
from analysis.services.rules import check_negative
from posts.models import Post, PostKeywordHit

logger = logging.getLogger(__name__)

RULE_HANDLERS: dict[str, callable] = {}


def _register(rule_type):
    def decorator(fn):
        RULE_HANDLERS[rule_type] = fn
        return fn
    return decorator


def check_after_collection(topic, run=None, post_ids=None):
    """对单个主题执行一次预警检查，返回触发的事件列表。

    post_ids：本次采集实际涉及（新建/更新/归并）的帖子集合。重复采集时
    帖子走更新路径、collected_at 不刷新，仅按时间过滤会漏检导致规则永不触发。
    """
    rules = topic.alert_rules.filter(enabled=True)
    if not rules.exists():
        return []

    # 本次采集起始时间：优先取 run.started_at，否则回退最近 1 小时
    since = run.started_at if (run and run.started_at) else timezone.now() - timedelta(minutes=60)

    triggered: list[AlertEvent] = []
    for rule in rules:
        handler = RULE_HANDLERS.get(rule.rule_type)
        if handler is None:
            logger.warning("no handler for rule_type=%s", rule.rule_type)
            continue
        try:
            result = handler(rule, topic, since, post_ids)
        except Exception:
            logger.exception("alert rule %s checker failed (topic=%s)", rule.id, topic.id)
            continue
        if not result:
            continue
        if _in_cooldown(rule):
            continue

        event = AlertEvent.objects.create(
            rule=rule,
            topic=topic,
            level=rule.level,
            reason=result.get("reason", "规则触发"),
            matched_posts=result.get("matched_posts", []),
            matched_keywords=result.get("matched_keywords", []),
            metrics=result.get("metrics", {}),
        )
        from alerts.services.notify import dispatch_notifications
        try:
            dispatch_notifications(event)
        except Exception:
            logger.exception("alert notification failed for event %s", event.id)
        triggered.append(event)
    return triggered


def _in_cooldown(rule: AlertRule) -> bool:
    """同一规则在冷却期内不重复触发。"""
    cooldown = rule.cooldown_minutes
    if cooldown <= 0:
        return False
    last = rule.events.order_by("-triggered_at").first()
    if not last:
        return False
    return (timezone.now() - last.triggered_at) < timedelta(minutes=cooldown)


def _recent_posts(topic, since, sentiment=None, post_ids=None):
    """主题下本次采集涉及的帖子（可过滤负面）。

    post_ids 提供时按集合精确扫描；未提供时回退按采集时间窗口过滤。
    """
    qs = Post.objects.filter(topic_hits__topic=topic).exclude(is_deleted=True).distinct()
    if post_ids is not None:
        qs = qs.filter(pk__in=post_ids)
    else:
        qs = qs.filter(collected_at__gte=since)
    if sentiment:
        qs = qs.filter(analysis__sentiment=sentiment)
    return qs


# ---------- 规则 1：负面关键词出现 ----------
@_register("negative_keyword")
def _check_negative_keyword(rule, topic, since, post_ids=None):
    extra_words = rule.config.get("keywords") or []
    min_count = int(rule.config.get("min_count", 1))

    matched_posts = []
    words_counter: Counter = Counter()
    for post in _recent_posts(topic, since, post_ids=post_ids).iterator():
        text = post.content or post.title
        found = check_negative(text, extra_words)[1]
        if found:
            matched_posts.append({
                "post_id": post.post_id,
                "url": post.url,
                "snippet": text[:200],
                "author": post.author.name if post.author_id else None,
            })
            words_counter.update(found)

    if len(matched_posts) >= min_count:
        top_words = [w for w, _ in words_counter.most_common(20)]
        return {
            "reason": f"命中负面关键词 {len(matched_posts)} 条：{'、'.join(top_words[:8])}",
            "matched_posts": matched_posts,
            "matched_keywords": top_words,
            "metrics": {"matched_count": len(matched_posts)},
        }
    return None


# ---------- 规则 2：负面帖点赞超阈值 ----------
@_register("like_threshold")
def _check_like_threshold(rule, topic, since, post_ids=None):
    threshold = int(rule.config.get("threshold", 1000))
    qs = Post.objects.filter(
        topic_hits__topic=topic,
        analysis__sentiment="negative",
        like_count__gte=threshold,
    ).distinct()
    if post_ids is not None:
        qs = qs.filter(pk__in=post_ids)
    else:
        qs = qs.filter(collected_at__gte=since)
    posts = list(qs.select_related("author").order_by("-like_count")[:10])
    if not posts:
        return None
    return {
        "reason": f"发现 {len(posts)} 条负面帖点赞超 {threshold}（最高 {posts[0].like_count}）",
        "matched_posts": [
            {
                "post_id": p.post_id,
                "url": p.url,
                "snippet": (p.content or p.title)[:200],
                "like_count": p.like_count,
            }
            for p in posts
        ],
        "metrics": {"threshold": threshold, "top_likes": posts[0].like_count},
    }


# ---------- 规则 3：负面帖数量激增 ----------
@_register("negative_spike")
def _check_negative_spike(rule, topic, since, post_ids=None):
    window = int(rule.config.get("window_minutes", 60))
    growth = float(rule.config.get("growth_ratio", 2.0))
    min_count = int(rule.config.get("min_count", 5))

    now = timezone.now()
    cur_start = now - timedelta(minutes=window)
    base_start = cur_start - timedelta(minutes=window * 3)  # 对比前 3 个窗口均值

    def _count_negative(start, end):
        # M14：按帖子发布时间（而非分析时刻）分桶——批量分析会让 analyzed_at 偏向同一时刻，
        # 导致激增误判；主题归属经命中表关联，共享帖也计入。
        return AnalysisResult.objects.filter(
            sentiment="negative",
            post__topic_hits__topic=topic,
            post__published_at__range=[start, end],
        ).distinct().count()

    cur_count = _count_negative(cur_start, now)
    base_count = _count_negative(base_start, cur_start)
    base_avg = base_count / 3.0

    if cur_count < min_count:
        return None
    ratio = (cur_count / base_avg) if base_avg > 0 else (cur_count if cur_count > 0 else 0)
    if base_avg > 0 and ratio < growth:
        return None

    return {
        "reason": (
            f"近 {window} 分钟负面帖 {cur_count} 条"
            + (f"，为基线均值 {base_avg:.1f} 的 {ratio:.1f} 倍" if base_avg > 0 else "，为近 4 小时最高峰")
        ),
        "metrics": {"window_minutes": window, "cur_count": cur_count, "base_avg": round(base_avg, 2), "ratio": round(ratio, 2)},
    }


# ---------- 规则 4：同观点多账号集中发布 ----------
@_register("coordinated_posting")
def _check_coordinated_posting(rule, topic, since, post_ids=None):
    window = int(rule.config.get("window_minutes", 60))
    min_posts = int(rule.config.get("min_posts", 5))
    min_accounts = int(rule.config.get("min_accounts", 3))
    win_start = timezone.now() - timedelta(minutes=window)

    rows = PostKeywordHit.objects.filter(
        topic=topic,
        post__collected_at__gte=win_start,
    ).values("keyword", "post_id", "post__author_id").distinct()

    posts_by_keyword: dict[str, set] = defaultdict(set)
    authors_by_keyword: dict[str, set] = defaultdict(set)
    for r in rows:
        posts_by_keyword[r["keyword"]].add(r["post_id"])
        if r["post__author_id"]:
            authors_by_keyword[r["keyword"]].add(r["post__author_id"])

    triggered_keywords = [
        kw for kw in posts_by_keyword
        if len(posts_by_keyword[kw]) >= min_posts and len(authors_by_keyword[kw]) >= min_accounts
    ]
    if not triggered_keywords:
        return None

    detail = []
    for kw in triggered_keywords[:10]:
        detail.append(f"{kw}({len(posts_by_keyword[kw])}帖/{len(authors_by_keyword[kw])}账号)")
    return {
        "reason": f"近 {window} 分钟多账号集中发布：{'；'.join(detail)}",
        "matched_keywords": triggered_keywords,
        "metrics": {
            "window_minutes": window,
            "min_posts": min_posts,
            "min_accounts": min_accounts,
            "triggered_keywords": triggered_keywords,
        },
    }


# ---------- 规则 5：单帖互动量异常增长 ----------
@_register("interaction_spike")
def _check_interaction_spike(rule, topic, since, post_ids=None):
    growth = float(rule.config.get("growth_ratio", 2.0))
    min_abs = int(rule.config.get("min_abs", 500))

    spikes = []
    posts = (
        Post.objects.filter(
            analysis__topic=topic,
            analysis__is_related=True,
            snapshots__collected_at__gte=since,
        )
        .distinct()[:200]
    )
    for post in posts:
        snaps = list(post.snapshots.order_by("-collected_at")[:2])
        if len(snaps) < 2:
            continue
        older, newer = snaps[1], snaps[0]
        prev = older.like_count + older.comment_count + older.share_count + older.favorite_count
        cur = newer.like_count + newer.comment_count + newer.share_count + newer.favorite_count
        if prev <= 0:
            continue
        delta = cur - prev
        ratio = cur / prev
        if delta >= min_abs and ratio >= growth:
            spikes.append({
                "post_id": post.post_id,
                "url": post.url,
                "prev": prev,
                "cur": cur,
                "ratio": round(ratio, 2),
            })

    if not spikes:
        return None
    return {
        "reason": f"发现 {len(spikes)} 条帖子互动量异常增长（{spikes[0]['ratio']}x）",
        "matched_posts": spikes[:10],
        "metrics": {"spike_count": len(spikes), "growth_ratio": growth, "min_abs": min_abs},
    }


# ---------- 规则 6：重点账号发布负面 ----------
@_register("key_author_negative")
def _check_key_author_negative(rule, topic, since, post_ids=None):
    qs = Post.objects.filter(
        author__is_key_author=True,
        topic_hits__topic=topic,
        analysis__sentiment="negative",
    ).distinct()
    if post_ids is not None:
        qs = qs.filter(pk__in=post_ids)
    else:
        qs = qs.filter(collected_at__gte=since)
    posts = list(qs.select_related("author").order_by("-like_count")[:10])
    if not posts:
        return None
    return {
        "reason": f"重点账号发布负面内容 {len(posts)} 条：{'、'.join(p.author.name for p in posts if p.author)}",
        "matched_posts": [
            {
                "post_id": p.post_id,
                "url": p.url,
                "snippet": (p.content or p.title)[:200],
                "author": p.author.name if p.author_id else None,
                "like_count": p.like_count,
            }
            for p in posts
        ],
        "metrics": {"count": len(posts)},
    }
