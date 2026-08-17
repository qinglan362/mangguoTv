"""舆情日报/周报生成。

聚合主题周期内数据（复用 dashboard 统计），生成 statistics 结构
与自然语言 summary 摘要，写入 Report 模型。

摘要优先由全站统一 LLM（DEEPSEEK_API_KEY）生成，未配置 Key 或调用失败时
退回模板拼接（_build_template_summary），保证定时报告始终有产出。
"""
import json
import logging
from datetime import date, timedelta

from django.utils import timezone

from dashboard.services import query as q
from reports.models import Report

logger = logging.getLogger(__name__)

PERIOD_DAYS = {"daily": 1, "weekly": 7}


def _period_range(period_type: str, report_date: date | None = None) -> tuple:
    """计算统计时间窗口，锚定 report_date（历史补报也按该日期取周期，而非现在）。

    日报 = report_date 当天 0 点 ~ 次日 0 点；周报 = 以 report_date 结束的最近 7 天。
    未指定 report_date（定时生成）时，end 截到当前时刻。
    """
    from datetime import datetime, time

    if report_date is None:
        ref = timezone.localdate()
    elif isinstance(report_date, datetime):
        ref = timezone.localdate(report_date)
    else:
        ref = report_date  # 已是 date
    if period_type == "daily":
        start = timezone.make_aware(datetime.combine(ref, time.min))
        end = start + timedelta(days=1)
    else:
        start = timezone.make_aware(datetime.combine(ref - timedelta(days=6), time.min))
        end = start + timedelta(days=7)
    if report_date is None:
        end = min(end, timezone.now())
    return start, end


def _top_viewpoints(topic_ids, start, end, limit=10):
    """聚合周期内帖子的热门观点（LLM 提取的 key_viewpoints），按出现次数排序。"""
    from collections import Counter

    from analysis.models import AnalysisResult
    from posts.models import PostTopicHit

    hits = PostTopicHit.objects.filter(topic_id__in=topic_ids)
    if start:
        hits = hits.filter(first_hit_at__gte=start)
    if end:
        hits = hits.filter(first_hit_at__lte=end)
    counter = Counter()
    for vps in AnalysisResult.objects.filter(
        post_id__in=hits.values("post_id"), key_viewpoints__len__gt=0,
    ).values_list("key_viewpoints", flat=True):
        for v in vps or []:
            if isinstance(v, str) and v.strip():
                counter[v.strip()] += 1
    return [{"viewpoint": v, "count": c} for v, c in counter.most_common(limit)]


def _collect_statistics(topic, start, end) -> dict:
    """聚合主题周期内统计（对齐需求文档「舆情分析看板」口径）。"""
    topic_ids = [topic.id]
    sentiment = q.sentiment_distribution(topic_ids, None, start, end)
    overview = q.overview(topic_ids, None, start, end)
    keywords = q.top_keywords(topic_ids, start, end, limit=10)
    hot = q.hot_posts(topic_ids, start=start, end=end, limit=5)
    negative = q.negative_posts(topic_ids, start=start, end=end, limit=5)
    platforms = q.platform_distribution(topic_ids, start, end)
    trend = q.trend(topic_ids, None, start, end, bucket="day")
    inter_trend = q.interaction_trend(topic_ids, None, start, end, bucket="day")
    heat_trend = q.heat_trend(topic_ids, None, start, end, bucket="day")
    key_authors = q.key_authors(topic_ids, None, start, end, limit=5)
    viewpoints = _top_viewpoints(topic_ids, start, end, limit=10)

    interaction_total = {
        "likes": sum(r["likes"] for r in inter_trend),
        "comments": sum(r["comments"] for r in inter_trend),
        "shares": sum(r["shares"] for r in inter_trend),
        "favorites": sum(r["favorites"] for r in inter_trend),
    }
    peak_heat = round(max((r["heat"] for r in heat_trend), default=0), 2)

    return {
        "post_count": overview["post_count"],
        "new_count": overview["post_count"],  # 周期内首见帖数 = 窗口内命中帖数
        "negative_count": sentiment.get("negative", 0),
        "positive_count": sentiment.get("positive", 0),
        "neutral_count": sentiment.get("neutral", 0),
        "sentiment_distribution": sentiment,
        "avg_heat": overview["avg_heat"],
        "platform_distribution": platforms,
        "alert_count": overview["alert_count"],
        "trend": trend,
        "interaction_total": interaction_total,
        "interaction_trend": inter_trend,
        "heat_trend": heat_trend,
        "peak_heat": peak_heat,
        "key_authors": key_authors,
        "top_viewpoints": viewpoints,
        "top_keywords": keywords,
        "hot_posts": hot,
        "negative_posts": negative,
    }


