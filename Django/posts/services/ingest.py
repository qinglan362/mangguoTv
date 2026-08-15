"""帖子入库：清洗 → 过滤 → 去重 → 落库（Author/Post/PostTopicHit/PostKeywordHit/PostSnapshot）。

返回 IngestResult 统计：新增/更新/重复/过滤。

事务策略：外层 @transaction.atomic 保证整批可见性一致；每帖再套一层 savepoint，
单帖失败仅回滚该帖（记入 filtered），不会拖垮整批。
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime

from django.db import IntegrityError, transaction
from django.utils import timezone

from collectors.schemas import RawPost
from posts.models import Author, Post, PostKeywordHit, PostSnapshot, PostTopicHit
from posts.services import clean
from posts.services.dedupe import assign_dedup_groups
from topics.models import Topic, TopicKeyword

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    fetched_count: int = 0
    new_count: int = 0
    updated_count: int = 0
    duplicate_count: int = 0
    filtered_count: int = 0
    filtered_reasons: list = field(default_factory=list)
    # 本次入库实际涉及（新建/更新/归并）的帖子 DB id，供预警引擎按「本次采集的帖子」扫描：
    # 重复采集走更新路径，collected_at 不刷新，按时间过滤会漏掉这些帖子导致规则永不触发
    touched_post_ids: set = field(default_factory=set)


def _match_keywords(text: str, keywords: list) -> list:
    """返回命中关键词列表 [{"word","kind"}]。

    与 rules.check_relevance 同口径：忽略大小写整词匹配；长词组关键词
    （如"芒果TV不好用"）在正文中很少连写出现，退化为按 2 字滑窗片段匹配，
    保证命中明细与高频关键词（词云）有数据。
    """
    matched = []
    t_lower = text.lower()
    for kw in keywords:
        word = kw["word"]
        if not word:
            continue
        w_lower = word.lower()
        hit = w_lower in t_lower
        if not hit and len(word) >= 4:
            hit = any(word[i : i + 2].lower() in t_lower for i in range(len(word) - 1))
        if hit:
            matched.append({"word": word, "kind": kw["kind"]})
    return matched


def _num(value):
    """把可能为 None 的互动值规整为 0（真实爬虫常返回 null）。"""
    return value if value is not None else 0


def _get_or_create_author(author_info) -> Author | None:
    if not author_info or not author_info.name:
        return None
    obj, _ = Author.objects.get_or_create(
        platform=author_info.platform,
        name=author_info.name,
        defaults={
            "author_id": author_info.author_id,
            "avatar_url": author_info.avatar_url,
            "follower_count": author_info.follower_count,
            "profile_url": author_info.profile_url,
        },
    )
    return obj


@transaction.atomic
def ingest_batch(topic: Topic, raw_posts: list, run=None) -> IngestResult:
    """批量入库一批 RawPost 到指定主题。"""
    result = IngestResult(fetched_count=len(raw_posts))
    # 排除用户按本次采集的平台过滤（H7：多平台主题各自平台的排除用户才生效）
    platform = run.platform if (run and getattr(run, "platform", None)) else (topic.platforms[0] if topic.platforms else "mock")

    # 主题词配置（含排除词）
    keywords = list(topic.keywords.values("word", "kind"))
    exclude_words = [k["word"] for k in keywords if k["kind"] == "exclude"]
    excluded_author_names = set(topic.excluded_users.filter(platform=platform).values_list("author_name", flat=True))

    # ---- 阶段一：清洗 + 过滤，收集 (raw, text, hash) ----
    prepared = []
    for raw in raw_posts:
        text = clean.normalize_text(f"{raw.title}\n{raw.content}")
        if clean.is_junk(text):
            result.filtered_count += 1
            result.filtered_reasons.append("junk")
            continue
        if clean.is_ad(text):
            result.filtered_count += 1
            result.filtered_reasons.append("ad")
            continue
        if exclude_words and any(w.lower() in text.lower() for w in exclude_words):
            result.filtered_count += 1
            result.filtered_reasons.append("exclude_keyword")
            continue
        if raw.author and raw.author.name in excluded_author_names:  # 排除用户：名字匹配
            result.filtered_count += 1
            result.filtered_reasons.append("exclude_author")
            continue
        h = clean.content_hash(text)
        prepared.append((raw, text, h))

    # ---- 阶段二：batch 内 simhash 相似分组（跨平台搬运/改写归并） ----
    dedup_map = assign_dedup_groups([{"content": text, "hash": h} for _, text, h in prepared])

    # ---- 阶段三：精确去重 + 相似归并 + 入库 ----
    seen_hashes = set()
    group_leaders: dict = {}  # group_id -> 本 batch 已建的代表帖

    # 预取库内已有 content_hash（按批 IN 查询，避免逐条 filter 往返）
    existing_map = {}
    batch_hashes = [h for _, _, h in prepared]
    for i in range(0, len(batch_hashes), 500):
        chunk = batch_hashes[i : i + 500]
        # 全字段加载：only() 会在 _update_interactions 访问互动字段时逐条补查（N+1）
        for p in Post.objects.filter(content_hash__in=chunk):
            existing_map[p.content_hash] = p

    author_cache: dict = {}

    def _cached_author(info):
        if not info or not info.name:
            return None
        key = (info.platform, info.name)
        if key not in author_cache:
            author_cache[key] = _get_or_create_author(info)
        return author_cache[key]

    def _ingest_one(raw, text, h):
        """处理单帖（在调用方 savepoint 内执行）。"""
        if h in seen_hashes:
            result.duplicate_count += 1
            return
        seen_hashes.add(h)

        # 库内精确重复（同内容）
        existing = existing_map.get(h)
        if existing:
            _update_interactions(existing, raw)
            result.duplicate_count += 1
            result.updated_count += 1
            _attach_topic(existing, topic, text, keywords)
            result.touched_post_ids.add(existing.id)
            return

        # 平台帖子ID 去重（跨关键词同帖）
        existing_by_pid = Post.objects.filter(platform=raw.platform, post_id=raw.post_id).first()
        if existing_by_pid:
            _update_interactions(existing_by_pid, raw)
            result.duplicate_count += 1
            _attach_topic(existing_by_pid, topic, text, keywords)
            result.touched_post_ids.add(existing_by_pid.id)
            return

        # 相似去重：同组已有代表（本 batch 新建或库内同组）→ 归并
        gid = dedup_map.get(h)
        if gid:
            leader = group_leaders.get(gid)
            if leader is None:
                leader = Post.objects.filter(dedup_group=gid).first()
            if leader is not None:
                _update_interactions(leader, raw)
                _attach_topic(leader, topic, text, keywords)
                result.duplicate_count += 1
                result.touched_post_ids.add(leader.id)
                return

        # ---- 新建 ----
        author = _cached_author(raw.author)
        post = Post.objects.create(
            post_id=raw.post_id,
            platform=raw.platform,
            url=raw.url,
            title=raw.title,
            content=raw.content,
            content_hash=h,
            author=author,
            published_at=raw.published_at,
            like_count=_num(raw.like_count),
            comment_count=_num(raw.comment_count),
            share_count=_num(raw.share_count),
            favorite_count=_num(raw.favorite_count),
            hashtags=raw.hashtags,
            cover_url=raw.cover_url,
            images=raw.images,
            dedup_group=gid,
        )
        if gid:
            group_leaders[gid] = post
        _attach_topic(post, topic, text, keywords)
        result.new_count += 1
        result.touched_post_ids.add(post.id)

        # 重点账号标记
        if raw.extra and raw.extra.get("is_key_author") and author:
            Author.objects.filter(pk=author.pk).update(is_key_author=True)

    for raw, text, h in prepared:
        try:
            with transaction.atomic():  # savepoint：单帖失败仅回滚该帖
                _ingest_one(raw, text, h)
        except IntegrityError as exc:
            # 并发竞态：(platform, post_id) 唯一约束——另一线程已插入同 pid → 归并
            logger.warning("post insert race topic=%s pid=%s: %s", topic.id, getattr(raw, "post_id", "?"), exc)
            existing = Post.objects.filter(platform=raw.platform, post_id=raw.post_id).first()
            if existing:
                try:
                    with transaction.atomic():
                        _update_interactions(existing, raw)
                        _attach_topic(existing, topic, text, keywords)
                        result.duplicate_count += 1
                        result.touched_post_ids.add(existing.id)
                except Exception:
                    logger.exception("merge after insert race failed")
            else:
                result.filtered_count += 1
                result.filtered_reasons.append("insert_error")
        except Exception:
            logger.exception("ingest single post failed topic=%s pid=%s", topic.id, getattr(raw, "post_id", "?"))
            result.filtered_count += 1
            result.filtered_reasons.append("insert_error")

    return result


def _update_interactions(post: Post, raw: RawPost):
    """更新互动数据并记录快照（持续监测，每次重新采集都记一条快照供趋势分析）。"""
    changed = False
    updates = {}
    for field in ("like_count", "comment_count", "share_count", "favorite_count"):
        value = getattr(raw, field)
        if value is None:
            continue  # 采集器未返回该字段时不覆盖，避免 None 比较崩溃
        if value > getattr(post, field):
            updates[field] = value
            setattr(post, field, value)
            changed = True
    if changed:
        post.save(update_fields=[*updates.keys(), "updated_at"])
    PostSnapshot.objects.create(
        post=post,
        like_count=post.like_count,
        comment_count=post.comment_count,
        share_count=post.share_count,
        favorite_count=post.favorite_count,
    )


def refresh_interactions(platform: str, post_id: str, stats) -> None:
    """持续监测：用采集器返回的最新互动数据刷新单帖并记快照。

    stats 需具备 like_count/comment_count/share_count/favorite_count 属性（RawPost 或 PostStats）。
    """
    post = Post.objects.filter(platform=platform, post_id=post_id).first()
    if post is None:
        return
    _update_interactions(post, stats)


def _attach_topic(post: Post, topic: Topic, text: str, keywords: list):
    """建立帖↔主题命中关系（同帖同主题仅一条，记录命中全部关键词）。"""
    matched = _match_keywords(text, keywords)
    hit, created = PostTopicHit.objects.get_or_create(
        post=post,
        topic=topic,
        defaults={
            "matched_keywords": matched,
            "matched_count": len(matched),
        },
    )
    if not created and len(matched) > hit.matched_count:
        hit.matched_keywords = matched
        hit.matched_count = len(matched)
        hit.save(update_fields=["matched_keywords", "matched_count"])

    # 关键词命中明细：(post, topic, keyword) 唯一约束下用 get_or_create，防并发重复且无 N+1 预取
    for m in matched:
        PostKeywordHit.objects.get_or_create(
            post=post,
            topic=topic,
            keyword=m["word"],
            defaults={"matched_text": text[:128]},
        )
