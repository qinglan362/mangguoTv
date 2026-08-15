"""采集器插件序列化器。"""
from rest_framework import serializers

from .models import PostComment


class PostCommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostComment
        fields = [
            "id", "post", "platform", "platform_post_id", "comment_id",
            "author_name", "content", "like_count", "published_at", "collected_at",
        ]
