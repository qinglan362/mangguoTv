from django.urls import path

from dashboard.views import (
    heat_trend,
    hot_posts,
    interaction_trend,
    key_authors,
    negative_posts,
    overview,
    platform_distribution,
    sentiment_distribution,
    top_keywords,
    topic_compare,
    trend,
)

app_name = "dashboard"

urlpatterns = [
    path("overview/", overview, name="overview"),
    path("trend/", trend, name="trend"),
    path("platform-distribution/", platform_distribution, name="platform-distribution"),
    path("sentiment-distribution/", sentiment_distribution, name="sentiment-distribution"),
    path("interaction-trend/", interaction_trend, name="interaction-trend"),
    path("hot-posts/", hot_posts, name="hot-posts"),
    path("negative-posts/", negative_posts, name="negative-posts"),
    path("top-keywords/", top_keywords, name="top-keywords"),
    path("heat-trend/", heat_trend, name="heat-trend"),
    path("key-authors/", key_authors, name="key-authors"),
    path("topic-compare/", topic_compare, name="topic-compare"),
]
