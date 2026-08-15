from django.db import models


class TopicKeywordsSnapshot(models.Model):
    """看板高频关键词预计算快照。

    定时任务按标准窗口（最近 7 天）提前算好写入本表，看板接口直接读库
    秒回，不依赖内存缓存、不因进程重启而重新等待 LLM。topic 为空表示
    「全部主题」聚合。
    """

    topic = models.ForeignKey(
        "topics.Topic",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="keyword_snapshots",
        verbose_name="主题",
    )
    window = models.CharField("时间窗口", max_length=16, default="7d")
    keywords = models.JSONField("关键词", default=list, blank=True)
    computed_at = models.DateTimeField("计算时间", auto_now=True)

    class Meta:
        verbose_name = "关键词快照"
        verbose_name_plural = verbose_name

    def __str__(self):
        return "%s/%s" % (self.topic_id or "全部主题", self.window)
