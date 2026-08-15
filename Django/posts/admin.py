from django.contrib import admin

from .models import Author, Post, PostKeywordHit, PostSnapshot, PostTopicHit


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "platform", "follower_count", "is_key_author")
    list_filter = ("platform", "is_key_author")
    search_fields = ("name",)


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("id", "post_id", "platform", "author", "like_count", "comment_count", "published_at", "collected_at")
    list_filter = ("platform",)
    search_fields = ("content", "post_id")


@admin.register(PostTopicHit)
class PostTopicHitAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "topic", "matched_count", "first_hit_at")
    search_fields = ("post__content", "topic__name")


@admin.register(PostKeywordHit)
class PostKeywordHitAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "topic", "keyword")
    search_fields = ("keyword",)


@admin.register(PostSnapshot)
class PostSnapshotAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "like_count", "comment_count", "collected_at")
