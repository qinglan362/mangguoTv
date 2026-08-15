"""微博采集器（插件，基于 m.weibo.cn 移动端公开接口）。

启用步骤：
1. 浏览器登录 m.weibo.cn，F12 复制完整 Cookie → 环境变量 WEIBO_COOKIE；
2. settings.COLLECTORS_ENABLED["weibo"] = True。

接口说明：
- 关键词搜索：GET /api/container/getIndex?containerid=100103type=1&q={关键词}&page_type=searchall
- 评论：GET /comments/hotflow?id={mid}&mid={mid}&max_id_type=0（热评，一页约 20 条）
未登录/无 Cookie 时接口通常拒绝访问，validate() 会提示缺失项。

评论抓取：每次采集对互动量最高的前 N 条帖子各抓一页热评，
N 由环境变量 WEIBO_COMMENT_TOP_N 控制（默认 5，置 0 关闭评论抓取）。
"""
import html as html_lib
import logging
import os
import re
import time
from datetime import datetime

import requests

from collectors.base import BaseCollector
from collectors.registry import register
from collectors.schemas import AuthorInfo, CollectQuery, CollectResult, RawPost

from .comments_service import store_comments

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_SEARCH_URL = "https://m.weibo.cn/api/container/getIndex"
_COMMENTS_URL = "https://m.weibo.cn/comments/hotflow"
_DETAIL_URL = "https://m.weibo.cn/detail/{mid}"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _clean_html(text) -> str:
    """去 HTML 标签并反转义实体。"""
    return html_lib.unescape(_TAG_RE.sub("", text or "")).strip()


def _parse_weibo_time(value):
    """解析微博时间：'Thu Aug 14 12:00:00 +0800 2025' 或秒级时间戳。"""
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value)).astimezone()
        except (TypeError, ValueError, OSError):
            return None
    try:
        return datetime.strptime(str(value), "%a %b %d %H:%M:%S %z %Y")
    except ValueError:
        return None


