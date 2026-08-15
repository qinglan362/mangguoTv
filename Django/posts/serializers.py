"""帖子序列化器。"""
from rest_framework import serializers

from posts.models import Author, Post, PostSnapshot, PostTopicHit


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = ["id", "platform", "author_id", "name", "avatar_url", "follower_count", "profile_url", "is_key_author"]


class PostTopicHitSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source="topic.name", read_only=True)

    class Meta:
        model = PostTopicHit
        fields = ["id", "topic", "topic_name", "matched_keywords", "matched_count", "first_hit_at"]


class PostSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.name", read_only=True, allow_null=True)
    author_followers = serializers.IntegerField(source="author.follower_count", read_only=True, default=0)
    sentiment = serializers.SerializerMethodField()
    heat_score = serializers.SerializerMethodField()
    topic_ids = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            "id", "post_id", "platform", "url", "title", "content", "author", "author_name",
            "author_followers", "published_at", "collected_at", "like_count", "comment_count",
            "share_count", "favorite_count", "hashtags", "cover_url", "images", "sentiment",
            "heat_score", "topic_ids",
        ]

    def get_sentiment(self, obj):
        return getattr(getattr(obj, "analysis", None), "sentiment", None)

    def get_heat_score(self, obj):
        return getattr(getattr(obj, "analysis", None), "heat_score", 0)

    def get_topic_ids(self, obj):
        return [h.topic_id for h in obj.topic_hits.all()]


class PostDetailSerializer(PostSerializer):
    author = AuthorSerializer(read_only=True)
    topic_hits = PostTopicHitSerializer(many=True, read_only=True)
    analysis = serializers.SerializerMethodField()

    class Meta(PostSerializer.Meta):
        fields = PostSerializer.Meta.fields + ["topic_hits", "analysis"]

    def get_analysis(self, obj):
        a = getattr(obj, "analysis", None)
        if a is None:
            return None
        from analysis.serializers import AnalysisResultSerializer
        return AnalysisResultSerializer(a).data


class PostSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostSnapshot
        fields = ["id", "like_count", "comment_count", "share_count", "favorite_count", "collected_at"]
