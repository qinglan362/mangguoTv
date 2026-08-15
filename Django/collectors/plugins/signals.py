"""插件信号：帖子入库后回填评论外键。"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from posts.models import Post

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Post)
def _link_comments_after_post_created(sender, instance, created, **kwargs):
    """帖子新建后，把采集时暂存（post 为空）的同平台同帖评论回填外键。"""
    if not created:
        return
    try:
        from .models import PostComment

        PostComment.objects.filter(
            platform=instance.platform,
            platform_post_id=instance.post_id,
            post__isnull=True,
        ).update(post=instance)
    except Exception:
        logger.exception("link comments for post %s failed", instance.pk)
