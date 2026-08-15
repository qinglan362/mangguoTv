"""预警模块 API 视图。"""
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from alerts.models import AlertEvent, AlertNotification, AlertRule
from alerts.serializers import AlertEventSerializer, AlertNotificationSerializer, AlertRuleSerializer


class AlertRuleViewSet(viewsets.ModelViewSet):
    """预警规则 CRUD。支持 ?topic= 与 ?enabled= 过滤。"""

    queryset = AlertRule.objects.all()
    serializer_class = AlertRuleSerializer
    filterset_fields = ("topic", "enabled")

    def get_queryset(self):
        qs = super().get_queryset()
        topic = self.request.query_params.get("topic")
        if topic:
            qs = qs.filter(topic=topic)
        return qs.select_related("topic").order_by("-updated_at")


class AlertEventViewSet(viewsets.ReadOnlyModelViewSet):
    """预警事件查询与确认。"""

    queryset = AlertEvent.objects.all()
    serializer_class = AlertEventSerializer
    filterset_fields = ("topic", "status", "level", "rule")

    def get_queryset(self):
        qs = super().get_queryset()
        topic = self.request.query_params.get("topic")
        if topic:
            qs = qs.filter(topic=topic)
        return qs.select_related("topic", "rule").order_by("-triggered_at")

    @action(detail=True, methods=["post"])
    def ack(self, request, pk=None):
        """确认预警事件。"""
        event = self.get_object()
        event.status = "acknowledged"
        event.handled_by = request.user if request.user.is_authenticated else None
        event.handled_at = timezone.now()
        event.save(update_fields=["status", "handled_by", "handled_at"])
        return Response(self.get_serializer(event).data)

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        """标记为已解决。"""
        event = self.get_object()
        event.status = "resolved"
        event.handled_by = request.user if request.user.is_authenticated else None
        event.handled_at = timezone.now()
        event.save(update_fields=["status", "handled_by", "handled_at"])
        return Response(self.get_serializer(event).data)


class AlertNotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """通知记录查询。"""

    queryset = AlertNotification.objects.all()
    serializer_class = AlertNotificationSerializer
    filterset_fields = ("status", "channel", "event")

    def get_queryset(self):
        return super().get_queryset().select_related("event").order_by("-created_at")
