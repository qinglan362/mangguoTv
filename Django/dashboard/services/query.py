"""分析看板聚合查询服务（只读）。

所有图表数据接口统一支持 topic / platform / start / end 筛选。
"""
import logging
import re
from collections import Counter
from datetime import timedelta

from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncDate, TruncHour
from django.utils import timezone

from analysis.models import AnalysisResult
from posts.models import Author, Post, PostKeywordHit, PostTopicHit
from alerts.models import AlertEvent

logger = logging.getLogger(__name__)


def _parse_filters(request):
    """从 request 解析通用筛选。返回 (topic_ids, platform, start, end)。

    看板已去掉时间筛选：未传 start/end 时默认取最近 30 天，
    避免历史老帖把趋势图时间轴拉到几年前。
    """
    from datetime import timedelta

    from django.utils import timezone

    topic = request.query_params.get("topic")
    topics = request.query_params.get("topics")
    topic_ids = None
    if topic:
        topic_ids = [int(topic)]
    elif topics:
        topic_ids = [int(t) for t in topics.split(",") if t]
    platform = request.query_params.get("platform")
    start = request.query_params.get("start")
    end = request.query_params.get("end")
    if not start or not end:
        # 用本地时间（settings.TIME_ZONE）生成 naive 字符串：
        # 与前端 dayjs 的格式一致，Django 会按本地时区解析后与 UTC 存储的时间比较
        now = timezone.localtime()
        if not start:
            start = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
        if not end:
            end = now.strftime("%Y-%m-%dT%H:%M:%S")
    return topic_ids, platform, start, end


def _base_hits(topic_ids=None, platform=None, start=None, end=None):
    qs = PostTopicHit.objects.all()
    if topic_ids:
        qs = qs.filter(topic_id__in=topic_ids)
    if platform:
        qs = qs.filter(post__platform=platform)
    if start:
        qs = qs.filter(first_hit_at__gte=start)
    if end:
        qs = qs.filter(first_hit_at__lte=end)
    return qs


def _base_analyses(topic_ids=None, platform=None, start=None, end=None):
    qs = AnalysisResult.objects.all()
    if topic_ids:
        # AnalysisResult.post 为 OneToOne：跨主题共享帖只存一条，归属主题须经帖↔主题命中表关联，
        # 否则共享帖只会计入第一个分析它的主题，其余命中主题统计漏帖（H9）。
        # 必须用 post_id 子查询去重：JOIN 命中表会产生重复行，若配合 .distinct()，
        # 后续 .values("sentiment") 会编译成 SELECT DISTINCT sentiment，把 36 行折叠成 3 行，
        # 情感占比/平均热度/报告统计全部失真（H25）。
        qs = qs.filter(post_id__in=PostTopicHit.objects.filter(topic_id__in=topic_ids).values("post_id"))
    if platform:
        qs = qs.filter(post__platform=platform)
    # 时间窗口按「帖子首次命中时间」过滤（与 _base_hits 口径一致），而不是 analyzed_at：
    # 分析时刻是内部实现细节，按它过滤会导致报告/看板在补采、滞后分析时帖子数与情感数不一致
    if start or end:
        hit_filter = Q()
        if start:
            hit_filter &= Q(first_hit_at__gte=start)
        if end:
            hit_filter &= Q(first_hit_at__lte=end)
        qs = qs.filter(post_id__in=PostTopicHit.objects.filter(hit_filter).values("post_id"))
    return qs


# ---------- 顶部概览卡片 ----------
def overview(topic_ids=None, platform=None, start=None, end=None):
    hits = _base_hits(topic_ids, platform, start, end)
    analyses = _base_analyses(topic_ids, platform, start, end)
    today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    new_today = hits.filter(first_hit_at__gte=today).count()

    sentiment_dist = {}
    for item in analyses.values("sentiment"):
        key = item["sentiment"] or "unknown"
        sentiment_dist[key] = sentiment_dist.get(key, 0) + 1

    avg_heat = analyses.aggregate(v=Avg("heat_score"))["v"] or 0
    # M16：预警计数按主题 + 触发时间窗口筛选（原实现忽略 platform/start/end）
    alerts = AlertEvent.objects.filter(status="new")
    if topic_ids:
        alerts = alerts.filter(topic_id__in=topic_ids)
    if start:
        alerts = alerts.filter(triggered_at__gte=start)
    if end:
        alerts = alerts.filter(triggered_at__lte=end)
    alert_count = alerts.count()

    return {
        "post_count": hits.count(),
        "new_today": new_today,
        "negative_count": analyses.filter(sentiment="negative").count(),
        "sentiment_distribution": sentiment_dist,
        "avg_heat": round(avg_heat, 2),
        "alert_count": alert_count,
    }


