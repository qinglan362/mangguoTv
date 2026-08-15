"""评论入库服务（插件自有表 PostComment）。"""
import logging

from posts.models import Post

logger = logging.getLogger(__name__)


def store_comments(platform: str, post_id: str, comments: list) -> int:
    """把采集到的评论写入 PostComment。

    post 尚未入库时先以 (platform, post_id) 暂存（post 外键置空），
    帖子入库后由本插件的 post_save 信号回填外键。返回新增条数。
    """
    from .models import PostComment

    post = Post.objects.filter(platform=platform, post_id=post_id).first()
    created = 0
    for c in comments or []:
        comment_id = str(c.get("comment_id") or "").strip()
        if not comment_id:
            continue
        try:
            _, is_new = PostComment.objects.update_or_create(
                platform=platform,
                comment_id=comment_id,
                defaults={
                    "post": post,
                    "platform_post_id": post_id,
                    "author_name": (c.get("author_name") or "")[:128],
                    "content": (c.get("content") or "").strip(),
                    "like_count": int(c.get("like_count") or 0),
                    "published_at": c.get("published_at"),
                },
            )
            created += int(is_new)
        except Exception:
            logger.exception("store comment failed platform=%s cid=%s", platform, comment_id)
    return created
