"""项目级视图：健康检查等。"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from django.conf import settings


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """健康检查：版本、调度器运行状态。"""
    scheduler_running = False
    try:
        from tasks.services.scheduler import get_scheduler
        scheduler_running = get_scheduler().running
    except Exception:
        scheduler_running = False

    return Response({
        "status": "ok",
        "version": "1.0.0",
        "env": getattr(settings, "DJANGO_ENV", "dev"),
        "timezone": settings.TIME_ZONE,
        "scheduler_running": scheduler_running,
    })
