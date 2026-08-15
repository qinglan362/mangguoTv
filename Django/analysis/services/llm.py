"""大模型分析层：相关性判断、情感识别、观点/实体提取，以及报告摘要等其余 LLM 场景。

默认对接 DeepSeek（OpenAI 兼容协议，requests 直连无额外依赖）；
未配置 API Key 时 get_llm_backend() 返回 None，各调用方降级为规则层/模板。
其余需要 LLM 的模块（如报告摘要）统一通过模块级 chat() 助手复用同一后端与 Key。
"""
import json
import logging
import os
import re
from datetime import date

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# ---------- 每日 Token 预算 ----------

def _budget_key() -> str:
    return "llm_token_budget_%s" % date.today().isoformat()


def daily_token_usage() -> int:
    """当日已消耗 token 数（local memory cache，单进程内有效）。"""
    return int(cache.get(_budget_key(), 0) or 0)


def consume_tokens(amount: int):
    """累计当日 token 消耗。"""
    if amount <= 0:
        return
    key = _budget_key()
    cache.set(key, daily_token_usage() + amount, 86400)


def check_token_budget(extra: int = 0) -> bool:
    """预算门控：预算内返回 True；超限返回 False（调用方降级规则层）。"""
    daily = int(settings.ANALYSIS_LLM.get("daily_token_budget", 0) or 0)
    if daily <= 0:
        return True  # 未配置预算则不限制
    return daily_token_usage() + extra <= daily


def _estimate_tokens(texts: list[str]) -> int:
    """粗略估算一次批处理消耗的 token（输入按每 2 字符 1 token，含输出上限）。"""
    input_chars = sum(len(t or "") for t in texts)
    return max(input_chars // 2, 64) + int(settings.ANALYSIS_LLM.get("max_tokens", 8192))


def _normalize_posts(posts: list) -> list:
    """统一入参为 dict（兼容 Django 模型实例与 dict 混合）。

    此前流水线直接传 Post 实例，llm.py 用 p.get() 访问 → AttributeError 在
    try 之前抛出，导致配置了 API Key 时 LLM 层整体失效、全部静默降级规则层。
    """
    normalized = []
    for p in posts:
        if isinstance(p, dict):
            normalized.append(p)
        else:
            normalized.append({
                "id": getattr(p, "id", None),
                "title": getattr(p, "title", "") or "",
                "content": getattr(p, "content", "") or "",
            })
    return normalized


def _build_messages(posts: list, topic_context: dict):
    """构造帖子批分析的系统/用户消息。"""
    system = (
        "你是一名资深舆情分析师，为芒果TV品牌和内容运营做舆情监测。"
        "对给定的每一条帖子内容，判断：\n"
        "1. is_related：是否与监测主题相关（布尔）\n"
        "2. related_score：相关度 0~1\n"
        "3. sentiment：情感倾向 positive(正面)/neutral(中性)/negative(负面) 三选一。"
        "负面=批评、质疑、负面情绪、投诉等；正面=赞扬、好评、安利等；无明确倾向为中性。\n"
        "4. sentiment_score：情感强度 0~1\n"
        "5. viewpoints：帖子表达的核心观点，1~3 条中文短句\n"
        "6. entities：识别出的实体列表，type 从 [brand, drama, variety, actor, character, tag] 选择\n"
        "7. keywords：3~5 个高频关键词\n"
        "只输出一个 JSON 数组，不要输出任何其他文字或代码块标记。"
    )
    lines = []
    for i, p in enumerate(posts):
        content = p.get("content", "") or p.get("title", "")
        lines.append("%d. %s" % (i + 1, content[:500]))
    user = (
        "监测主题：%s\n"
        "核心关键词：%s\n"
        "帖子列表：\n%s\n"
        "请按上述规则分析，输出 JSON 数组，元素格式："
        '{"post_id":<帖子序号>,"is_related":true,"related_score":0.9,"sentiment":"positive",'
        '"sentiment_score":0.8,"viewpoints":["..."],"entities":[{"type":"brand","name":"芒果TV"}],"keywords":["..."]}'
    ) % (
        topic_context.get("topic_name", ""),
        "、".join(topic_context.get("keywords", [])),
        "\n".join(lines),
    )
    return system, user


class LLMBackend:
    """大模型分析抽象后端。"""

    def available(self) -> bool:
        return True

    def chat(self, system: str, user: str, max_tokens: int = None, json_mode: bool = True) -> str:
        """单次对话补全，返回文本内容；失败抛异常（调用方决定降级）。"""
        raise NotImplementedError

    def analyze_batch(self, posts: list, topic_context: dict) -> list:
        """分析一批帖子，返回与 posts 同序的结果 dict 列表。"""
        raise NotImplementedError


class DeepSeekBackend(LLMBackend):
    """DeepSeek 后端（OpenAI 兼容 chat/completions，requests 直连）。"""

    def __init__(self):
        cfg = settings.ANALYSIS_LLM
        self.model = cfg.get("model", "deepseek-v4-pro")
        self.api_key = os.environ.get(cfg.get("api_key_env", "DEEPSEEK_API_KEY"), "")
        self.base_url = (cfg.get("base_url", "https://api.deepseek.com") or "").rstrip("/")
        self.max_tokens = cfg.get("max_tokens", 8192)
        self.timeout = cfg.get("timeout", 60)
        self.retries = cfg.get("retries", 3)

    def available(self) -> bool:
        return bool(self.api_key)

    def _post(self, payload: dict) -> dict:
        import requests

        resp = requests.post(
            self.base_url + "/chat/completions",
            headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def chat(self, system: str, user: str, max_tokens: int = None, json_mode: bool = True) -> str:
        if not self.available():
            raise RuntimeError("DeepSeek API Key 未配置")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens or self.max_tokens,
            "stream": False,
        }
        if json_mode:
            # json_object 模式要求 prompt 中出现 "json" 字样（调用方需保证）
            payload["response_format"] = {"type": "json_object"}
        data = self._post(payload)
        return data["choices"][0]["message"]["content"]

    def analyze_batch(self, posts: list, topic_context: dict) -> list:
        if not self.available():
            return [None] * len(posts)
        posts = _normalize_posts(posts)
        # 预算门控：本次批处理预计超预算则拒绝，触发规则层降级
        estimate = _estimate_tokens([p.get("content", "") or p.get("title", "") for p in posts])
        if not check_token_budget(estimate):
            logger.warning("LLM token budget exceeded (daily=%s used=%s est=%s), degrade to rules",
                           settings.ANALYSIS_LLM.get("daily_token_budget"), daily_token_usage(), estimate)
            return [None] * len(posts)
        system, user = _build_messages(posts, topic_context)
        last_exc = None
        for attempt in range(self.retries):
            try:
                text = self.chat(system, user, json_mode=True)
                consume_tokens(estimate)
                parsed = _parse_json_array(text)
                if parsed is None:
                    raise ValueError("无法解析 LLM JSON 输出")
                return _align_results(parsed, posts)
            except Exception as exc:
                last_exc = exc
                logger.warning("LLM batch attempt %d failed: %s", attempt + 1, exc)
        logger.error("LLM batch failed after retries: %s", last_exc)
        return [None] * len(posts)


class ClaudeBackend(LLMBackend):
    """Claude API 后端（anthropic SDK，兼容保留；新配置请用 DeepSeek）。"""

    def __init__(self):
        cfg = settings.ANALYSIS_LLM
        self.model = cfg.get("model", "claude-sonnet-4-5")
        self.api_key = os.environ.get(cfg.get("api_key_env", "ANTHROPIC_API_KEY"), "")
        self.max_tokens = cfg.get("max_tokens", 8192)
        self.timeout = cfg.get("timeout", 60)
        self.retries = cfg.get("retries", 3)
        self._client = None

    def available(self) -> bool:
        return bool(self.api_key)

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key, timeout=self.timeout)
        return self._client

    def chat(self, system: str, user: str, max_tokens: int = None, json_mode: bool = True) -> str:
        resp = self._get_client().messages.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text

    def analyze_batch(self, posts: list, topic_context: dict) -> list:
        if not self.available():
            return [None] * len(posts)
        posts = _normalize_posts(posts)
        estimate = _estimate_tokens([p.get("content", "") or p.get("title", "") for p in posts])
        if not check_token_budget(estimate):
            logger.warning("LLM token budget exceeded (daily=%s used=%s est=%s), degrade to rules",
                           settings.ANALYSIS_LLM.get("daily_token_budget"), daily_token_usage(), estimate)
            return [None] * len(posts)
        system, user = _build_messages(posts, topic_context)
        last_exc = None
        for attempt in range(self.retries):
            try:
                text = self.chat(system, user, json_mode=True)
                consume_tokens(estimate)
                parsed = _parse_json_array(text)
                if parsed is None:
                    raise ValueError("无法解析 LLM JSON 输出")
                return _align_results(parsed, posts)
            except Exception as exc:
                last_exc = exc
                logger.warning("LLM batch attempt %d failed: %s", attempt + 1, exc)
        logger.error("LLM batch failed after retries: %s", last_exc)
        return [None] * len(posts)


