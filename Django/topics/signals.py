"""主题信号：创建/更新/删除时联动调度器注册/更新/移除 job。"""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from topics.models import Topic


def _sync_topic_safe(topic):
    try:
        from tasks.services.scheduler import sync_topic
        sync_topic(topic)
    except Exception:
        # 调度器未启动时静默（runscheduler 启动时会统一重建）
        pass


@receiver(post_save, sender=Topic)
def topic_saved(sender, instance, **kwargs):
    _sync_topic_safe(instance)


@receiver(post_delete, sender=Topic)
def topic_deleted(sender, instance, **kwargs):
    try:
        from tasks.services.scheduler import get_scheduler
        scheduler = get_scheduler()
        scheduler.remove_job("topic_%d" % instance.id)
    except Exception:
        pass
