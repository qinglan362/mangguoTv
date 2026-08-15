"""MockCollector：模拟数据源。

设计目标：
- 真实感：中文帖子模板嵌入关键词，文本确实包含命中词；
- 可复现：按 topic+platform+date_slot 稳定随机种子；
- 全链路可验证：key/exclude 作者、高热帖、负面激增用于测试规则。
"""
import hashlib
import random
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .base import BaseCollector
from .registry import register
from .schemas import AuthorInfo, CollectQuery, CollectResult, PostStats, RawPost

# 中文帖子模板：占位符 {keyword} 渲染真实命中词
TEMPLATES = {
    "positive": [
        "看了{keyword}的这期节目，剪辑节奏绝了，全程无尿点！",
        "{keyword}真的太上头了，已经三刷，强烈安利给身边朋友",
        "{keyword}最新物料质感拉满，芒果审美一如既往在线",
        "被{keyword}圈粉了，演技台词都在线，期待后续剧情",
        "{keyword}这波操作太赞了，路人缘直接拉满",
        "和朋友聊到{keyword}，一致好评，准备二刷",
        "{keyword}的服化道真的用心，每一帧都能截图当壁纸",
        "谁能想到{keyword}这么好看，连续追了好多天",
    ],
    "neutral": [
        "今天看到关于{keyword}的讨论，简单记录一下",
        "{keyword}最近热度还可以，观察中",
        "有人了解{keyword}的情况吗？想问问大家怎么看",
        "随手刷到{keyword}相关内容，转发存档",
        "{keyword}相关话题今天讨论度一般",
        "关于{keyword}，目前没有特别明确的说法，再观望",
    ],
    "negative": [
        "{keyword}最近这波操作真的败好感，太失望了",
        "{keyword}体验越来越差，会员还要看广告，退订了",
        "自动续费！{keyword}这吃相也太难看了，果断投诉",
        "{keyword}直接翻车，这波舆论真不是空穴来风",
        "{keyword}内容质量下滑明显，怀念以前的水平",
        "抵制{keyword}！给个说法，别当缩头乌龟",
        "{keyword}造假实锤了吗？评论区吵疯了",
        "{keyword}又出事了，黑料一堆还立人设",
        "平台对{keyword}的处理敷衍了事，完全不尊重观众",
    ],
}

SURNAMES = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
GIVEN = "伟芳娜敏静丽强磊军洋勇艳杰娟涛明超秀霞平刚桂英华玉萍红娥玲芬燕丹宁欣杰婷浩宇轩梓萱雨欣梦琪子涵梓涵"

HASHTAG_POOL = ["#今日热点#", "#追剧日常#", "#芒果TV#", "#娱乐八卦#", "#热搜#", "#综艺现场#", "#会员体验#", "#剧集安利#"]