# ---------- 新增趋势 ----------
def trend(topic_ids=None, platform=None, start=None, end=None, bucket="hour"):
    hits = _base_hits(topic_ids, platform, start, end)
    trunc = TruncHour("first_hit_at") if bucket == "hour" else TruncDate("first_hit_at")
    rows = (
        hits.annotate(bucket=trunc)
        .values("bucket")
        .annotate(count=Count("id"))
        .order_by("bucket")
    )
    return [{"time": r["bucket"].isoformat(), "count": r["count"]} for r in rows]


# ---------- 平台分布 ----------
def platform_distribution(topic_ids=None, start=None, end=None):
    qs = _base_hits(topic_ids, None, start, end).values("post__platform").annotate(count=Count("id"))
    return {r["post__platform"]: r["count"] for r in qs}


# ---------- 情感占比 ----------
def sentiment_distribution(topic_ids=None, platform=None, start=None, end=None):
    dist = {}
    for item in _base_analyses(topic_ids, platform, start, end).values("sentiment"):
        key = item["sentiment"] or "unknown"
        dist[key] = dist.get(key, 0) + 1
    return dist


# ---------- 互动量趋势 ----------
def interaction_trend(topic_ids=None, platform=None, start=None, end=None, bucket="hour"):
    # 用子查询而非 JOIN 定位主题内帖子：JOIN PostTopicHit 多值关联会让 Sum 重复累计（H11）。
    hit_posts = PostTopicHit.objects.all()
    if topic_ids:
        hit_posts = hit_posts.filter(topic_id__in=topic_ids)
    posts = Post.objects.filter(pk__in=hit_posts.values("post_id"), published_at__isnull=False)
    if platform:
        posts = posts.filter(platform=platform)
    if start:
        posts = posts.filter(published_at__gte=start)
    if end:
        posts = posts.filter(published_at__lte=end)

    trunc = TruncHour("published_at") if bucket == "hour" else TruncDate("published_at")
    rows = (
        posts.annotate(bucket=trunc)
        .values("bucket")
        .annotate(
            likes=Sum("like_count"),
            comments=Sum("comment_count"),
            shares=Sum("share_count"),
            favorites=Sum("favorite_count"),
        )
        .order_by("bucket")
    )
    return [
        {
            "time": r["bucket"].isoformat(),
            "likes": r["likes"] or 0,
            "comments": r["comments"] or 0,
            "shares": r["shares"] or 0,
            "favorites": r["favorites"] or 0,
        }
        for r in rows
    ]


# ---------- 帖子排行 ----------
def hot_posts(topic_ids=None, platform=None, start=None, end=None, limit=10):
    analyses = _base_analyses(topic_ids, platform, start, end).order_by("-heat_score")[:limit]
    return [_analysis_brief(a) for a in analyses.select_related("post", "post__author")]


def negative_posts(topic_ids=None, platform=None, start=None, end=None, limit=10):
    analyses = (
        _base_analyses(topic_ids, platform, start, end)
        .filter(sentiment="negative")
        .order_by("-heat_score")[:limit]
    )
    return [_analysis_brief(a) for a in analyses.select_related("post", "post__author")]


def _analysis_brief(a):
    post = a.post
    return {
        "id": a.id,
        "post_id": post.id,
        "content": (post.content or post.title or "")[:120],
        "url": post.url,
        "platform": post.platform,
        "author": post.author.name if post.author else None,
        "like_count": post.like_count,
        "comment_count": post.comment_count,
        "sentiment": a.sentiment,
        "heat_score": a.heat_score,
        "published_at": post.published_at.isoformat() if post.published_at else None,
    }


# ---------- 高频关键词 ----------
_stopwords_cache = None


