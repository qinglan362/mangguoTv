"""数据导出与舆情报告模型。"""
from django.contrib.auth import get_user_model
from django.db import models


class DataExport(models.Model):
    """数据导出任务。"""

    EXPORT_TYPES = [
        ("post", "帖子数据"),
        ("full", "全量数据"),
    ]
    EXPORT_STATUS = [
        ("pending", "待处理"),
        ("running", "处理中"),
        ("done", "完成"),
        ("failed", "失败"),
    ]
    requester = models.ForeignKey(
        get_user_model(), verbose_name="发起人", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="data_exports",
    )
    export_type = models.CharField("导出类型", max_length=16, choices=EXPORT_TYPES, default="post")
    filters = models.JSONField("筛选条件", default=dict, blank=True)
    file_path = models.CharField("文件路径", max_length=256, null=True, blank=True)
    status = models.CharField("状态", max_length=16, choices=EXPORT_STATUS, default="pending")
    row_count = models.IntegerField("导出行数", default=0)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    finished_at = models.DateTimeField("完成时间", null=True, blank=True)

    class Meta:
        verbose_name = "数据导出任务"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"Export{self.id} {self.export_type} {self.status}"


class Report(models.Model):
    """舆情日报/周报。"""

    PERIOD_TYPES = [
        ("daily", "日报"),
        ("weekly", "周报"),
    ]
    REPORT_STATUS = [
        ("generating", "生成中"),
        ("done", "已完成"),
        ("failed", "失败"),
    ]
    topic = models.ForeignKey("topics.Topic", verbose_name="主题", on_delete=models.CASCADE, related_name="reports")
    period_type = models.CharField("周期类型", max_length=8, choices=PERIOD_TYPES)
    report_date = models.DateField("报告日期")
    title = models.CharField("标题", max_length=256)
    summary = models.TextField("摘要", blank=True, default="")
    statistics = models.JSONField("统计信息", default=dict, blank=True)
    chart_image = models.CharField("图表文件", max_length=256, null=True, blank=True)
    status = models.CharField("状态", max_length=16, choices=REPORT_STATUS, default="generating")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    generated_at = models.DateTimeField("完成时间", null=True, blank=True)

    class Meta:
        verbose_name = "舆情报告"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.topic.name} {self.report_date} {self.period_type}"
