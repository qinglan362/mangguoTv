"""小红书采集器（插件，基于社区库 xhs 0.2.x）。

启用步骤：
1. 浏览器登录 www.xiaohongshu.com，F12 复制完整 Cookie → 环境变量 XHS_COOKIE；
2. 签名：默认用插件内置的 Playwright + stealth.min.js 自动生成 x-s/x-t；
   也可配置 XHS_SIGN_SERVER 指向独立签名服务（官方 Flask/Docker 方案）；
3. （可选）XHS_USER_AGENT：自定义 UA（风控严时建议配成登录浏览器的 UA）；
4. settings.COLLECTORS_ENABLED["xiaohongshu"] = True。

评论抓取：每次采集对互动量最高的前 N 条帖子各抓一页评论（约 20 条），
N 由环境变量 XHS_COMMENT_TOP_N 控制（默认 5，置 0 关闭评论抓取）。

数据说明：搜索接口返回的互动数可能为「增量值」，与帖子详情页略有出入属正常；
fetch_interactions 用详情接口刷新互动数据。
"""
import logging
import os
import time
from datetime import datetime, timezone as dt_timezone

from collectors.base import BaseCollector
from collectors.registry import register
from collectors.schemas import AuthorInfo, CollectQuery, CollectResult, PostStats, RawPost

from .comments_service import store_comments
from .xhs_sign import build_signer

logger = logging.getLogger(__name__)