def _load_stopwords() -> set:
    """加载中文停用词表（analysis/data/stopwords.txt，每行一个）。"""
    global _stopwords_cache
    if _stopwords_cache is not None:
        return _stopwords_cache
    from django.conf import settings

    path = settings.BASE_DIR / "analysis" / "data" / "stopwords.txt"
    words = set()
    try:
        words = {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}
    except OSError:
        pass
    _stopwords_cache = words
    return words


def _extract_keywords_from_texts(texts: list) -> Counter:
    """对帖子内容做中文分词统计（jieba），过滤停用词/单字/纯标点。"""
    import jieba

    stop = _load_stopwords()
    counter: Counter = Counter()
    word_re = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")
    for text in texts:
        if not text:
            continue
        for w in jieba.cut(text):
            w = w.strip()
            if len(w) < 2 or w in stop:
                continue
            if not word_re.search(w):
                continue
            # 纯英文词统一小写，合并 TV/tv、VIP/vip 等大小写变体
            if w.isascii() and w.isalpha():
                w = w.lower()
            counter[w] += 1
    return counter


def _keyword_counter(topic_ids=None, start=None, end=None) -> Counter:
    """高频词计数：LLM 每帖高频词聚合 + jieba 正文分词统计，排除主题配置词。"""
    from topics.models import TopicKeyword

    post_ids_qs = _base_hits(topic_ids, None, start, end).values("post_id")

    counter: Counter = Counter()
    # 1) LLM 高频词聚合（未配置 LLM 时为空）
    for row in AnalysisResult.objects.filter(
        post_id__in=post_ids_qs, high_freq_keywords__len__gt=0,
    ).values_list("high_freq_keywords", flat=True):
        for w in row or []:
            if isinstance(w, str) and w.strip():
                counter[w.strip()] += 1

    # 2) jieba 内容分词统计
    posts_qs = Post.objects.filter(pk__in=post_ids_qs)
    if start:
        posts_qs = posts_qs.filter(collected_at__gte=start)
    if end:
        posts_qs = posts_qs.filter(collected_at__lte=end)
    texts = list(posts_qs.values_list("content", flat=True)[:5000])
    counter.update(_extract_keywords_from_texts(texts))

    # 3) 排除主题自身配置的关键词（检索词本身没有信息量）
    if topic_ids:
        exclude_words = set(
            TopicKeyword.objects.filter(topic_id__in=topic_ids).values_list("word", flat=True)
        )
        for w in list(counter):
            if w in exclude_words:
                del counter[w]

    return counter


def top_keywords(topic_ids=None, start=None, end=None, limit=30):
    """高频关键词（统计版）：按词频取前 N。报告等功能继续使用。"""
    counter = _keyword_counter(topic_ids, start, end)
    return [{"keyword": w, "count": c} for w, c in counter.most_common(limit)]


# LLM 精选关键词缓存：key 已按小时归一，TTL 1 小时，
# 同一小时内反复刷新、切换回同一主题都直接命中缓存
_KEYWORD_LLM_CACHE_TTL = 3600
# 送入 LLM 精选的候选词上限（统计口径先取足够多的候选，交给 LLM 收敛）
_KEYWORD_LLM_CANDIDATES = 120


def _cache_time_bucket(ts) -> str:
    """把时间参数归一到整点，仅用于缓存 key。

    前端每次刷新页面都会用「当前时刻」重建时间范围的 end（默认最近 7 天窗口），
    直接用原始值建 key 会导致每次刷新 key 都不同、缓存永不命中、
    每次都重新触发约 2 分钟的 LLM 调用。归一到整点后，
    同一小时内的任意刷新共享同一份缓存。
    """
    if not ts:
        return ""
    try:
        from django.utils.dateparse import parse_datetime

        dt = parse_datetime(ts)
        if dt:
            return dt.replace(minute=0, second=0, microsecond=0).isoformat()
    except (TypeError, ValueError):
        pass
    return ts


