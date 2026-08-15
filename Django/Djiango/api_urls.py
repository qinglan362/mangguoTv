"""REST API 根路由（全部挂 /api/ 前缀）。"""
from django.urls import include, path

from .views import health

urlpatterns = [
    path("health/", health, name="health"),
    path("", include("accounts.urls")),
    path("topics/", include("topics.urls")),
    path("collectors/", include("collectors.urls")),
    path("crawler/", include("collectors.plugins.urls")),  # 采集器插件评论 API（可随插件目录删除）
    path("tasks/", include("tasks.urls")),
    path("posts/", include("posts.urls")),
    path("analysis/", include("analysis.urls")),
    path("alerts/", include("alerts.urls")),
    path("reports/", include("reports.urls")),
    path("dashboard/", include("dashboard.urls")),
]
