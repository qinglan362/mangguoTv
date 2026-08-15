"""采集运行序列化器。"""
from rest_framework import serializers

from tasks.models import CollectionRun


class CollectionRunSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source="topic.name", read_only=True)

    class Meta:
        model = CollectionRun
        fields = [
            "id", "topic", "topic_name", "platform", "status",
            "trigger_type", "started_at", "finished_at", "fetched_count",
            "new_count", "updated_count", "duplicate_count", "retry_count",
            "error_message", "cursor", "created_at",
        ]
