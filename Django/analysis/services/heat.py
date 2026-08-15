"""热度计算。"""
import math
from datetime import timedelta

from django.utils import timezone


def compute_heat(like_count: int, comment_count: int, share_count: int, favorite_count: int, published_at=None, age_hours: float | None = None) -> float:
    """热度分：互动加权 / 时间衰减。

    heat = (like + comment*3 + share*4 + favorite*2) / max(age_hours,1)**0.8
    """
    if age_hours is None:
        if not published_at:
            age_hours = 1
        else:
            age_hours = max((timezone.now() - published_at).total_seconds() / 3600, 1)
    weight = like_count + comment_count * 3 + share_count * 4 + favorite_count * 2
    return round(weight / (age_hours ** 0.8), 2)


def normalize_scores(topic_heat_pairs: list[tuple[int, float]]) -> dict[int, float]:
    """把主题内热度分对数归一化到 0~100。

    输入 [(post_id, heat_score), ...]，返回 {post_id: 0~100 分}。
    """
    if not topic_heat_pairs:
        return {}
    scores = [max(h, 0) for _, h in topic_heat_pairs]
    max_v = max(scores) or 1
    result = {}
    for pid, h in topic_heat_pairs:
        normalized = round(100 * math.log10(1 + max(h, 0)) / math.log10(1 + max_v), 2)
        result[pid] = normalized
    return result
