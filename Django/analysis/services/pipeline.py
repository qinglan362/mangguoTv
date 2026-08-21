"""混合内容识别流水线。

原始帖子 → 规则层(负面词典/相关性) → LLM层(批量) → 热度计算 → 实体/观点落库 → 触发预警
"""
import logging
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.db import IntegrityError
from django.db.models import F

from analysis.models import AnalysisResult, Entity, PostEntity, Viewpoint
from analysis.services import heat as heat_service
from analysis.services import rules
from analysis.services.llm import get_llm_backend
from posts.models import Post, PostTopicHit

logger = logging.getLogger(__name__)


def run_for_topic(topic, limit: int = 500):
    """对主题内尚未分析的新帖执行识别流水线。

    post→AnalysisResult 为 OneToOne 唯一，跨主题同帖只分析一次；
    用 LEFT JOIN 在 SQL 层排除已分析帖，避免每次调用全表加载 AnalysisResult。
    """
    hits = (
        PostTopicHit.objects.filter(topic=topic, post__analysis__isnull=True)
        .select_related("post")
        .order_by("first_hit_at")[:limit]
    )
    candidates = [h.post for h in hits]
    if not candidates:
        return 0

    keywords = list(topic.keywords.filter(kind__in=["core", "related"]).values_list("word", flat=True))
    negative_extra = rules.get_topic_negative_keywords(topic.id)

    # 规则层兜底：关键词/词典判定仅作为 LLM 缺失或失败时的兜底结果。
    # 不按关键词字面命中决定是否送 LLM——小红书等平台大量帖子（艺人本人账号、
    # 纯图片/视频笔记、昵称命中等）正文不含主题关键词，但语义上属于主题，
    # 一律交给 LLM 判定相关性与情感，避免关键词未命中被直接标成 unknown。
    rule_results = {}     # post_id -> dict（最终结果）
    rule_fallbacks = {}   # post_id -> dict（LLM 缺失/失败时的兜底）
    llm_candidates = []   # 需要 LLM 分析的帖子（主题下全部新帖）
    for post in candidates:
        text = "%s\n%s" % (post.title, post.content)
        is_rel = rules.check_relevance(text, keywords)
        classified = rules.classify_by_rules(text, keywords, negative_extra)
        llm_candidates.append(post)
        if is_rel:
            rule_fallbacks[post.id] = {
                "is_related": True,
                "related_score": 0.9 if classified["sentiment"] == "negative" else 0.8,
                "sentiment": classified["sentiment"],
                "sentiment_score": classified["score"],
                "source": classified["source"],
                "viewpoints": [],
                "entities": [],
                "keywords": [],
            }
        else:
            # 关键词未命中：LLM 可用时由其判定；仅当 LLM 缺失/失败时保持 unknown 兜底
            rule_fallbacks[post.id] = {
                "is_related": False,
                "related_score": 0.2,
                "sentiment": "unknown",
                "sentiment_score": 0.5,
                "source": "rule",
                "viewpoints": [],
                "entities": [],
                "keywords": [],
            }

    # LLM 层批量：配置了 API Key 时，主题下全部新帖（含关键词未命中的帖子）
    # 统一交给 LLM 判定相关性与情感，规则结果仅作为 LLM 未返回/调用失败时的兜底；
    # 未配置 Key 时整体走规则层兜底（关键词未命中仍标 unknown）。
    backend = get_llm_backend()
    if llm_candidates and backend is not None:
        llm_results = _run_llm_batches(backend, llm_candidates, topic, keywords)
        for post, res in zip(llm_candidates, llm_results):
            if res is None:
                # LLM 未返回 → 规则兜底，保留规则来源标记，不得标成 llm
                res = dict(rule_fallbacks[post.id])
            else:
                res["source"] = "llm"
            rule_results[post.id] = res
    else:
        for post in llm_candidates:
            rule_results[post.id] = rule_fallbacks[post.id]

    _persist_results(topic, candidates, rule_results)
    return len(candidates)