def _parse_json_array(text: str):
    """从 LLM 输出中提取 JSON 数组（容忍 json 代码块包裹与前后文字）。"""
    text = text.strip()
    # 去掉代码块标记
    text = re.sub(r"^```(?:json)?\s*", "", text).rstrip("`").strip()
    # 提取第一个 [ 到最后一个 ]
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _align_results(parsed: list, posts: list) -> list:
    """把 LLM 结果与 posts 对齐（按序号），缺省返回 None。"""
    by_index = {}
    for item in parsed:
        idx = item.get("post_id")
        if idx is not None:
            by_index[int(idx)] = item
    results = []
    for i, p in enumerate(posts):
        item = by_index.get(i + 1)
        if not item:
            results.append(None)
            continue
        results.append({
            "is_related": bool(item.get("is_related", True)),
            "related_score": float(item.get("related_score", 0.8)),
            "sentiment": item.get("sentiment", "neutral") if item.get("sentiment") in ("positive", "neutral", "negative") else "neutral",
            "sentiment_score": float(item.get("sentiment_score", 0.5)),
            "viewpoints": item.get("viewpoints", []) or [],
            "entities": item.get("entities", []) or [],
            "keywords": item.get("keywords", []) or [],
        })
    return results


def get_llm_backend() -> LLMBackend | None:
    """按 settings 返回 LLM 后端；provider 不识别或未配置 Key 返回 None。"""
    provider = settings.ANALYSIS_LLM.get("provider", "deepseek")
    if provider == "deepseek":
        backend = DeepSeekBackend()
        return backend if backend.available() else None
    if provider == "anthropic":
        backend = ClaudeBackend()
        return backend if backend.available() else None
    return None


def chat(system: str, user: str, max_tokens: int = None, json_mode: bool = True) -> str | None:
    """全站统一 LLM 对话入口：其余 LLM 场景（报告摘要等）直接复用。

    复用与帖子分析相同的后端与 DEEPSEEK_API_KEY；未配置 Key 或调用失败返回 None，
    调用方需准备非 LLM 兜底逻辑。
    """
    backend = get_llm_backend()
    if backend is None:
        return None
    try:
        text = backend.chat(system, user, max_tokens=max_tokens, json_mode=json_mode)
        return (text or "").strip() or None
    except Exception:
        logger.exception("LLM chat failed")
        return None
