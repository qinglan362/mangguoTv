"""舆情主题 API 视图。"""
from datetime import datetime, time

from django.db.models import Count
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from analysis.models import AnalysisResult
from alerts.models import AlertEvent
from posts.models import PostTopicHit
from tasks.models import CollectionRun
from tasks.services.dispatcher import enqueue_run, execute_run
from topics.models import Topic, TopicKeyword
from topics.serializers import TopicCreateSerializer, TopicSerializer


def _wait_run_finished(run_id, timeout: float = 60.0):
    """轮询等待一个采集运行结束（派发线程已抢占时，用于同步返回结果）。"""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = CollectionRun.objects.filter(pk=run_id).first()
        if run and run.status in ("success", "failed", "canceled"):
            return run
        time.sleep(0.5)
    return CollectionRun.objects.filter(pk=run_id).first()


class TopicViewSet(viewsets.ModelViewSet):
    queryset = Topic.objects.all()
    serializer_class = TopicSerializer

    def get_queryset(self):
        qs = super().get_queryset().filter(status__in=["active", "paused", "archived"])
        name = self.request.query_params.get("name")
        if name:
            qs = qs.filter(name__icontains=name)
        s = self.request.query_params.get("status")
        if s:
            qs = qs.filter(status=s)
        return qs.prefetch_related("keywords", "excluded_users")

    def get_serializer_class(self):
        if self.action == "create":
            return TopicCreateSerializer
        return TopicSerializer

    def perform_destroy(self, instance):
        """硬删除主题，并清理该主题采集到的帖子。

        - 专属帖子（仅本主题命中）：连同其分析结果/互动快照/评论等一并删除；
        - 共享帖子（其他主题也命中）：仅解除与本主题的关联，其分析结果归属
          转移到仍命中的主题，避免误删其他主题的数据。
        """
        from analysis.models import AnalysisResult
        from posts.models import Author, Post, PostTopicHit

        hit_qs = PostTopicHit.objects.filter(topic=instance)
        post_ids = list(hit_qs.values_list("post_id", flat=True))
        if post_ids:
            shared_ids = set(
                PostTopicHit.objects.filter(post_id__in=post_ids)
                .exclude(topic=instance)
                .values_list("post_id", flat=True),
            )
            # 共享帖的分析结果若归属本主题，转移到仍命中的其他主题（AnalysisResult 按帖唯一）
            if shared_ids:
                for analysis in AnalysisResult.objects.filter(
                    topic=instance, post_id__in=list(shared_ids),
                ):
                    other = PostTopicHit.objects.filter(post_id=analysis.post_id).exclude(topic=instance).order_by("id").first()
                    if other:
                        analysis.topic_id = other.topic_id
                        analysis.save(update_fields=["topic"])
            # 专属帖子硬删除（级联清理命中/关键词命中/快照/分析/评论等）
            exclusive_ids = [pid for pid in post_ids if pid not in shared_ids]
            if exclusive_ids:
                author_ids = list(
                    Post.objects.filter(id__in=exclusive_ids)
                    .exclude(author__isnull=True)
                    .values_list("author_id", flat=True)
                )
                Post.objects.filter(id__in=exclusive_ids).delete()
                # 清理不再被任何帖子引用的孤儿作者（仅属于被删帖子）
                if author_ids:
                    Author.objects.filter(pk__in=author_ids, posts__isnull=True).delete()
        # 主题本身硬删除：关键词/排除用户/规则/事件/通知/运行记录/报告/摘要/观点等由外键级联清理
        instance.delete()

    def update(self, request, *args, **kwargs):
        """PATCH 更新：额外支持 keywords 全量替换。"""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        # 关键词全量替换（提供 keywords 数组时）
        if "keywords" in request.data:
            words = request.data["keywords"]
            TopicKeyword.objects.filter(topic=instance).delete()
            for kw in words:
                if isinstance(kw, dict) and kw.get("word"):
                    TopicKeyword.objects.create(topic=instance, word=kw["word"], kind=kw.get("kind", "core"))
                elif isinstance(kw, str) and kw.strip():
                    TopicKeyword.objects.create(topic=instance, word=kw.strip(), kind="core")
            self._sync(instance)

        # 排除用户全量替换（提供 excluded_users 数组时；M4 前端可配排除用户）
        if "excluded_users" in request.data:
            users = request.data["excluded_users"]
            from topics.models import TopicExclusionUser
            TopicExclusionUser.objects.filter(topic=instance).delete()
            for u in users:
                if isinstance(u, dict) and u.get("author_name") and u.get("platform"):
                    TopicExclusionUser.objects.create(
                        topic=instance, platform=u["platform"], author_name=u["author_name"],
                    )
            self._sync(instance)

        return Response(TopicSerializer(instance, context=self.request).data)

    def _sync(self, topic):
        try:
            from tasks.services.scheduler import sync_topic
            sync_topic(topic)
        except Exception:
            pass

    # ---------- 自定义动作 ----------
    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        topic = self.get_object()
        topic.status = "paused"
        topic.save(update_fields=["status"])
        self._sync(topic)
        return Response({"status": "paused"})

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        topic = self.get_object()
        topic.status = "active"
        topic.save(update_fields=["status"])
        self._sync(topic)
        return Response({"status": "active"})

    @action(detail=True, methods=["post"])
    def collect_now(self, request, pk=None):
        """手动触发立即采集（同步执行，返回运行结果）。

        真实平台（小红书/微博）的内置采集器未启用时不再产生失败记录，
        由前端路由到 MediaCrawler 采集流程。
        """
        from tasks.services.dispatch import claim_specific_run, release_run

        from collectors.registry import get_collector

        topic = self.get_object()
        platforms = topic.platforms or ["mock"]
        runs = []
        for platform in platforms:
            if platform in ("xiaohongshu", "weibo"):
                # 真实平台统一走 MediaCrawler（前端「立即采集」已路由），内置采集器不再参与
                runs.append({
                    "run_id": None,
                    "platform": platform,
                    "status": "skipped",
                    "fetched_count": 0,
                    "new_count": 0,
                    "duplicate_count": 0,
                    "updated_count": 0,
                    "error_message": "该平台未启用内置采集器；小红书/微博请用 MediaCrawler 采集",
                })
                continue
            run = enqueue_run(topic, platform, trigger_type="manual")
            if claim_specific_run(run.id):
                try:
                    run = execute_run(run.id)
                finally:
                    release_run(run.id)
            else:
                # 派发线程已抢占该 run：轮询等待其完成，保证手动触发能拿到结果（H5）
                run = _wait_run_finished(run.id)
            runs.append({
                "run_id": run.id,
                "platform": platform,
                "status": run.status,
                "fetched_count": run.fetched_count,
                "new_count": run.new_count,
                "duplicate_count": run.duplicate_count,
                "updated_count": run.updated_count,
                "error_message": run.error_message,
            })
        return Response({"runs": runs})

    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        """主题概览统计。"""
        topic = self.get_object()
        now = timezone.now()
        today_start = timezone.make_aware(datetime.combine(now.date(), time.min))
        hits = PostTopicHit.objects.filter(topic=topic)
        # 跨主题共享帖的分析结果只存一条（post 为 OneToOne），归属主题经命中表关联，
        # 与看板口径一致，避免共享帖在非首分析主题下漏计
        analyses = AnalysisResult.objects.filter(post_id__in=hits.values("post_id"))
        last_run = CollectionRun.objects.filter(topic=topic).order_by("-created_at").first()

        sentiment_dist = {}
        platform_dist = {}
        for item in analyses.values("sentiment"):
            key = item["sentiment"] or "unknown"
            sentiment_dist[key] = sentiment_dist.get(key, 0) + 1

        for item in hits.values("post__platform").annotate(c=Count("id")):
            platform_dist[item["post__platform"]] = item["c"]

        data = {
            "post_count": hits.count(),
            "new_today": hits.filter(first_hit_at__gte=today_start).count(),
            "sentiment_distribution": sentiment_dist,
            "negative_count": analyses.filter(sentiment="negative").count(),
            "alert_count": AlertEvent.objects.filter(topic=topic, status="new").count(),
            "last_run_status": last_run.status if last_run else None,
            "platform_distribution": platform_dist,
        }
        return Response(data)
