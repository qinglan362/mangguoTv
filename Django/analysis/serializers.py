"""内容识别序列化器。

仅保留 AnalysisResultSerializer：供帖子详情（posts.PostDetailSerializer 嵌套）
与人工修正接口使用；实体/观点/聚类/摘要序列化器随对应前端页面一并移除。
"""
from rest_framework import serializers

from analysis.models import AnalysisResult


class AnalysisResultSerializer(serializers.ModelSerializer):
    post_content = serializers.CharField(source="post.content", read_only=True)
    post_url = serializers.URLField(source="post.url", read_only=True)
    post_platform = serializers.CharField(source="post.platform", read_only=True)
    topic_name = serializers.CharField(source="topic.name", read_only=True)

    class Meta:
        model = AnalysisResult
        fields = [
            "id", "post", "post_content", "post_url", "post_platform", "topic", "topic_name",
            "related_score", "is_related", "sentiment", "sentiment_score",
            "sentiment_source", "key_viewpoints", "key_entities", "high_freq_keywords",
            "heat_score", "analyzed_at", "updated_at",
        ]
        read_only_fields = fields
