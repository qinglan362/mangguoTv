"""帖子 API 视图。"""
from django.db.models import Q
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from analysis.models import AnalysisResult
from posts.models import Post, PostSnapshot
from posts.serializers import PostDetailSerializer, PostSerializer, PostSnapshotSerializer


class PostViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Post.objects.select_related("author", "analysis").all()
    serializer_class = PostSerializer

    def get_serializer_class(self):
        if self.action == "retrieve":
            return PostDetailSerializer
        return PostSerializer

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related("topic_hits")
        params = self.request.query_params

        topic = params.get("topic")
        if topic:
            qs = qs.filter(topic_hits__topic_id=topic)

        platform = params.get("platform")
        if platform:
            qs = qs.filter(platform=platform)

        sentiment = params.get("sentiment")
        if sentiment and sentiment != "all":
            qs = qs.filter(analysis__sentiment=sentiment)

        is_related = params.get("is_related")
        if is_related in ("1", "true"):
            qs = qs.filter(analysis__is_related=True)

        q = params.get("q")
        if q:
            qs = qs.filter(Q(content__icontains=q) | Q(title__icontains=q))

        ordering = params.get("ordering", "-published_at")
        if ordering in ("heat_score", "-heat_score"):
            qs = qs.filter(analysis__isnull=False).order_by(ordering.replace("heat_score", "analysis__heat_score"))
        else:
            qs = qs.order_by(ordering)
        return qs.distinct()

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        post = self.get_object()
        snapshots = PostSnapshot.objects.filter(post=post).order_by("collected_at")
        return Response(PostSnapshotSerializer(snapshots, many=True).data)