def _run_llm_batches(backend, posts, topic, keywords):
    """按 batch_size 分批，并发调用 LLM。"""
    cfg = settings.ANALYSIS_LLM
    batch_size = cfg.get("batch_size", 16)
    concurrency = cfg.get("concurrency", 3)
    context = {"topic_name": topic.name, "keywords": keywords}

    batches = [posts[i : i + batch_size] for i in range(0, len(posts), batch_size)]
    ordered = [None] * len(batches)
    with ThreadPoolExecutor(max_workers=min(concurrency, len(batches))) as pool:
        futures = {pool.submit(backend.analyze_batch, b, context): i for i, b in enumerate(batches)}
        for fut, i in futures.items():
            try:
                ordered[i] = fut.result()
            except Exception:
                ordered[i] = [None] * len(batches[i])
    # 展平并与 posts 对齐
    flat = []
    for i, batch in enumerate(batches):
        res = ordered[i]
        if res is None:
            res = [None] * len(batch)
        flat.extend(res)
    return flat


def _persist_results(topic, posts, rule_results):
    """写 AnalysisResult + Viewpoint + Entity/PostEntity + 热度归一化。"""
    # 热度计算
    heat_pairs = []
    for post in posts:
        res = rule_results[post.id]
        heat_pairs.append((post.id, heat_service.compute_heat(
            post.like_count, post.comment_count, post.share_count, post.favorite_count, post.published_at,
        )))
    normalized = heat_service.normalize_scores(heat_pairs)

    entities_by_name = {}
    for post in posts:
        res = rule_results[post.id]
        _upsert_analysis(post, topic, {
            "is_related": res["is_related"],
            "related_score": res["related_score"],
            "sentiment": res["sentiment"],
            "sentiment_score": res["sentiment_score"],
            "sentiment_source": res["source"],
            "key_viewpoints": res["viewpoints"],
            "key_entities": res["entities"],
            "high_freq_keywords": res["keywords"],
            "heat_score": normalized.get(post.id, 0),
        })
        _save_entities(topic, post, res.get("entities", []), entities_by_name)
        _save_viewpoints(topic, post, res.get("viewpoints", []))


def _upsert_analysis(post, topic, defaults):
    """按 post（OneToOne 唯一）写入分析结果，跨主题同帖共享同一条记录。

    update_or_create 的查询若含 topic 会在跨主题共帖时撞 UNIQUE 约束，
    因此改为 post 唯一查找 + create 失败重试，避免并发竞态。
    """
    analysis = AnalysisResult.objects.filter(post=post).first()
    if analysis is None:
        try:
            analysis = AnalysisResult.objects.create(post=post, topic=topic, **defaults)
            return analysis
        except IntegrityError:
            analysis = AnalysisResult.objects.filter(post=post).first()
            if analysis is None:
                raise
    for key, value in defaults.items():
        setattr(analysis, key, value)
    analysis.save()
    return analysis


def _save_entities(topic, post, entities, cache: dict):
    """实体标准化入库（name+type 匹配，新实体自动创建）。"""
    for e in entities:
        name = (e.get("name") or "").strip()[:128]
        etype = e.get("type", "tag")
        if not name:
            continue
        key = (name, etype)
        entity = cache.get(key)
        if entity is None:
            entity, _ = Entity.objects.get_or_create(name=name, type=etype)
            cache[key] = entity
        Entity.objects.filter(pk=entity.pk).update(mention_count=F("mention_count") + 1)
        PostEntity.objects.get_or_create(post=post, entity=entity, defaults={"mention": name})


def _save_viewpoints(topic, post, viewpoints):
    """观点落库并合并计数。"""
    for text in viewpoints:
        text = (text or "").strip()
        if not text or len(text) < 3:
            continue
        vp, created = Viewpoint.objects.get_or_create(
            topic=topic, text=text[:1000],
            defaults={"sentiment": "neutral", "mention_count": 1, "representative_post": post},
        )
        if not created:
            Viewpoint.objects.filter(pk=vp.pk).update(mention_count=F("mention_count") + 1)