def _parse_llm_keywords(text: str) -> list:
    """解析 LLM 精选输出为词列表。

    兼容纯字符串数组 ["迪丽热巴","演技"]（当前格式）、
    {"keywords":[...]} 对象包装，以及带 count 的旧对象条目；容忍代码块包裹与前后文字。
    """
    import json as _json

    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text).rstrip("`").strip()
    data = None
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1:
        try:
            data = _json.loads(text[start : end + 1])
        except ValueError:
            data = None
    if not isinstance(data, list):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            try:
                obj = _json.loads(text[start : end + 1])
                data = obj.get("keywords") if isinstance(obj, dict) else None
            except ValueError:
                data = None
    if not isinstance(data, list):
        return []

    words = []
    for item in data:
        if isinstance(item, str):
            words.append(item)
        elif isinstance(item, dict):
            word = str(item.get("keyword", "")).strip()
            if word:
                words.append(word)
    return words


def _merge_refined_counts(words: list, counter: Counter) -> list:
    """把 LLM 精选词映射回统计次数（LLM 只返回词、不返回次数）。

    精确命中用原次数；合并词累加其包含的候选碎片次数
    （候选里没有「迪丽热巴」，只有「迪丽」「热巴」时自动累加）；
    完全匹配不到的新词用候选词次数的中位数，保证词云仍有可比大小。
    """
    stats = sorted(counter.values())
    median = stats[len(stats) // 2] if stats else 1
    result = []
    seen = set()
    for raw in words:
        w = (raw or "").strip()
        if not w or w in seen:
            continue
        seen.add(w)
        if w in counter:
            result.append({"keyword": w, "count": counter[w]})
            continue
        total = 0
        for cand, n in counter.items():
            if cand != w and (w in cand or cand in w):
                total += n
        result.append({"keyword": w, "count": total or median})
    return result


def _refine_keywords(topic_ids=None, start=None, end=None, limit=30):
    """候选统计 + LLM 精选 + 次数映射（不含缓存）。在线兜底与预计算任务共用。"""
    from analysis.services import llm as llm_service

    counter = _keyword_counter(topic_ids, start, end)
    candidates = counter.most_common(_KEYWORD_LLM_CANDIDATES)
    fallback = [{"keyword": w, "count": c} for w, c in candidates[:limit]]
    if len(candidates) <= limit:
        return fallback  # 候选本就不多，无需 LLM 收敛

    topic_names = []
    if topic_ids:
        from topics.models import Topic

        topic_names = list(Topic.objects.filter(id__in=topic_ids).values_list("name", flat=True))

    system = (
        "你是一名资深舆情分析师，负责从舆情热词统计中提炼重点关键词。\n"
        "要求：\n"
        "1. 候选词中被拆散的专有名词必须合并为一个完整词，例如「迪丽」「热巴」合并为「迪丽热巴」，"
        "合并时保留候选词中最长的完整表达；\n"
        "2. 同义词、近义词、简称别名合并为一个规范词；\n"
        "3. 剔除「感觉、真的、可以、知道、东西」等无信息量的泛化词和语气词；\n"
        "4. 最多保留 %d 个最能反映当前舆情焦点、用户关注点与情绪的词，按重要性从高到低排序；\n"
        "5. 只输出一个 json 字符串数组，例如 [\"迪丽热巴\",\"演技\"]，不要输出任何解释或多余文字。"
    ) % limit
    cand_lines = "\n".join("%s：%d" % (w, c) for w, c in candidates)
    user = (
        "监测主题：%s\n候选词及出现次数：\n%s\n请直接输出精选后的关键词数组。"
    ) % ("、".join(topic_names) or "（全部主题）", cand_lines)

    refined = None
    try:
        # 不传 max_tokens（使用全局配置）：推理模型思考占输出额度，限制过小会把 JSON 截断导致解析失败
        text = llm_service.chat(system, user, json_mode=True)
        if text:
            words = _parse_llm_keywords(text)
            if words:
                refined = _merge_refined_counts(words, counter)[:limit]
    except Exception:
        logger.exception("LLM 关键词精选失败，降级统计结果")

    return refined if refined else fallback


def top_keywords_refined(topic_ids=None, start=None, end=None, limit=30, window=None):
    """高频关键词（看板用）：标准窗口优先读预计算快照，其余在线计算。

    window（如 "7d"）命中数据库快照时直接秒回，不调 LLM、不受进程重启影响；
    快照缺失时转为在线计算并回写快照（自愈）。自定义时间窗口仍走在线计算，
    结果内存缓存 1 小时（key 按小时归一）。LLM 未配置/失败/解析异常时
    降级返回统计结果，看板始终有产出。
    """
    from django.core.cache import cache

    snapshot_ctx = None
    if window:
        from dashboard.services import snapshots

        rows = snapshots.get_keyword_snapshot(topic_ids, window, limit)
        if rows is not None:
            return rows
        # 快照缺失（新建主题/定时任务未覆盖）：按窗口推导时间范围，转为在线计算
        ws, we = snapshots.window_range(window)
        start, end = start or ws, end or we
        if len(topic_ids or []) <= 1:
            snapshot_ctx = snapshots

    cache_key = "dashboard:kw_llm:%s:%s:%s:%s" % (
        ",".join(str(t) for t in sorted(topic_ids or [])),
        _cache_time_bucket(start), _cache_time_bucket(end), limit,
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = _refine_keywords(topic_ids, start, end, limit)
    cache.set(cache_key, result, _KEYWORD_LLM_CACHE_TTL)
    if snapshot_ctx is not None:
        snapshot_ctx.store_snapshot(topic_ids, window, result)
    return result


# ---------- 热度趋势 ----------
def heat_trend(topic_ids=None, platform=None, start=None, end=None, bucket="hour"):
    analyses = _base_analyses(topic_ids, platform, start, end)
    trunc = TruncHour("analyzed_at") if bucket == "hour" else TruncDate("analyzed_at")
    rows = (
        analyses.annotate(bucket=trunc)
        .values("bucket")
        .annotate(avg_heat=Avg("heat_score"))
        .order_by("bucket")
    )
    return [{"time": r["bucket"].isoformat(), "heat": round(r["avg_heat"] or 0, 2)} for r in rows]


# ---------- 重点作者 ----------
def key_authors(topic_ids=None, platform=None, start=None, end=None, limit=10):
    # 通过子查询限定主题内帖子，再对 distinct 帖子聚合，避免多值 join 使 total_likes 重复累计（H11）。
    hit_posts = PostTopicHit.objects.all()
    if topic_ids:
        hit_posts = hit_posts.filter(topic_id__in=topic_ids)
    posts_qs = Post.objects.filter(pk__in=hit_posts.values("post_id"))
    if platform:
        posts_qs = posts_qs.filter(platform=platform)
    if start:
        posts_qs = posts_qs.filter(published_at__gte=start)
    if end:
        posts_qs = posts_qs.filter(published_at__lte=end)

    agg = {
        r["author_id"]: r
        for r in posts_qs.exclude(author_id__isnull=True)
        .values("author_id")
        .annotate(post_count=Count("id"), total_likes=Sum("like_count"))
    }
    author_ids = sorted(agg, key=lambda aid: agg[aid]["total_likes"] or 0, reverse=True)[:limit]
    authors = Author.objects.in_bulk(author_ids)
    result = []
    for aid in author_ids:
        a = authors.get(aid)
        if not a:
            continue
        row = agg[aid]
        result.append({
            "id": a.id,
            "name": a.name,
            "platform": a.platform,
            "follower_count": a.follower_count,
            "is_key_author": a.is_key_author,
            "post_count": row["post_count"],
            "total_likes": row["total_likes"] or 0,
        })
    return result


# ---------- 主题对比 ----------
def topic_compare(topic_ids=None, start=None, end=None):
    if not topic_ids:
        return []
    from topics.models import Topic
    topics = Topic.objects.filter(id__in=topic_ids)
    result = []
    for t in topics:
        hits = _base_hits([t.id], None, start, end)
        analyses = _base_analyses([t.id], None, start, end)
        total = analyses.count()
        neg = analyses.filter(sentiment="negative").count()
        result.append({
            "topic_id": t.id,
            "name": t.name,
            "post_count": hits.count(),
            "negative_count": neg,
            # M15：占比分母与分子同源（同一窗口的分析帖），避免帖子/分析两套口径
            "negative_ratio": round(neg / total, 4) if total else 0,
            "avg_heat": round(analyses.aggregate(v=Avg("heat_score"))["v"] or 0, 2),
        })
    return result
