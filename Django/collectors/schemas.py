"""采集器统一数据结构。跨进程边界用 to_dict/from_dict 序列化。"""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AuthorInfo:
    """作者公开信息。"""

    platform: str
    author_id: str | None
    name: str
    avatar_url: str | None = None
    follower_count: int = 0
    profile_url: str | None = None

    def to_dict(self):
        return {
            "platform": self.platform,
            "author_id": self.author_id,
            "name": self.name,
            "avatar_url": self.avatar_url,
            "follower_count": self.follower_count,
            "profile_url": self.profile_url,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            platform=d.get("platform", ""),
            author_id=d.get("author_id"),
            name=d.get("name", ""),
            avatar_url=d.get("avatar_url"),
            follower_count=d.get("follower_count", 0),
            profile_url=d.get("profile_url"),
        )


@dataclass
class RawPost:
    """标准化帖子数据（采集器输出，跨边界时序列化）。"""

    post_id: str
    platform: str
    url: str
    title: str
    content: str
    author: AuthorInfo
    published_at: datetime | None
    collected_at: datetime
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    favorite_count: int = 0
    hashtags: list = field(default_factory=list)
    cover_url: str | None = None
    images: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)  # 采集器私有字段，不落库

    def to_dict(self):
        return {
            "post_id": self.post_id,
            "platform": self.platform,
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "author": self.author.to_dict() if self.author else None,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "collected_at": self.collected_at.isoformat(),
            "like_count": self.like_count,
            "comment_count": self.comment_count,
            "share_count": self.share_count,
            "favorite_count": self.favorite_count,
            "hashtags": self.hashtags,
            "cover_url": self.cover_url,
            "images": self.images,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            post_id=d["post_id"],
            platform=d["platform"],
            url=d["url"],
            title=d.get("title", ""),
            content=d.get("content", ""),
            author=AuthorInfo.from_dict(d["author"]) if d.get("author") else None,
            published_at=datetime.fromisoformat(d["published_at"]) if d.get("published_at") else None,
            collected_at=datetime.fromisoformat(d["collected_at"]),
            like_count=d.get("like_count", 0),
            comment_count=d.get("comment_count", 0),
            share_count=d.get("share_count", 0),
            favorite_count=d.get("favorite_count", 0),
            hashtags=d.get("hashtags", []),
            cover_url=d.get("cover_url"),
            images=d.get("images", []),
            extra=d.get("extra", {}),
        )


@dataclass
class PostStats:
    """互动数据快照。"""

    like_count: int
    comment_count: int
    share_count: int
    favorite_count: int


@dataclass
class CollectQuery:
    """一次采集查询参数。"""

    topic_id: int
    keywords: list
    platform: str
    since: datetime | None = None
    until: datetime | None = None
    limit: int = 100
    cursor: str | None = None


@dataclass
class CollectResult:
    """一次采集结果。"""

    platform: str
    posts: list
    next_cursor: str | None = None
    has_more: bool = False
