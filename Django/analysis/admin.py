from django.contrib import admin

from .models import AnalysisResult, Entity, ManualCorrection, PostEntity, Viewpoint


@admin.register(AnalysisResult)
class AnalysisResultAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "topic", "is_related", "sentiment", "sentiment_source", "heat_score", "analyzed_at")
    list_filter = ("sentiment", "sentiment_source", "is_related")


@admin.register(Entity)
class EntityAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "type", "mention_count")
    list_filter = ("type",)
    search_fields = ("name",)


@admin.register(PostEntity)
class PostEntityAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "entity", "mention")


@admin.register(Viewpoint)
class ViewpointAdmin(admin.ModelAdmin):
    list_display = ("id", "topic", "sentiment", "mention_count", "text")
    search_fields = ("text",)


@admin.register(ManualCorrection)
class ManualCorrectionAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "field", "corrected_value", "corrected_by", "corrected_at")
    list_filter = ("field",)
