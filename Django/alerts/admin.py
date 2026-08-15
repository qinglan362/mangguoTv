from django.contrib import admin

from .models import AlertEvent, AlertNotification, AlertRule


@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    list_display = ("id", "topic", "name", "rule_type", "level", "enabled", "cooldown_minutes")
    list_filter = ("rule_type", "level", "enabled")


@admin.register(AlertEvent)
class AlertEventAdmin(admin.ModelAdmin):
    list_display = ("id", "rule", "topic", "level", "status", "triggered_at", "handled_at")
    list_filter = ("level", "status")


@admin.register(AlertNotification)
class AlertNotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "event", "channel", "recipient", "status", "sent_at")
    list_filter = ("channel", "status")
