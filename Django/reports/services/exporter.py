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

# 导出列（中文题头，对齐需求文档采集字段口径；去掉 post_id/sentiment_score/related_score 等内部字段）
BASE_COLUMNS = [
    "platform", "title", "content", "url",
    "author_name", "published_at", "collected_at",
    "like_count", "comment_count", "share_count", "favorite_count",
    "sentiment", "heat_score",
]

FULL_COLUMNS = BASE_COLUMNS + ["topic_names", "matched_keywords", "key_viewpoints"]

COLUMN_LABELS = {
    "platform": "平台",
    "title": "标题",
    "content": "正文",
    "url": "链接",
    "author_name": "作者",
    "published_at": "发布时间",
    "collected_at": "采集时间",
    "like_count": "点赞数",
    "comment_count": "评论数",
    "share_count": "转发数",
    "favorite_count": "收藏数",
    "sentiment": "情感倾向",
    "heat_score": "热度",
    "topic_names": "关联主题",
    "matched_keywords": "命中关键词",
    "key_viewpoints": "核心观点",
}

SENTIMENT_LABELS = {"positive": "正面", "neutral": "中性", "negative": "负面", "unknown": "未知"}


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


def _export_filename(filters: dict, export_type: str) -> str:
    """导出文件名。

    报告导出（filters 带 period_type/report_date）命名为「主题+日报/周报+日期」，
    同名文件已存在时追加序号，绝不覆盖；普通导出保留时间戳命名。
    """
    topic = _sanitize_dir(filters.get("topic_names", "")) or "posts"
    period_type = filters.get("period_type")
    report_date = filters.get("report_date")
    if period_type in ("daily", "weekly") and report_date:
        label = "%s%s_%s" % (
            topic,
            "日报" if period_type == "daily" else "周报",
            _sanitize_dir(str(report_date)),
        )
        filename = f"{label}.csv"
        seq = 2
        while (settings.EXPORT_DIR / filename).exists():
            filename = f"{label}_{seq}.csv"
            seq += 1
        return filename
    stamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    return f"export_{topic}_{stamp}_{export_type}.csv"


def export_posts_csv(filters: dict, export_type: str = "post") -> tuple[str, int]:
    """生成帖子 CSV 文件，返回 (文件相对路径, 行数)。"""
    Path(settings.EXPORT_DIR).mkdir(parents=True, exist_ok=True)
    columns = FULL_COLUMNS if export_type == "full" else BASE_COLUMNS

    filename = _export_filename(filters, export_type)
    file_path = settings.EXPORT_DIR / filename

    rows = 0
    with open(file_path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[COLUMN_LABELS[c] for c in columns], extrasaction="ignore")
        writer.writeheader()
        for post in _query_posts(filters).iterator(chunk_size=500):
            analysis = getattr(post, "analysis", None)  # OneToOne 可能未命中
            topics = [hit.topic.name for hit in post.topic_hits.all()]
            sentiment = analysis.sentiment if analysis else ""
            raw = {
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
                "sentiment": SENTIMENT_LABELS.get(sentiment, sentiment),
                "heat_score": analysis.heat_score if analysis else "",
                "topic_names": "、".join(topics),
                "matched_keywords": _join_strings(
                    [k for hit in post.topic_hits.all() for k in (hit.matched_keywords or [])]
                ),
                "key_viewpoints": _join_strings((analysis.key_viewpoints or []) if analysis else []),
            }
            writer.writerow({COLUMN_LABELS[c]: raw[c] for c in columns})
            rows += 1
    return str(file_path), rows


def export_absolute_path(rel_or_abs: str) -> Path:
    """解析导出文件路径（兼容绝对/相对存储）。"""
    p = Path(rel_or_abs)
    if p.is_absolute():
        return p
    return settings.EXPORT_DIR / p