def _llm_summary(topic, period_type, stats: dict) -> str | None:
    """用统一 LLM（DeepSeek）生成报告摘要；未配置 Key/失败返回 None。"""
    try:
        from analysis.services.llm import chat
    except ImportError:
        return None
    period_label = "今日" if period_type == "daily" else "本周"
    system = (
        "你是一名资深舆情分析师，为芒果TV品牌与内容运营撰写舆情报告摘要。"
        "要求：150~250 字中文，客观凝练，先总后分——整体声量与情感分布、"
        "平台与互动表现、热度变化与重点作者、负面焦点与风险点、高热内容、"
        "最后给一条处置建议。"
        "只输出摘要正文，不要标题、序号或任何额外说明。"
    )
    user = "监测主题：%s\n统计周期：%s\n统计数据(JSON)：\n%s" % (
        topic.name, period_label, json.dumps(stats, ensure_ascii=False, default=str),
    )
    text = chat(system, user, max_tokens=1200, json_mode=False)
    return text or None


def _build_summary(topic, period_type, stats: dict) -> str:
    """生成摘要：优先 LLM，失败退回模板拼接。"""
    llm_text = _llm_summary(topic, period_type, stats)
    if llm_text:
        return llm_text
    return _build_template_summary(topic, period_type, stats)


def _build_template_summary(topic, period_type, stats: dict) -> str:
    """模板摘要（LLM 不可用时的兜底）。"""
    period_label = "今日" if period_type == "daily" else "本周"
    total = stats["post_count"]
    neg = stats["negative_count"]
    neg_ratio = round(neg / total * 100, 1) if total else 0
    sentiment = stats["sentiment_distribution"]

    lines = [
        f"《{topic.name}》{period_label}舆情报告：统计期内共采集相关帖子 {total} 条，"
        f"其中负面 {neg} 条（占比 {neg_ratio}%），正面 {sentiment.get('positive', 0)} 条，"
        f"中性 {sentiment.get('neutral', 0)} 条。",
    ]
    platforms = stats.get("platform_distribution") or {}
    if platforms:
        lines.append("平台分布：" + "、".join(f"{k} {v} 条" for k, v in platforms.items()) + "。")
    inter = stats.get("interaction_total") or {}
    if inter:
        lines.append(
            f"互动量：累计点赞 {inter.get('likes', 0)}、评论 {inter.get('comments', 0)}、"
            f"转发 {inter.get('shares', 0)}、收藏 {inter.get('favorites', 0)}。"
        )
    if stats.get("avg_heat"):
        heat_line = f"平均热度 {stats['avg_heat']}"
        if stats.get("peak_heat"):
            heat_line += f"，峰值热度 {stats['peak_heat']}"
        lines.append(heat_line + "。")
    authors = stats.get("key_authors") or []
    if authors:
        lines.append("重点作者：" + "、".join(f"{a.get('name')}（{a.get('post_count', 0)} 帖）" for a in authors[:3]) + "。")
    viewpoints = stats.get("top_viewpoints") or []
    if viewpoints:
        lines.append("热门观点：" + "、".join(v.get("viewpoint", "") for v in viewpoints[:5]) + "。")
    if neg:
        keywords = [kw.get("keyword", "") for kw in stats["top_keywords"][:5] if kw.get("keyword")]
        if keywords:
            lines.append(f"负面内容主要涉及：{'、'.join(keywords)}。")
    hot = stats.get("hot_posts") or []
    if hot:
        lines.append("热度最高的帖子：")
        for p in hot[:3]:
            lines.append(f"- {p.get('title') or p.get('content', '')[:40]}")
    if stats.get("alert_count"):
        lines.append(f"另有 {stats['alert_count']} 条待处理预警事件，建议及时跟进。")
    return "\n".join(lines)


def generate_report(topic, period_type: str, report_date: date | None = None) -> Report:
    """生成指定主题周期报告，返回 Report 记录。

    每次调用都新建一条记录，不覆盖历史报告：同一天多次生成的日报/周报各自保留，
    统计窗口锚定本次 report_date（默认今天），期间新采集的数据计入新报告。
    """
    report_date = report_date or timezone.localdate()
    report = Report.objects.create(
        topic=topic,
        period_type=period_type,
        report_date=report_date,
        title=f"{topic.name}{'日报' if period_type == 'daily' else '周报'} {report_date:%Y-%m-%d}",
        status="generating",
    )

    try:
        start, end = _period_range(period_type, report_date)
        stats = _collect_statistics(topic, start, end)
        report.statistics = stats
        report.summary = _build_summary(topic, period_type, stats)
        report.status = "done"
        report.generated_at = timezone.now()
        report.save(update_fields=["statistics", "summary", "status", "generated_at"])
        logger.info("report generated: topic=%s period=%s date=%s", topic.id, period_type, report_date)
    except Exception:
        logger.exception("report generation failed: topic=%s period=%s", topic.id, period_type)
        report.status = "failed"
        report.save(update_fields=["status"])
    return report


def generate_for_active_topics(period_type: str) -> int:
    """为所有 active 主题生成周期报告（调度器调用）。"""
    from topics.models import Topic
    count = 0
    for topic in Topic.objects.filter(status="active"):
        try:
            generate_report(topic, period_type)
            count += 1
        except Exception:
            logger.exception("report generation failed for topic %s", topic.id)
    return count
