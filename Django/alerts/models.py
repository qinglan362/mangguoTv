"""舆情预警模型。"""
from django.contrib.auth import get_user_model
from django.db import models

RULE_TYPES = [
    ("negative_keyword", "负面关键词出现"),
    ("like_threshold", "负面帖点赞超阈值"),
    ("negative_spike", "负面帖数量激增"),
    ("coordinated_posting", "同观点多账号集中发布"),
    ("interaction_spike", "互动量异常增长"),
    ("key_author_negative", "重点账号发布负面"),
]

LEVELS = [
    ("low", "低"),
    ("medium", "中"),
    ("high", "高"),
    ("critical", "严重"),
]

EVENT_STATUS = [
    ("new", "待处理"),
    ("acknowledged", "已确认"),
    ("resolved", "已解决"),
]

NOTIFY_CHANNELS = [
    ("platform", "站内消息"),
    ("email", "邮件"),
]


class AlertRule(models.Model):
    """预警规则。"""

    topic = models.ForeignKey("topics.Topic", verbose_name="主题", on_delete=models.CASCADE, related_name="alert_rules")
    name = models.CharField("规则名称", max_length=128)
    rule_type = models.CharField("规则类型", max_length=32, choices=RULE_TYPES)
    config = models.JSONField("配置参数", default=dict, blank=True)
    level = models.CharField("关注等级", max_length=8, choices=LEVELS, default="medium")
    enabled = models.BooleanField("启用", default=True)
    notify_channels = models.JSONField("通知渠道", default=list, blank=True)
    notify_recipients = models.JSONField("通知对象", default=list, blank=True)
    cooldown_minutes = models.IntegerField("冷却时间(分钟)", default=60, help_text="同规则触发防抖")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "预警规则"
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=["topic", "enabled"]),
        ]

    def __str__(self):
        return f"{self.topic.name}/{self.name}"


class AlertEvent(models.Model):
    """预警事件。"""

    rule = models.ForeignKey(AlertRule, verbose_name="规则", on_delete=models.CASCADE, related_name="events")
    topic = models.ForeignKey("topics.Topic", verbose_name="主题", on_delete=models.CASCADE, related_name="alert_events")
    triggered_at = models.DateTimeField("触发时间", auto_now_add=True)
    level = models.CharField("关注等级", max_length=8, choices=LEVELS)
    reason = models.TextField("触发原因")
    matched_posts = models.JSONField("相关帖子", default=list, blank=True)
    matched_keywords = models.JSONField("命中关键词", default=list, blank=True)
    metrics = models.JSONField("指标快照", default=dict, blank=True)
    status = models.CharField("状态", max_length=16, choices=EVENT_STATUS, default="new")
    handled_by = models.ForeignKey(
        get_user_model(), verbose_name="处理人", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="handled_alert_events",
    )
    handled_at = models.DateTimeField("处理时间", null=True, blank=True)

    class Meta:
        verbose_name = "预警事件"
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=["topic", "triggered_at"]),
            models.Index(fields=["status", "triggered_at"]),
        ]

    def __str__(self):
        return f"Alert#{self.id} {self.level} {self.triggered_at:%m-%d %H:%M}"


class AlertNotification(models.Model):
    """通知记录。"""

    NOTIFY_STATUS = [
        ("pending", "待发送"),
        ("sent", "已发送"),
        ("failed", "失败"),
    ]
    event = models.ForeignKey(AlertEvent, verbose_name="事件", on_delete=models.CASCADE, related_name="notifications")
    channel = models.CharField("渠道", max_length=16, choices=NOTIFY_CHANNELS)
    recipient = models.CharField("接收方", max_length=128)
    status = models.CharField("状态", max_length=16, choices=NOTIFY_STATUS, default="pending")
    sent_at = models.DateTimeField("发送时间", null=True, blank=True)
    error_message = models.TextField("错误信息", null=True, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "通知记录"
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"Notify{self.id} {self.channel}->{self.recipient} {self.status}"
