"""规则层：负面词典快判、主题相关性初判、广告识别。

快路径：不耗 LLM token，置信度高的直接写分析结果。
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_negative_words: list[str] | None = None
_positive_words: list[str] | None = None


def _load_words(path_name: str, cache_key: str) -> list[str]:
    path = Path(__file__).resolve().parent.parent / "data" / path_name
    words = []
    if path.exists():
        words = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return words


def get_negative_words() -> list[str]:
    """加载内置负面词典（首次加载后缓存）。"""
    global _negative_words
    if _negative_words is None:
        _negative_words = _load_words("negative_words.txt", "neg")
    return _negative_words


def get_positive_words() -> list[str]:
    """加载内置正面词典。"""
    global _positive_words
    if _positive_words is None:
        _positive_words = _load_words("positive_words.txt", "pos")
    return _positive_words


def check_negative(text: str, extra_words: list[str] | None = None) -> tuple[bool, list[str]]:
    """检测文本是否命中负面词。返回 (是否负面, 命中负面词列表)。"""
    if not text:
        return False, []
    words = get_negative_words()
    if extra_words:
        words = list(words) + [w for w in extra_words if w]
    matched = [w for w in words if w and w in text]
    return bool(matched), matched


def check_positive(text: str) -> tuple[bool, list[str]]:
    """检测文本是否命中正面词。返回 (是否正面, 命中正面词列表)。"""
    if not text:
        return False, []
    words = get_positive_words()
    matched = [w for w in words if w and w in text]
    return bool(matched), matched


def classify_by_rules(text: str, keywords: list[str], extra_negative: list[str] | None = None) -> dict:
    """规则层综合判定：负面优先，其次正面，否则中性。"""
    is_neg, neg_words = check_negative(text, extra_negative)
    if is_neg:
        return {"sentiment": "negative", "score": 0.8, "source": "rule", "matched": neg_words}
    is_pos, pos_words = check_positive(text)
    if is_pos:
        return {"sentiment": "positive", "score": 0.7, "source": "rule", "matched": pos_words}
    return {"sentiment": "neutral", "score": 0.5, "source": "rule", "matched": []}


def check_relevance(text: str, keywords: list[str]) -> bool:
    """主题相关性初判：文本是否命中任一核心/关联关键词。

    1. 忽略大小写匹配整词（"芒果tv" 也能命中 "芒果TV"）；
    2. 长词组关键词（如"芒果TV不好用"）在正文中很少连写出现，退化为
       按 2 字滑窗片段匹配（含"不好用"/"芒果"即判相关），避免全部误判不相关。
    """
    if not text:
        return False
    t_lower = text.lower()
    for kw in keywords:
        if not kw:
            continue
        kw_lower = kw.lower()
        if kw_lower in t_lower:
            return True
        if len(kw) >= 4:
            for i in range(len(kw) - 1):
                seg = kw[i : i + 2]
                if len(seg) == 2 and seg.lower() in t_lower:
                    return True
    return False


def is_ad_text(text: str) -> bool:
    """广告特征识别（正则）。"""
    import re
    patterns = [
        re.compile(r"加\s*[Vv微信]"),
        re.compile(r"私信.*?(?:领取|代购)"),
        re.compile(r"代购|刷单|微商"),
    ]
    return any(p.search(text) for p in patterns)


def compute_sentiment_score(sentiment: str) -> float:
    """情感得分：negative 低、neutral 中、positive 高。"""
    return {"negative": 0.15, "neutral": 0.5, "positive": 0.85}.get(sentiment, 0.5)


def get_topic_negative_keywords(topic_id: int) -> list[str]:
    """主题配置的负面关键词（来自该主题 negative_keyword 预警规则）。"""
    try:
        from alerts.models import AlertRule
        from topics.models import Topic
        topic = Topic.objects.filter(pk=topic_id).first()
        if not topic:
            return []
        rules = topic.alert_rules.filter(rule_type="negative_keyword", enabled=True)
        words = []
        for rule in rules:
            words.extend(rule.config.get("keywords", []))
        return words
    except Exception:
        # 防御性返回空，但必须留痕——否则主题负面规则静默失效难以排查（M10）
        logger.exception("get_topic_negative_keywords failed topic=%s", topic_id)
        return []
