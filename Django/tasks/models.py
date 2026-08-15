"""采集任务与运行记录模型。"""
from django.db import models

RUN_STATUS = [
    ("pending", "待执行"),
    ("running", "执行中"),
    ("success", "成功"),
    ("failed", "失败"),
    ("canceled", "已取消"),
]


class CollectionRun(models.Model):
    """一次采集运行记录。"""

    topic = models.ForeignKey(
        "topics.Topic", verbose_name="主题", on_delete=models.CASCADE, related_name="runs",
    )
    platform = models.CharField("平台", max_length=16)
    status = models.CharField("状态", max_length=16, choices=RUN_STATUS, default="pending")
    trigger_type = models.CharField("触发方式", max_length=16, choices=[("schedule", "定时"), ("manual", "手动")], default="schedule")
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    finished_at = models.DateTimeField("结束时间", null=True, blank=True)
    fetched_count = models.IntegerField("采集条数", default=0)
    new_count = models.IntegerField("新增条数", default=0)
    updated_count = models.IntegerField("更新条数", default=0)
    duplicate_count = models.IntegerField("重复条数", default=0)
    retry_count = models.IntegerField("重试次数", default=0)
    error_message = models.TextField("错误信息", null=True, blank=True)
    cursor = models.CharField("增量游标", max_length=256, null=True, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "采集运行记录"
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["topic", "status", "created_at"]),
        ]

    def __str__(self):
        return f"Run#{self.id} {self.topic_id}({self.platform}) {self.status}"
