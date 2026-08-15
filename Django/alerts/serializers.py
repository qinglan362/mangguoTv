"""预警模块 API 序列化器。"""
from rest_framework import serializers

from alerts.models import AlertEvent, AlertNotification, AlertRule

RULE_TYPE_CHOICES = {
    "negative_keyword": "负面关键词出现",
    "like_threshold": "负面帖点赞超阈值",
    "negative_spike": "负面帖数量激增",
    "coordinated_posting": "同观点多账号集中发布",
    "interaction_spike": "互动量异常增长",
    "key_author_negative": "重点账号发布负面",
}


class AlertRuleSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source="topic.name", read_only=True)
    rule_type_label = serializers.SerializerMethodField()

    class Meta:
        model = AlertRule
        fields = "__all__"
        read_only_fields = ("created_at", "updated_at")

    def get_rule_type_label(self, obj):
        return RULE_TYPE_CHOICES.get(obj.rule_type, obj.rule_type)

    def validate_rule_type(self, value):
        if value not in RULE_TYPE_CHOICES:
            raise serializers.ValidationError(f"不支持的规则类型：{value}")
        return value


class AlertEventSerializer(serializers.ModelSerializer):
    rule_name = serializers.CharField(source="rule.name", read_only=True)
    rule_type = serializers.CharField(source="rule.rule_type", read_only=True)
    topic_name = serializers.CharField(source="topic.name", read_only=True)
    level_label = serializers.CharField(source="get_level_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = AlertEvent
        fields = "__all__"
        read_only_fields = ("triggered_at",)


class AlertNotificationSerializer(serializers.ModelSerializer):
    channel_label = serializers.CharField(source="get_channel_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = AlertNotification
        fields = "__all__"
