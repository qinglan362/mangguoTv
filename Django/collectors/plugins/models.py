"""采集器插件自有模型：平台帖子评论。

评论独立成插件应用的表，不侵入核心 posts 模型；
post 外键在帖子入库后由 post_save 信号回填，入库前以 (platform, post_id) 暂存。
"""
from django.db import models


class PostComment(models.Model):
    """从小红书/微博抓取的帖子评论。"""

    post = models.ForeignKey(
        "posts.Post", verbose_name="帖子", null=True, blank=True,
        on_delete=models.CASCADE, related_name="crawled_comments",
    )
    platform = models.CharField("平台", max_length=16)
    platform_post_id = models.CharField("平台侧帖子ID", max_length=128)
    comment_id = models.CharField("平台侧评论ID", max_length=128)
    author_name = models.CharField("评论作者", max_length=128, blank=True, default="")
    content = models.TextField("评论内容", blank=True, default="")
    like_count = models.BigIntegerField("点赞数", default=0)
    published_at = models.DateTimeField("发布时间", null=True, blank=True)
    collected_at = models.DateTimeField("采集时间", auto_now_add=True)

    class Meta:
        verbose_name = "平台评论"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "comment_id"],
                name="uq_plugin_comment_platform_cid",
            ),
        ]
        indexes = [
            models.Index(fields=["platform", "platform_post_id"]),
            models.Index(fields=["post"]),
        ]

    def __str__(self):
        return f"{self.platform}/{self.comment_id}: {self.content[:30]}"

class MediaCrawlerRun(models.Model):
    """一次 MediaCrawler 外部采集运行（命令执行 + 数据导入状态）。"""

    RUN_STATUS = [
        ("running", "运行中"),
        ("queued", "排队中"),
        ("finished", "已完成"),
        ("importing", "导入中"),
        ("failed", "失败"),
        ("stopped", "已停止"),
    ]
    platform = models.CharField("平台", max_length=16, default="xhs")
    topic = models.ForeignKey(
        "topics.Topic", verbose_name="关联主题", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="mediacrawler_runs",
    )
    keywords = models.TextField("关键词", blank=True, default="")
    status = models.CharField("状态", max_length=16, choices=RUN_STATUS, default="running")
    log_path = models.CharField("日志文件", max_length=512, blank=True, default="")
    pid = models.IntegerField("进程号", null=True, blank=True)
    exit_code = models.IntegerField("退出码", null=True, blank=True)
    fetched_count = models.IntegerField("抓取条数", default=0)
    new_count = models.IntegerField("新增条数", default=0)
    duplicate_count = models.IntegerField("重复条数", default=0)
    updated_count = models.IntegerField("更新条数", default=0)
    comment_count = models.IntegerField("导入评论数", default=0)
    error_message = models.TextField("错误信息", blank=True, default="")
    started_at = models.DateTimeField("开始时间", auto_now_add=True)
    finished_at = models.DateTimeField("结束时间", null=True, blank=True)

    class Meta:
        verbose_name = "MediaCrawler 运行记录"
        verbose_name_plural = verbose_name
        ordering = ["-id"]


class MediaCrawlerFileState(models.Model):
    """MediaCrawler 数据文件导入进度（按文件记录已导入行数，增量导入）。"""

    path = models.CharField("文件相对路径", max_length=512, unique=True)
    imported_lines = models.IntegerField("已导入行数", default=0)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "MediaCrawler 导入进度"
        verbose_name_plural = verbose_name
