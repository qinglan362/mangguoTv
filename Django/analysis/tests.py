"""analysis 模块 LLM 归一化、source 标注与观点聚类测试。"""
from unittest import mock

from django.test import TestCase

from analysis.services import pipeline
from analysis.services.llm import ClaudeBackend, _normalize_posts
from posts.models import Post
from topics.models import Topic, TopicKeyword


class LLMNormalizeTests(TestCase):
    def test_normalize_accepts_model_instances(self):
        """H1 回归：Post 模型实例被归一化为 dict，避免 .get() AttributeError。"""
        norm = _normalize_posts([Post(title="标题", content="正文"), {"content": "dict文本"}])
        self.assertEqual(norm[0]["content"], "正文")
        self.assertEqual(norm[1]["content"], "dict文本")

    def test_analyze_batch_accepts_post_instances(self):
        """H1 回归：配置了 API Key 时传入 Post 实例，LLM 批处理不再崩溃。"""
        backend = ClaudeBackend()
        client = mock.MagicMock()
        client.messages.create.return_value.content[0].text = (
            '[{"post_id":1,"is_related":true,"related_score":0.9,"sentiment":"neutral",'
            '"sentiment_score":0.5,"viewpoints":["观点"],"entities":[],"keywords":["芒果TV"]}]'
        )
        with mock.patch.object(backend, "available", return_value=True), \
             mock.patch.object(backend, "_get_client", return_value=client):
            res = backend.analyze_batch(
                [Post(title="标题", content="正文内容")],
                {"topic_name": "主题", "keywords": ["芒果TV"]},
            )
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["sentiment"], "neutral")
        self.assertEqual(res[0]["viewpoints"], ["观点"])


class PipelineSourceTests(TestCase):
    def setUp(self):
        self.topic = Topic.objects.create(name="分析主题", platforms=["mock"], collection_interval=30)
        TopicKeyword.objects.create(topic=self.topic, word="芒果TV", kind="core")
        self.post = Post.objects.create(
            post_id="a1", platform="mock", url="https://e.com/a1", title="标题",
            content="芒果TV 今晚播出的新节目真好看", content_hash="hash1",
        )
        from posts.models import PostTopicHit
        PostTopicHit.objects.create(post=self.post, topic=self.topic, matched_count=1)

    def test_llm_result_marked_llm(self):
        """H2 回归：真实 LLM 结果 source=llm。"""
        with mock.patch.object(pipeline, "get_llm_backend") as mock_get:
            backend = mock.MagicMock()
            backend.analyze_batch.return_value = [{
                "is_related": True, "related_score": 0.9, "sentiment": "positive",
                "sentiment_score": 0.8, "viewpoints": ["很好看"], "entities": [], "keywords": [],
            }]
            mock_get.return_value = backend
            pipeline.run_for_topic(self.topic)
        ar = self.post.analysis
        self.assertEqual(ar.sentiment_source, "llm")

    def test_llm_fallback_keeps_rule_source(self):
        """H2 回归：LLM 返回 None 时走规则兜底，source 不得标成 llm。"""
        with mock.patch.object(pipeline, "get_llm_backend") as mock_get:
            backend = mock.MagicMock()
            backend.analyze_batch.return_value = [None]
            mock_get.return_value = backend
            pipeline.run_for_topic(self.topic)
        ar = self.post.analysis
        self.assertNotEqual(ar.sentiment_source, "llm")
