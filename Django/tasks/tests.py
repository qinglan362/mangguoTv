"""tasks 模块派发/执行测试。"""
from django.test import TestCase

from tasks.models import CollectionRun
from tasks.services.dispatcher import execute_run
from topics.models import Topic, TopicKeyword


class ExecuteRunTests(TestCase):
    def setUp(self):
        self.topic = Topic.objects.create(
            name="调度测试主题",
            platforms=["mock"],
            collection_interval=30,
            status="active",
        )
        TopicKeyword.objects.create(topic=self.topic, word="芒果TV", kind="core")

    def test_execute_run_success(self):
        """执行一条采集运行：mock 采集 → 入库 → 分析 → success。"""
        run = CollectionRun.objects.create(topic=self.topic, platform="mock")
        run = execute_run(run.id)
        self.assertEqual(run.status, "success")
        self.assertGreater(run.fetched_count, 0)

    def test_execute_run_canceled_when_topic_paused(self):
        self.topic.status = "paused"
        self.topic.save(update_fields=["status"])
        run = CollectionRun.objects.create(topic=self.topic, platform="mock")
        run = execute_run(run.id)
        self.assertEqual(run.status, "canceled")

    def test_enqueue_run_creates_pending(self):
        from tasks.services.dispatcher import enqueue_run

        run = enqueue_run(self.topic, "mock", trigger_type="manual")
        self.assertEqual(run.status, "pending")
        self.assertEqual(run.trigger_type, "manual")

    def test_claim_specific_run_once(self):
        """H5：同一运行只能被抢占一次，第二次抢占返回 False。"""
        from tasks.services.dispatch import claim_specific_run, release_run

        run = CollectionRun.objects.create(topic=self.topic, platform="mock")
        self.assertTrue(claim_specific_run(run.id))
        self.assertFalse(claim_specific_run(run.id))
        self.assertEqual(CollectionRun.objects.get(pk=run.id).status, "running")
        release_run(run.id)
        # 释放后状态已为 running（非 pending），不可再抢占
        self.assertFalse(claim_specific_run(run.id))
