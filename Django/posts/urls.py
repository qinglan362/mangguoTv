from django.urls import include, path
from rest_framework.routers import DefaultRouter

from posts.views import PostViewSet

router = DefaultRouter()
router.register("", PostViewSet, basename="post")

app_name = "posts"

urlpatterns = [
    path("", include(router.urls)),
]
