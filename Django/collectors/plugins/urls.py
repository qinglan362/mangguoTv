"""采集器插件路由：/api/crawler/*。"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .mediacrawler.views import (
    mediacrawler_import,
    mediacrawler_run,
    mediacrawler_status,
    mediacrawler_stop,
)
from .views import PostCommentViewSet

app_name = "collectors_plugins"

router = DefaultRouter()
router.register("comments", PostCommentViewSet, basename="plugin-comment")

urlpatterns = [
    path("", include(router.urls)),
    path("mediacrawler/run/", mediacrawler_run, name="mediacrawler-run"),
    path("mediacrawler/status/", mediacrawler_status, name="mediacrawler-status"),
    path("mediacrawler/stop/", mediacrawler_stop, name="mediacrawler-stop"),
    path("mediacrawler/import/", mediacrawler_import, name="mediacrawler-import"),
]