class WeiboCollector(BaseCollector):
    platform = "weibo"
    display_name = "微博采集器(插件)"

    def __init__(self, config=None):
        super().__init__(config or {})
        self.cookie = (config or {}).get("cookie") or os.environ.get("WEIBO_COOKIE", "")
        self.comment_top_n = int((config or {}).get("comment_top_n") or os.environ.get("WEIBO_COMMENT_TOP_N", "5") or 5)
        self._http: requests.Session | None = None

    # ---------- 就绪状态 ----------
    def validate(self) -> list:
        issues = []
        if not self.cookie:
            issues.append("缺少 WEIBO_COOKIE（登录 m.weibo.cn 后从浏览器复制 Cookie）")
        return issues

    def _get_session(self) -> requests.Session:
        if self._http is None:
            s = requests.Session()
            s.headers.update({
                "User-Agent": _UA,
                "Referer": "https://m.weibo.cn/",
                "X-Requested-With": "XMLHttpRequest",
                "Cookie": self.cookie,
            })
            self._http = s
        return self._http

    # ---------- 搜索 ----------
    def _search_keyword(self, keyword: str, page_size: int) -> list:
        resp = self._get_session().get(
            _SEARCH_URL,
            params={
                "containerid": "100103type=1&q=" + keyword,
                "page_type": "searchall",
                "page": 1,
            },
            timeout=15,
        )
        data = resp.json()
        if not data.get("ok"):
            logger.warning("weibo search kw=%s not ok: %s", keyword, str(data)[:200])
            return []
        cards = (data.get("data") or {}).get("cards") or []
        mblogs = [c.get("mblog") or {} for c in cards if isinstance(c, dict) and c.get("card_type") == 9]
        return mblogs[:page_size]

    def _mblog_to_raw(self, mblog: dict, now: datetime) -> RawPost:
        mid = str(mblog.get("id") or mblog.get("mid") or "")
        user = mblog.get("user") or {}
        raw_text = mblog.get("text") or ""
        text = _clean_html(raw_text)
        hashtags = [t.strip() for t in re.findall(r"#([^#]+)#", raw_text) if t.strip()]
        pics = [p.get("url") for p in (mblog.get("pics") or []) if isinstance(p, dict) and p.get("url")]
        cover = pics[0] if pics else None

        return RawPost(
            post_id=mid,
            platform=self.platform,
            url=_DETAIL_URL.format(mid=mid) if mid else "",
            title=text[:64],
            content=text,
            author=AuthorInfo(
                platform=self.platform,
                author_id=str(user.get("id") or "") or None,
                name=user.get("screen_name") or "",
                avatar_url=user.get("avatar_hd") or user.get("avatar_large") or None,
                follower_count=int(user.get("followers_count") or 0),
                profile_url=(f"https://m.weibo.cn/profile/{user.get('id')}" if user.get("id") else None),
            ),
            published_at=_parse_weibo_time(mblog.get("created_at")),
            collected_at=now,
            like_count=int(mblog.get("attitudes_count") or 0),
            comment_count=int(mblog.get("comments_count") or 0),
            share_count=int(mblog.get("reposts_count") or 0),
            favorite_count=0,  # 微博无收藏数
            hashtags=hashtags,
            cover_url=cover,
            images=pics,
        )

    # ---------- 评论 ----------
    def _fetch_comments(self, mid: str, count: int) -> list:
        try:
            resp = self._get_session().get(
                _COMMENTS_URL,
                params={"id": mid, "mid": mid, "max_id_type": 0},
                timeout=15,
            )
            data = resp.json()
        except Exception as exc:
            logger.warning("weibo comments mid=%s failed: %s", mid, exc)
            return []
        if not data.get("ok"):
            return []
        items = ((data.get("data") or {}).get("data")) or []
        result = []
        for c in items[:count]:
            user = c.get("user") or {}
            result.append({
                "comment_id": str(c.get("id") or ""),
                "author_name": user.get("screen_name") or "",
                "content": _clean_html(c.get("text") or ""),
                "like_count": int(c.get("like_count") or 0),
                "published_at": _parse_weibo_time(c.get("created_at")),
            })
        return result

    # ---------- BaseCollector 实现 ----------
    def search(self, query: CollectQuery) -> CollectResult:
        if not self.cookie:
            raise RuntimeError("微博采集器缺少 Cookie：请设置 WEIBO_COOKIE 环境变量（登录 m.weibo.cn 后从浏览器复制）")
        now = datetime.now().astimezone()
        raw_posts: list[RawPost] = []
        per_keyword = max(1, min(query.limit // max(len(query.keywords), 1), 20))
        for keyword in query.keywords:
            try:
                for mblog in self._search_keyword(keyword, per_keyword):
                    raw = self._mblog_to_raw(mblog, now)
                    if raw.post_id:
                        raw_posts.append(raw)
                time.sleep(0.6)
            except Exception as exc:
                logger.warning("weibo search kw=%s failed: %s", keyword, exc)

        # 评论：互动量最高的前 N 条帖子，各抓一页热评
        if self.comment_top_n > 0 and raw_posts:
            top_posts = sorted(
                raw_posts,
                key=lambda p: p.like_count + p.comment_count + p.share_count,
                reverse=True,
            )[: self.comment_top_n]
            for raw in top_posts:
                comments = self._fetch_comments(raw.post_id, count=20)
                if comments:
                    try:
                        store_comments(self.platform, raw.post_id, comments)
                    except Exception:
                        logger.exception("store weibo comments failed pid=%s", raw.post_id)
                time.sleep(0.5)

        return CollectResult(platform=self.platform, posts=raw_posts, next_cursor=None, has_more=False)

    def fetch_interactions(self, post_ids: list) -> dict:
        # m.weibo.cn 无稳定批量互动接口；保持为空，由后续采集自然更新快照
        return {}


register("weibo")(WeiboCollector)
