"""标准化帖子数据资产模型。"""
from django.db import models


class Author(models.Model):
    """作者（基础公开信息）。"""

    platform = models.CharField("平台", max_length=16)
    author_id = models.CharField("平台侧ID", max_length=128, null=True, blank=True)
    name = models.CharField("作者名", max_length=128)
    avatar_url = models.URLField("头像地址", null=True, blank=True)
    follower_count = models.BigIntegerField("粉丝数", default=0)
    profile_url = models.URLField("主页地址", null=True, blank=True)
    is_key_author = models.BooleanField("重点账号", default=False)

    class Meta:
        verbose_name = "作者"
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=["platform", "name"]),
        ]

    def __str__(self):
        return f"{self.name}({self.platform})"


class Post(models.Model):
    """标准化帖子。"""

    post_id = models.CharField("平台帖子ID", max_length=128)
    platform = models.CharField("平台", max_length=16)
    url = models.URLField("原始链接", unique=True)
    title = models.CharField("标题", max_length=512, blank=True, default="")
    content = models.TextField("正文", blank=True, default="")
    content_hash = models.CharField("内容哈希", max_length=64, db_index=True)
    author = models.ForeignKey(
        Author, verbose_name="作者", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="posts",
    )
    published_at = models.DateTimeField("发布时间", null=True, blank=True)
    collected_at = models.DateTimeField("采集时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)
    like_count = models.BigIntegerField("点赞数", default=0)
    comment_count = models.BigIntegerField("评论数", default=0)
    share_count = models.BigIntegerField("转发数", default=0)
    favorite_count = models.BigIntegerField("收藏数", default=0)
    hashtags = models.JSONField("话题标签", default=list, blank=True)
    cover_url = models.URLField("封面地址", null=True, blank=True)
    images = models.JSONField("图片/视频封面", default=list, blank=True)
    dedup_group = models.CharField("相似去重组", max_length=64, null=True, blank=True)
    is_deleted = models.BooleanField("软删除", default=False)

    class Meta:
        verbose_name = "帖子"
        verbose_name_plural = verbose_name
        constraints = [
            # 跨关键词/并发采集下，同平台同帖子ID必须唯一（H6 竞态防线）
            models.UniqueConstraint(fields=["platform", "post_id"], name="uq_post_platform_pid"),
        ]
        indexes = [
            models.Index(fields=["platform", "post_id"]),
            models.Index(fields=["platform", "published_at"]),
            models.Index(fields=["dedup_group"]),
            models.Index(fields=["collected_at"]),
        ]

    def __str__(self):
        return f"{self.platform}/{self.post_id}"


class PostTopicHit(models.Model):
    """帖子↔主题命中关系（同帖同主题仅一条，记录命中全部关键词）。"""

    post = models.ForeignKey(Post, verbose_name="帖子", on_delete=models.CASCADE, related_name="topic_hits")
    topic = models.ForeignKey("topics.Topic", verbose_name="主题", on_delete=models.CASCADE, related_name="post_hits")
    matched_keywords = models.JSONField("命中关键词", default=list, blank=True)
    matched_count = models.IntegerField("命中词数", default=0)
    first_hit_at = models.DateTimeField("首次命中时间", auto_now_add=True)

    class Meta:
        verbose_name = "帖帖命中关联"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(fields=["post", "topic"], name="uq_post_topic"),
        ]
        indexes = [
            models.Index(fields=["topic", "first_hit_at"]),
        ]

    def __str__(self):
        return f"Post{self.post_id}->Topic{self.topic_id}"


class PostKeywordHit(models.Model):
    """命中关键词明细（可按词聚合）。"""

    post = models.ForeignKey(Post, verbose_name="帖子", on_delete=models.CASCADE, related_name="keyword_hits")
    topic = models.ForeignKey("topics.Topic", verbose_name="主题", on_delete=models.CASCADE)
    keyword = models.CharField("关键词快照", max_length=128)
    matched_text = models.CharField("命中原文片段", max_length=128)

    class Meta:
        verbose_name = "关键词命中明细"
        verbose_name_plural = verbose_name
        constraints = [
            # 同帖同主题同一关键词只记一条（M11 并发/重复采集防重复）
            models.UniqueConstraint(fields=["post", "topic", "keyword"], name="uq_post_topic_keyword"),
        ]
        indexes = [
            models.Index(fields=["post", "topic"]),
            models.Index(fields=["keyword"]),
        ]

    def __str__(self):
        return f"{self.keyword}@{self.post_id}"


class PostSnapshot(models.Model):
    """互动历史快照（供持续监测与互动趋势）。"""

    post = models.ForeignKey(Post, verbose_name="帖子", on_delete=models.CASCADE, related_name="snapshots")
    like_count = models.BigIntegerField("点赞数", default=0)
    comment_count = models.BigIntegerField("评论数", default=0)
    share_count = models.BigIntegerField("转发数", default=0)
    favorite_count = models.BigIntegerField("收藏数", default=0)
    collected_at = models.DateTimeField("采集时间", auto_now_add=True)

    class Meta:
        verbose_name = "互动快照"
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=["post", "collected_at"]),
        ]

    def __str__(self):
        return f"Snapshot@{self.post_id}:{self.collected_at:%H:%M}"
