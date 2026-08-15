"""舆情主题管理模型。"""
from django.contrib.auth import get_user_model
from django.db import models

PLATFORM_CHOICES = [
    ("xiaohongshu", "小红书"),
    ("weibo", "微博"),
    ("mock", "模拟数据"),
]

KEYWORD_KINDS = [
    ("core", "核心关键词"),
    ("related", "关联关键词"),
    ("exclude", "排除关键词"),
]

TOPIC_STATUS = [
    ("active", "监测中"),
    ("paused", "已暂停"),
    ("archived", "已归档"),
    ("deleted", "已删除"),
]


class Topic(models.Model):
    """舆情主题。"""

    name = models.CharField("主题名称", max_length=128)
    description = models.TextField("描述", blank=True)
    platforms = models.JSONField("采集平台", default=list, blank=True)
    collection_interval = models.IntegerField("采集频率(分钟)", default=30, help_text="5~1440 分钟")
    monitor_start = models.DateTimeField("监测开始时间", null=True, blank=True)
    monitor_end = models.DateTimeField("监测结束时间", null=True, blank=True)
    status = models.CharField("状态", max_length=16, choices=TOPIC_STATUS, default="active")
    owner = models.ForeignKey(
        get_user_model(), verbose_name="创建人", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="topics",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "舆情主题"
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["name"]),
        ]

    def __str__(self):
        return self.name

    @property
    def core_keywords(self):
        return list(self.keywords.filter(kind="core").values_list("word", flat=True))

    @property
    def related_keywords(self):
        return list(self.keywords.filter(kind="related").values_list("word", flat=True))

    @property
    def exclude_keywords(self):
        return list(self.keywords.filter(kind="exclude").values_list("word", flat=True))

    def is_in_monitor_window(self, at=None):
        """是否处于监测时间窗口内。"""
        from django.utils import timezone
        now = at or timezone.now()
        if self.monitor_start and now < self.monitor_start:
            return False
        if self.monitor_end and now > self.monitor_end:
            return False
        return True


class TopicKeyword(models.Model):
    """主题关键词（核心/关联/排除）。"""

    topic = models.ForeignKey(Topic, verbose_name="主题", on_delete=models.CASCADE, related_name="keywords")
    word = models.CharField("关键词", max_length=128)
    kind = models.CharField("类型", max_length=8, choices=KEYWORD_KINDS, default="core")

    class Meta:
        verbose_name = "主题关键词"
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=["word"]),
            models.Index(fields=["topic"]),
        ]

    def __str__(self):
        return f"{self.topic.name}/{self.word}({self.kind})"


class TopicExclusionUser(models.Model):
    """排除用户（如官方运营号、黑粉账号）。"""

    topic = models.ForeignKey(Topic, verbose_name="主题", on_delete=models.CASCADE, related_name="excluded_users")
    platform = models.CharField("平台", max_length=16, choices=PLATFORM_CHOICES)
    author_name = models.CharField("作者名", max_length=128)

    class Meta:
        verbose_name = "排除用户"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=["topic", "platform", "author_name"],
                name="uq_topic_platform_author",
            ),
        ]

    def __str__(self):
        return f"{self.topic.name}/{self.platform}/{self.author_name}"
