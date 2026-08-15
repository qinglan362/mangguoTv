from django.contrib import admin

from .models import Topic, TopicExclusionUser, TopicKeyword


class TopicKeywordInline(admin.TabularInline):
    model = TopicKeyword
    extra = 1


class TopicExclusionUserInline(admin.TabularInline):
    model = TopicExclusionUser
    extra = 0


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "status", "platforms", "collection_interval", "monitor_start", "monitor_end")
    list_filter = ("status", "platforms")
    search_fields = ("name",)
    inlines = [TopicKeywordInline, TopicExclusionUserInline]
