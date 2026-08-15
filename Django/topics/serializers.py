"""舆情主题序列化器。"""
from rest_framework import serializers

from topics.models import Topic, TopicExclusionUser, TopicKeyword


class TopicKeywordSerializer(serializers.ModelSerializer):
    class Meta:
        model = TopicKeyword
        fields = ["id", "topic", "word", "kind"]
        read_only_fields = ["id", "topic"]


class TopicExclusionUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = TopicExclusionUser
        fields = ["id", "topic", "platform", "author_name"]
        read_only_fields = ["id", "topic"]


class TopicSerializer(serializers.ModelSerializer):
    keywords = TopicKeywordSerializer(many=True, read_only=True)
    excluded_users = TopicExclusionUserSerializer(many=True, read_only=True)
    collecting = serializers.SerializerMethodField()

    class Meta:
        model = Topic
        fields = [
            "id", "name", "description", "platforms", "collection_interval",
            "monitor_start", "monitor_end", "status", "owner", "collecting",
            "created_at", "updated_at", "keywords", "excluded_users",
        ]
        read_only_fields = ["id", "owner", "created_at", "updated_at", "collecting"]

    def get_collecting(self, obj) -> bool:
        """主题是否正在采集（MediaCrawler 运行/排队/导入中，或内置采集运行 pending/running）。

        供前端主题列表展示「爬取中」状态；点击可打开采集过程页面。
        """
        try:
            from collectors.plugins.models import MediaCrawlerRun
            if MediaCrawlerRun.objects.filter(
                topic=obj, status__in=["queued", "running", "importing"],
            ).exists():
                return True
        except Exception:
            pass
        try:
            from tasks.models import CollectionRun
            return CollectionRun.objects.filter(
                topic=obj, status__in=["pending", "running"],
            ).exists()
        except Exception:
            return False

    def validate_collection_interval(self, value):
        if not (5 <= value <= 1440):
            raise serializers.ValidationError("采集频率必须在 5~1440 分钟之间")
        return value

    def validate_platforms(self, value):
        allowed = {"xiaohongshu", "weibo", "mock"}
        if not value:
            raise serializers.ValidationError("请至少选择一个采集平台")
        for p in value:
            if p not in allowed:
                raise serializers.ValidationError("不支持的平台: %s" % p)
        return value


class TopicCreateSerializer(TopicSerializer):
    """创建主题：允许内联提交关键词。"""

    keywords_inline = serializers.ListField(
        child=serializers.DictField(), write_only=True, required=False, default=list,
    )
    excluded_users_inline = serializers.ListField(
        child=serializers.DictField(), write_only=True, required=False, default=list,
    )

    class Meta(TopicSerializer.Meta):
        fields = TopicSerializer.Meta.fields + ["keywords_inline", "excluded_users_inline"]

    def create(self, validated_data):
        keywords_inline = validated_data.pop("keywords_inline", [])
        excluded_inline = validated_data.pop("excluded_users_inline", [])
        request = self.context.get("request")
        validated_data["owner"] = request.user if request and request.user.is_authenticated else None
        topic = super().create(validated_data)

        for kw in keywords_inline:
            if kw.get("word"):
                TopicKeyword.objects.create(
                    topic=topic, word=kw["word"], kind=kw.get("kind", "core"),
                )
        for eu in excluded_inline:
            if eu.get("author_name") and eu.get("platform"):
                TopicExclusionUser.objects.create(
                    topic=topic, platform=eu["platform"], author_name=eu["author_name"],
                )
        return topic


class TopicStatsSerializer(serializers.Serializer):
    """主题概览统计。"""

    post_count = serializers.IntegerField()
    new_today = serializers.IntegerField()
    sentiment_distribution = serializers.DictField()
    negative_count = serializers.IntegerField()
    alert_count = serializers.IntegerField()
    last_run_status = serializers.CharField(allow_null=True)
    platform_distribution = serializers.DictField()
