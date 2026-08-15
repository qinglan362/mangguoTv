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


def _collect_statistics(topic, start, end) -> dict:
    """聚合主题周期内统计。"""
    topic_ids = [topic.id]
    sentiment = q.sentiment_distribution(topic_ids, None, start, end)
    overview = q.overview(topic_ids, None, start, end)
    keywords = q.top_keywords(topic_ids, start, end, limit=10)
    hot = q.hot_posts(topic_ids, start=start, end=end, limit=5)
    negative = q.negative_posts(topic_ids, start=start, end=end, limit=5)
    platforms = q.platform_distribution(topic_ids, start, end)

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
        "负面焦点与风险点、高热内容、最后给一条处置建议。"
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
    if stats.get("avg_heat"):
        lines.append(f"平均热度 {stats['avg_heat']}。")
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
    """生成/更新指定主题周期报告，返回 Report 记录。"""
    report_date = report_date or timezone.localdate()
    report, _ = Report.objects.get_or_create(
        topic=topic, period_type=period_type, report_date=report_date,
        defaults={"title": f"{topic.name}{'日报' if period_type == 'daily' else '周报'} {report_date:%Y-%m-%d}",
                  "status": "generating"},
    )
    report.status = "generating"
    report.save(update_fields=["status"])

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
