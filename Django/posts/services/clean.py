"""数据清洗：文本归一化、无效内容过滤、广告识别。"""
import hashlib
import re

# 广告特征正则
AD_PATTERNS = [
    re.compile(r"加\s*[Vv微信]", re.I),
    re.compile(r"私信.*(?:领取|代购|购买)"),
    re.compile(r"扫[码一]?.*?(?:微信|二维码|下单)"),
    re.compile(r"代购|刷单|拉群|微商"),
    re.compile(r"(?:https?://\S+){3,}"),  # 大量外链
]

# 无效/占位内容
JUNK_PATTERNS = [
    re.compile(r"^\s*$"),
    re.compile(r"^[#\s，。,.]+$"),
]


def normalize_text(text: str) -> str:
    """归一化：去空白、HTML 标签、emoji 重复等。"""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("​", "").replace("﻿", "")
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    return text


def content_hash(text: str) -> str:
    """精确去重哈希（归一化文本）。"""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def is_junk(text: str) -> bool:
    """是否无效内容。"""
    normalized = normalize_text(text)
    return any(p.search(normalized) for p in JUNK_PATTERNS)


def is_ad(text: str) -> bool:
    """是否疑似广告。"""
    normalized = normalize_text(text)
    return any(p.search(normalized) for p in AD_PATTERNS)