class MockCollector(BaseCollector):
    platform = "mock"
    display_name = "模拟数据源"

    def __init__(self, config=None):
        super().__init__(config or {})
        cfg = settings.MOCK_COLLECTOR
        self.per_run = cfg.get("per_run", [30, 200])
        self.sentiment_weights = cfg.get("sentiment_weights", {"positive": 0.62, "neutral": 0.24, "negative": 0.14})
        self.negative_burst_hour = cfg.get("negative_burst_hour")
        self.seed_per_topic = cfg.get("seed_per_topic", True)
        self.hot_ratio = cfg.get("hot_ratio", 0.04)
        self.key_author_names = cfg.get("key_author_names", [])
        self.exclude_author_names = cfg.get("exclude_author_names", [])
        self._author_pool = self._build_author_pool()

    # ---------- 作者池 ----------
    def _build_author_pool(self):
        names = list(self.key_author_names) + list(self.exclude_author_names)
        for _ in range(60):
            surname = SURNAMES[random.randrange(len(SURNAMES))]
            name = surname + GIVEN[random.randrange(len(GIVEN))]
            names.append(name)
        pool = []
        for name in names:
            followers = int(100 * (random.random() ** 2.5) + random.random() * 50)
            pool.append({
                "name": name,
                "avatar_url": "https://example.com/avatar/%s.png" % hashlib.md5(name.encode()).hexdigest()[:8],
                "follower_count": followers,
                "is_key_author": name in self.key_author_names,
            })
        return pool

    # ---------- 时间与种子 ----------
    def _date_slot(self, dt) -> str:
        return dt.strftime("%Y%m%d%H")

    def _rng(self, query, dt):
        if self.seed_per_topic:
            seed = "%s:%s:%s" % (query.topic_id, query.platform, self._date_slot(dt))
        else:
            seed = self._date_slot(dt)
        return random.Random(hashlib.sha1(seed.encode()).hexdigest()[:16])

    def _stable_post_id(self, rng, query, index):
        seed = "%s:%s:%s:%s" % (query.platform, query.topic_id, self._date_slot(timezone.now()), index)
        return hashlib.sha1(seed.encode()).hexdigest()[:24]

    # ---------- 文本渲染 ----------
    def _render_post(self, rng, query, sentiment, index):
        now = timezone.now()
        keyword = rng.choice(query.keywords)
        template = rng.choice(TEMPLATES[sentiment])
        content = template.format(keyword=keyword)
        title = content[:20] if rng.random() < 0.7 else ""

        # 发布时间：增量窗口内随机；无窗口则最近几小时
        if query.since:
            start = query.since
            end = min(query.until or now, now)
            span = max((end - start).total_seconds(), 60)
            published_at = start + timedelta(seconds=rng.uniform(0, span))
        else:
            published_at = now - timedelta(hours=rng.uniform(0, 24))

        base = rng.random()
        if base < self.hot_ratio:
            mult = rng.uniform(5, 50)  # 高热帖放大
        else:
            mult = rng.uniform(0.6, 3.0)

        author = rng.choice(self._author_pool)
        stable_id = self._stable_post_id(rng, query, index)
        return {
            "post_id": stable_id,
            "platform": query.platform,
            "url": "https://example.com/%s/post/%s" % (query.platform, stable_id),
            "title": title,
            "content": content,
            "author": author,
            "published_at": published_at,
            "collected_at": now,
            "like_count": int(rng.uniform(0, 800) * mult),
            "comment_count": int(rng.uniform(0, 120) * mult),
            "share_count": int(rng.uniform(0, 60) * mult),
            "favorite_count": int(rng.uniform(0, 200) * mult),
            "hashtags": rng.sample(HASHTAG_POOL, k=rng.randint(0, 2)),
            "cover_url": "https://example.com/img/%d.jpg" % rng.randint(1, 999) if rng.random() < 0.3 else None,
            "images": [],
        }

    def _pick_sentiment(self, rng, published_at):
        weights = dict(self.sentiment_weights)
        if self.negative_burst_hour is not None and published_at.hour == self.negative_burst_hour:
            weights = {"positive": 0.15, "neutral": 0.25, "negative": 0.60}  # 负面激增
        total = sum(weights.values())
        r = rng.random() * total
        for sentiment, w in weights.items():
            r -= w
            if r <= 0:
                return sentiment
        return "neutral"

    # ---------- BaseCollector 实现 ----------
    def search(self, query: CollectQuery) -> CollectResult:
        rng = self._rng(query, timezone.now())
        count = min(rng.randint(*self.per_run), query.limit)
        posts = []
        for i in range(count):
            sentiment = self._pick_sentiment(rng, timezone.now())
            p = self._render_post(rng, query, sentiment, i)
            author = p.pop("author")
            posts.append(RawPost(
                post_id=p["post_id"],
                platform=p["platform"],
                url=p["url"],
                title=p["title"],
                content=p["content"],
                author=AuthorInfo(
                    platform=query.platform,
                    author_id=None,
                    name=author["name"],
                    avatar_url=author["avatar_url"],
                    follower_count=author["follower_count"],
                    profile_url=None,
                ),
                published_at=p["published_at"],
                collected_at=p["collected_at"],
                like_count=p["like_count"],
                comment_count=p["comment_count"],
                share_count=p["share_count"],
                favorite_count=p["favorite_count"],
                hashtags=p["hashtags"],
                cover_url=p["cover_url"],
                images=p["images"],
                extra={
                    "is_key_author": author["is_key_author"],
                    "is_excluded_author": author["name"] in self.exclude_author_names,
                },
            ))
        return CollectResult(
            platform=query.platform,
            posts=posts,
            next_cursor=str(int(query.cursor or 0) + 1),
            has_more=False,
        )

    def fetch_interactions(self, post_ids: list[str]) -> dict:
        result = {}
        for pid in post_ids:
            rng = random.Random(hashlib.sha1("interact:%s" % pid).hexdigest()[:16])
            result[pid] = PostStats(
                like_count=int(rng.uniform(0, 50)),
                comment_count=int(rng.uniform(0, 10)),
                share_count=int(rng.uniform(0, 5)),
                favorite_count=int(rng.uniform(0, 15)),
            )
        return result

    def validate(self) -> list[str]:
        return []  # 模拟源始终就绪


register("mock")(MockCollector)