def _ms_to_datetime(value):
    """毫秒/秒时间戳 → 带时区 datetime；失败返回 None。"""
    if not value:
        return None
    try:
        ts = float(value)
        if ts > 1e12:  # 毫秒
            ts = ts / 1000
        return datetime.fromtimestamp(ts, tz=dt_timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _num(value, default=0):
    """xhs 互动字段多为字符串，统一转 int。"""
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return default


class XiaohongshuCollector(BaseCollector):
    platform = "xiaohongshu"
    display_name = "小红书采集器(插件)"

    def __init__(self, config=None):
        super().__init__(config or {})
        self.cookie = (config or {}).get("cookie") or os.environ.get("XHS_COOKIE", "")
        self.sign_server = (config or {}).get("sign_server") or os.environ.get("XHS_SIGN_SERVER", "") or ""
        self.user_agent = (config or {}).get("user_agent") or os.environ.get("XHS_USER_AGENT", "") or None
        self.comment_top_n = int((config or {}).get("comment_top_n") or os.environ.get("XHS_COMMENT_TOP_N", "5") or 5)
        self._client = None
        self._signer = None

    # ---------- 就绪状态 ----------
    def validate(self) -> list:
        issues = []
        if not self.cookie:
            issues.append("缺少 XHS_COOKIE（登录小红书后从浏览器复制 Cookie）")
        if not self.sign_server:
            # 内置 Playwright 签名需要 stealth.min.js 与 playwright
            from pathlib import Path

            stealth = Path(__file__).resolve().parent / "stealth.min.js"
            if not stealth.exists():
                issues.append("缺少 stealth.min.js（插件签名文件不完整）")
            try:
                import playwright  # noqa: F401
            except ImportError:
                issues.append("缺少 playwright 包（pip install playwright && playwright install chromium）")
        return issues

    def _get_signer(self):
        if self._signer is None:
            self._signer = build_signer(self.sign_server)
        return self._signer

    def _get_client(self):
        if self._client is None:
            from xhs import XhsClient

            kwargs = {"cookie": self.cookie, "timeout": 15, "sign": self._get_signer()}
            if self.user_agent:
                kwargs["user_agent"] = self.user_agent
            self._client = XhsClient(**kwargs)
        return self._client

    # ---------- 结构兼容提取 ----------
    @staticmethod
    def _extract_items(payload):
        """兼容 list / {"items": [...]} / {"data": {"items": [...]}} 结构。"""
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            if isinstance(payload.get("items"), list):
                return payload["items"]
            data = payload.get("data") or {}
            if isinstance(data.get("items"), list):
                return data["items"]
        return []

    # ---------- 数据映射 ----------
    def _note_to_raw(self, note: dict, now: datetime) -> RawPost:
        note_id = str(note.get("id") or note.get("note_id") or "")
        card = note.get("note_card") or note.get("noteCard") or {}
        interact = card.get("interact_info") or note.get("interact_info") or {}
        user = card.get("user") or {}
        title = (card.get("display_title") or card.get("title") or "").strip()
        content = (note.get("desc") or card.get("desc") or title).strip()
        cover = (card.get("cover") or {}).get("url_default") or None
        author_name = user.get("nickname") or user.get("nick_name") or ""
        published_at = _ms_to_datetime(note.get("time") or note.get("timestamp") or card.get("time"))

        return RawPost(
            post_id=note_id,
            platform=self.platform,
            url=f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else "",
            title=title[:512],
            content=content,
            author=AuthorInfo(
                platform=self.platform,
                author_id=str(user.get("user_id") or user.get("id") or "") or None,
                name=author_name,
                avatar_url=user.get("avatar") or None,
                follower_count=_num(user.get("fans")),
                profile_url=None,
            ),
            published_at=published_at,
            collected_at=now,
            like_count=_num(interact.get("liked_count")),
            comment_count=_num(interact.get("comment_count")),
            share_count=_num(interact.get("share_count")),
            favorite_count=_num(interact.get("collected_count")),
            hashtags=[
                f"#{t.get('name')}"
                for t in (note.get("tag_list") or [])
                if isinstance(t, dict) and t.get("name")
            ],
            cover_url=cover,
            images=[
                img.get("url_default")
                for img in (card.get("image_list") or [])
                if isinstance(img, dict) and img.get("url_default")
            ],
        )

    # ---------- 评论 ----------
    def _fetch_comments(self, note_id: str, count: int) -> list:
        try:
            payload = self._get_client().get_note_comments(note_id, cursor="")
        except Exception as exc:
            logger.warning("xiaohongshu comments note=%s failed: %s", note_id, exc)
            return []
        comments = payload.get("comments") if isinstance(payload, dict) else None
        if not isinstance(comments, list):
            comments = []
        result = []
        for c in comments[:count]:
            user = c.get("user_info") or {}
            result.append({
                "comment_id": str(c.get("id") or ""),
                "author_name": user.get("nickname") or "",
                "content": (c.get("content") or "").strip(),
                "like_count": _num(c.get("like_count")),
                "published_at": _ms_to_datetime(c.get("create_time")),
            })
        return result

    # ---------- BaseCollector 实现 ----------
    def search(self, query: CollectQuery) -> CollectResult:
        if not self.cookie:
            raise RuntimeError("小红书采集器缺少 Cookie：请设置 XHS_COOKIE 环境变量（登录小红书后从浏览器复制）")
        client = self._get_client()
        now = datetime.now(dt_timezone.utc)
        raw_posts: list[RawPost] = []
        per_keyword = max(1, min(query.limit // max(len(query.keywords), 1), 20))
        for keyword in query.keywords:
            try:
                payload = client.get_note_by_keyword(keyword, page=1, page_size=per_keyword)
                for note in self._extract_items(payload)[:per_keyword]:
                    raw = self._note_to_raw(note, now)
                    if raw.post_id:
                        raw_posts.append(raw)
                time.sleep(0.5)  # 控制频率，降低风控
            except Exception as exc:
                logger.warning("xiaohongshu search kw=%s failed: %s", keyword, exc)

        # 评论：互动量最高的前 N 条帖子，各抓一页
        if self.comment_top_n > 0 and raw_posts:
            top_posts = sorted(
                raw_posts,
                key=lambda p: p.like_count + p.comment_count,
                reverse=True,
            )[: self.comment_top_n]
            for raw in top_posts:
                comments = self._fetch_comments(raw.post_id, count=20)
                if comments:
                    try:
                        store_comments(self.platform, raw.post_id, comments)
                    except Exception:
                        logger.exception("store xiaohongshu comments failed pid=%s", raw.post_id)
                time.sleep(0.4)

        return CollectResult(platform=self.platform, posts=raw_posts, next_cursor=None, has_more=False)

    def fetch_interactions(self, post_ids: list) -> dict:
        client = self._get_client()
        result = {}
        for pid in post_ids:
            try:
                payload = client.get_note_by_id(pid)
                for note in self._extract_items(payload):
                    note_id = str(note.get("id") or note.get("note_id") or "")
                    if note_id != str(pid):
                        continue
                    interact = note.get("interact_info") or {}
                    result[pid] = PostStats(
                        like_count=_num(interact.get("liked_count")),
                        comment_count=_num(interact.get("comment_count")),
                        share_count=_num(interact.get("share_count")),
                        favorite_count=_num(interact.get("collected_count")),
                    )
                    break
                time.sleep(0.3)
            except Exception as exc:
                logger.warning("xiaohongshu interactions pid=%s failed: %s", pid, exc)
        return result


register("xiaohongshu")(XiaohongshuCollector)
