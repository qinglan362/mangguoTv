"""数据导出：帖子数据生成 CSV（UTF-8 BOM，Excel 可直接打开）。

按筛选条件（topic/platform/时间窗口/情感）查询帖子并流式写出，
避免大数据量时内存占用。导出任务由 DataExportViewSet 同步完成。
"""
import csv
import logging
import os
import re
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from analysis.models import AnalysisResult
from posts.models import Post, PostTopicHit

logger = logging.getLogger(__name__)

BASE_COLUMNS = [
    "post_id", "platform", "title", "content", "url",
    "author_name", "published_at", "collected_at",
    "like_count", "comment_count", "share_count", "favorite_count",
    "sentiment", "sentiment_score", "heat_score", "related_score",
]

FULL_COLUMNS = BASE_COLUMNS + ["topic_names", "matched_keywords", "key_viewpoints"]


def _query_posts(filters: dict):
    """根据筛选条件构造帖子查询集。"""
    qs = Post.objects.filter(is_deleted=False).distinct()
    topic_ids = filters.get("topic_ids")
    if topic_ids:
        qs = qs.filter(topic_hits__topic_id__in=topic_ids)
    platform = filters.get("platform")
    if platform:
        qs = qs.filter(platform=platform)
    start = filters.get("start")
    end = filters.get("end")
    if start:
        qs = qs.filter(collected_at__gte=start)
    if end:
        qs = qs.filter(collected_at__lte=end)
    sentiment = filters.get("sentiment")
    if sentiment:
        qs = qs.filter(analysis__sentiment=sentiment)
    return qs.select_related("author").prefetch_related("topic_hits", "analysis").order_by("-collected_at")


def _sanitize_dir(name: str) -> str:
    """把主题名/文件名转为安全片段。"""
    name = re.sub(r'[\\/:*?"<>|]', "_", name or "")
    return name.strip() or "export"


def _join_strings(values) -> str:
    """把可能混入 dict 的字段安全展平为字符串列表并去重。"""
    out = []
    for v in values or []:
        if isinstance(v, str):
            if v not in out:
                out.append(v)
        elif isinstance(v, dict):
            for sub in v.values():
                if isinstance(sub, str) and sub not in out:
                    out.append(sub)
    return "、".join(out)


def export_posts_csv(filters: dict, export_type: str = "post") -> tuple[str, int]:
    """生成帖子 CSV 文件，返回 (文件相对路径, 行数)。"""
    Path(settings.EXPORT_DIR).mkdir(parents=True, exist_ok=True)
    columns = FULL_COLUMNS if export_type == "full" else BASE_COLUMNS

    stamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    name = _sanitize_dir(filters.get("topic_names", "")) or "posts"
    filename = f"export_{name}_{stamp}_{export_type}.csv"
    file_path = settings.EXPORT_DIR / filename

    rows = 0
    with open(file_path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for post in _query_posts(filters).iterator(chunk_size=500):
            analysis = getattr(post, "analysis", None)  # OneToOne 可能未命中
            topics = [hit.topic.name for hit in post.topic_hits.all()]
            row = {
                "post_id": post.post_id,
                "platform": post.platform,
                "title": post.title,
                "content": post.content,
                "url": post.url,
                "author_name": post.author.name if post.author_id else "",
                "published_at": post.published_at.strftime("%Y-%m-%d %H:%M:%S") if post.published_at else "",
                "collected_at": post.collected_at.strftime("%Y-%m-%d %H:%M:%S"),
                "like_count": post.like_count,
                "comment_count": post.comment_count,
                "share_count": post.share_count,
                "favorite_count": post.favorite_count,
                "sentiment": analysis.sentiment if analysis else "",
                "sentiment_score": analysis.sentiment_score if analysis else "",
                "heat_score": analysis.heat_score if analysis else "",
                "related_score": analysis.related_score if analysis else "",
                "topic_names": "、".join(topics),
                "matched_keywords": _join_strings(
                    [k for hit in post.topic_hits.all() for k in (hit.matched_keywords or [])]
                ),
                "key_viewpoints": _join_strings((analysis.key_viewpoints or []) if analysis else []),
            }
            writer.writerow(row)
            rows += 1
    return str(file_path), rows


def export_absolute_path(rel_or_abs: str) -> Path:
    """解析导出文件路径（兼容绝对/相对存储）。"""
    p = Path(rel_or_abs)
    if p.is_absolute():
        return p
    return settings.EXPORT_DIR / p
