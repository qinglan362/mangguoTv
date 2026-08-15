from django.urls import include, path
from rest_framework.routers import DefaultRouter

from topics.views import TopicViewSet

router = DefaultRouter()
router.register("", TopicViewSet, basename="topic")

urlpatterns = [
    path("", include(router.urls)),
]
