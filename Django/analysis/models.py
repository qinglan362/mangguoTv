"""舆情内容识别结果模型。"""
from django.contrib.auth import get_user_model
from django.db import models

SENTIMENT_CHOICES = [
    ("positive", "正面"),
    ("neutral", "中性"),
    ("unknown", "未知"),
    ("negative", "负面"),
]

SENTIMENT_SOURCES = [
    ("rule", "规则"),
    ("llm", "大模型"),
    ("manual", "人工修正"),
]

ENTITY_TYPES = [
    ("brand", "品牌"),
    ("drama", "剧集"),
    ("variety", "综艺"),
    ("actor", "艺人"),
    ("character", "角色"),
    ("tag", "话题"),
]


class AnalysisResult(models.Model):
    """每帖分析结果（相关性/情感/观点/实体/热度）。"""

    post = models.OneToOneField("posts.Post", verbose_name="帖子", on_delete=models.CASCADE, related_name="analysis")
    topic = models.ForeignKey("topics.Topic", verbose_name="主题", on_delete=models.CASCADE, related_name="analyses")
    related_score = models.FloatField("相关度", default=0)
    is_related = models.BooleanField("是否相关", default=False)
    sentiment = models.CharField("情感", max_length=16, choices=SENTIMENT_CHOICES, default="unknown")
    sentiment_score = models.FloatField("情感得分", default=0)
    sentiment_source = models.CharField("情感来源", max_length=8, choices=SENTIMENT_SOURCES, default="llm")
    key_viewpoints = models.JSONField("核心观点", default=list, blank=True)
    key_entities = models.JSONField("关键实体", default=list, blank=True)
    high_freq_keywords = models.JSONField("高频关键词", default=list, blank=True)
    heat_score = models.FloatField("热度分", default=0)
    analyzed_at = models.DateTimeField("分析时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "帖子分析结果"
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=["topic", "sentiment"]),
            models.Index(fields=["topic", "is_related"]),
            models.Index(fields=["topic", "heat_score"]),
            models.Index(fields=["post"]),
        ]

    def __str__(self):
        return f"Analysis{self.id} Post{self.post_id} {self.sentiment}"


class Entity(models.Model):
    """标准化实体库（品牌/剧综/艺人/角色）。"""

    name = models.CharField("实体名", max_length=128)
    type = models.CharField("类型", max_length=16, choices=ENTITY_TYPES)
    aliases = models.JSONField("别名", default=list, blank=True)
    mention_count = models.IntegerField("提及次数", default=0)

    class Meta:
        verbose_name = "实体"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(fields=["name", "type"], name="uq_entity_name_type"),
        ]

    def __str__(self):
        return f"{self.name}({self.type})"


class PostEntity(models.Model):
    """帖子↔实体关联。"""

    post = models.ForeignKey("posts.Post", verbose_name="帖子", on_delete=models.CASCADE, related_name="entities")
    entity = models.ForeignKey(Entity, verbose_name="实体", on_delete=models.CASCADE, related_name="posts")
    mention = models.CharField("原文提及", max_length=128)

    class Meta:
        verbose_name = "帖子实体"
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=["entity"]),
            models.Index(fields=["post"]),
        ]

    def __str__(self):
        return f"{self.entity.name}@{self.post_id}"


class Viewpoint(models.Model):
    """观点（从帖子中提取的核心观点）。"""

    topic = models.ForeignKey("topics.Topic", verbose_name="主题", on_delete=models.CASCADE, related_name="viewpoints")
    text = models.TextField("观点文本")
    sentiment = models.CharField("情感", max_length=16, choices=SENTIMENT_CHOICES, default="neutral")
    mention_count = models.IntegerField("提及次数", default=0)
    representative_post = models.ForeignKey(
        "posts.Post", verbose_name="代表帖子", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "观点"
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=["topic", "mention_count"]),
        ]

    def __str__(self):
        return self.text[:30]


class ManualCorrection(models.Model):
    """人工修正记录（可回填模型/规则优化）。"""

    FIELD_CHOICES = [
        ("sentiment", "情感倾向"),
        ("related", "相关性"),
        ("viewpoint", "核心观点"),
        ("entities", "关键实体"),
    ]
    post = models.ForeignKey("posts.Post", verbose_name="帖子", on_delete=models.CASCADE, related_name="corrections")
    analysis = models.ForeignKey(AnalysisResult, verbose_name="分析结果", on_delete=models.CASCADE)
    field = models.CharField("修正字段", max_length=16, choices=FIELD_CHOICES)
    original_value = models.TextField("原始值")
    corrected_value = models.TextField("修正值")
    corrected_by = models.ForeignKey(
        get_user_model(), verbose_name="修正人", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="corrections",
    )
    note = models.TextField("修正说明", blank=True, default="")
    corrected_at = models.DateTimeField("修正时间", auto_now_add=True)

    class Meta:
        verbose_name = "人工修正记录"
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=["post"]),
        ]

    def __str__(self):
        return f"Fix{self.id} Post{self.post_id} {self.field}"