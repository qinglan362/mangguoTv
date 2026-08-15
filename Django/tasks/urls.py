from django.urls import include, path
from rest_framework.routers import DefaultRouter

from tasks.views import CollectionRunViewSet, scheduler_status

router = DefaultRouter()
router.register("runs", CollectionRunViewSet, basename="run")

app_name = "tasks"

urlpatterns = [
    path("", include(router.urls)),
    path("status/", scheduler_status, name="status"),
]
