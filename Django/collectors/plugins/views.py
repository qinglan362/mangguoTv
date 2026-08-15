"""采集器插件 API：评论查询（只读）。"""
from rest_framework import viewsets

from .models import PostComment
from .serializers import PostCommentSerializer


class PostCommentViewSet(viewsets.ReadOnlyModelViewSet):
    """平台评论查询。

    - ?post=<帖子DB id>：查询某帖的评论（前端帖子详情用）
    - ?platform=<平台>&platform_post_id=<平台侧帖子ID>：按平台标识查询
    """

    queryset = PostComment.objects.select_related("post").all()
    serializer_class = PostCommentSerializer
    filterset_fields = ("post", "platform")

    def get_queryset(self):
        qs = super().get_queryset()
        platform_post_id = self.request.query_params.get("platform_post_id")
        if platform_post_id:
            qs = qs.filter(platform_post_id=platform_post_id)
        return qs.order_by("-like_count", "-published_at")
