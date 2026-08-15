"""dashboard 统计口径测试：共享帖归属 / 多值关联去重。"""
import json
from collections import Counter
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from analysis.models import AnalysisResult
from dashboard.services import query as q
from posts.models import Author, Post, PostTopicHit
from topics.models import Topic


class QueryScopingTests(TestCase):
    def setUp(self):
        self.t1 = Topic.objects.create(name="主题1", platforms=["mock"])
        self.t2 = Topic.objects.create(name="主题2", platforms=["mock"])
        self.author = Author.objects.create(platform="mock", name="作者", follower_count=10)
        self.post = Post.objects.create(
            post_id="s1", platform="mock", url="https://e.com/s1",
            title="共享帖", content="内容", like_count=100, author=self.author,
            published_at=timezone.now(),
        )
        # 同帖命中两个主题
        PostTopicHit.objects.create(post=self.post, topic=self.t1, matched_count=1)
        PostTopicHit.objects.create(post=self.post, topic=self.t2, matched_count=1)
        # AnalysisResult.post 为 OneToOne：共享帖只存一条，归属第一个分析它的主题
        AnalysisResult.objects.create(post=self.post, topic=self.t1, sentiment="negative", heat_score=50)

    def test_shared_post_counts_in_both_topics(self):
        """H9：共享帖在命中的每个主题都参与情感统计，而非只算第一个分析它的主题。"""
        d1 = q.sentiment_distribution([self.t1.id])
        d2 = q.sentiment_distribution([self.t2.id])
        self.assertEqual(d1.get("negative", 0), 1)
        self.assertEqual(d2.get("negative", 0), 1)  # 修复前 t2 统计为 0

    def test_interaction_trend_no_double_count(self):
        """H11：同帖命中多主题，互动量 Sum 只计一次。"""
        rows = q.interaction_trend([self.t1.id, self.t2.id], bucket="date")
        self.assertTrue(rows)
        self.assertEqual(rows[0]["likes"], 100)

    def test_key_authors_no_double_count(self):
        """H11：重点作者 total_likes/post_count 不受多值 join 放大。"""
        rows = q.key_authors([self.t1.id, self.t2.id])
        row = next((r for r in rows if r["id"] == self.author.id), None)
        self.assertIsNotNone(row)
        self.assertEqual(row["total_likes"], 100)
        self.assertEqual(row["post_count"], 1)


class TopKeywordsRefinedTests(TestCase):
    """看板 LLM 精选关键词：降级 / 精选 / 缓存 / 候选不足跳过 / 统计版不受影响。"""

    # 内容词均不在 analysis/data/stopwords.txt 中，保证分词后成为候选
    CONTENT = "剧情 演员 演技 台词 节奏 画面 配乐 结尾 男主 女主 配角 导演 编剧 服装 道具 特效 滤镜 剪辑 配音 字幕"

    def setUp(self):
        cache.clear()
        self.topic = Topic.objects.create(name="主题K", platforms=["mock"])
        self.author = Author.objects.create(platform="mock", name="作者", follower_count=10)
        self.post = Post.objects.create(
            post_id="k1", platform="mock", url="https://e.com/k1",
            title="关键词帖", content=self.CONTENT, like_count=1, author=self.author,
            published_at=timezone.now(),
        )
        PostTopicHit.objects.create(post=self.post, topic=self.topic, matched_count=1)

    def test_llm_unavailable_falls_back_to_stats(self):
        """LLM 未配置/失败（chat 返回 None）时降级为统计结果。"""
        with mock.patch("analysis.services.llm.chat", return_value=None) as m:
            refined = q.top_keywords_refined([self.topic.id], limit=5)
        self.assertTrue(m.called)
        self.assertEqual(refined, q.top_keywords([self.topic.id], limit=5))

    def test_llm_selection_used_with_count_mapping(self):
        """LLM 返回纯关键词数组时采用其结果，count 从统计映射（合并词累加碎片次数）。"""
        payload = json.dumps(["演员演技", "剧情"], ensure_ascii=False)
        with mock.patch("analysis.services.llm.chat", return_value=payload):
            refined = q.top_keywords_refined([self.topic.id], limit=5)
        # 「演员」「演技」各 1 次 → 合并词「演员演技」累加为 2；「剧情」精确命中为 1
        self.assertEqual(refined, [
            {"keyword": "演员演技", "count": 2},
            {"keyword": "剧情", "count": 1},
        ])

    def test_cached_result_skips_second_llm_call(self):
        """同参数二次请求命中缓存，不重复调用 LLM。"""
        payload = json.dumps(["剧情"], ensure_ascii=False)
        with mock.patch("analysis.services.llm.chat", return_value=payload) as m:
            first = q.top_keywords_refined([self.topic.id], limit=5)
            second = q.top_keywords_refined([self.topic.id], limit=5)
        self.assertEqual(m.call_count, 1)
        self.assertEqual(first, second)

    def test_cache_key_ignores_minute_second_drift(self):
        """同一小时内的 start/end 秒级漂移共享缓存（前端刷新页面不重复调 LLM）。"""
        payload = json.dumps(["剧情"], ensure_ascii=False)
        now = timezone.now()
        with mock.patch("analysis.services.llm.chat", return_value=payload) as m:
            first = q.top_keywords_refined(
                [self.topic.id],
                start=(now - timedelta(hours=2)).replace(minute=5, second=10).isoformat(),
                end=(now + timedelta(hours=1)).replace(minute=40, second=20).isoformat(),
                limit=5,
            )
            second = q.top_keywords_refined(
                [self.topic.id],
                start=(now - timedelta(hours=2)).replace(minute=5, second=55).isoformat(),
                end=(now + timedelta(hours=1)).replace(minute=40, second=59).isoformat(),
                limit=5,
            )
        self.assertEqual(m.call_count, 1)
        self.assertEqual(first, second)

    def test_cache_key_separates_hour_buckets(self):
        """跨小时的时间窗口属于不同缓存项，会重新调用 LLM。"""
        payload = json.dumps(["剧情"], ensure_ascii=False)
        now = timezone.now()
        with mock.patch("analysis.services.llm.chat", return_value=payload) as m:
            q.top_keywords_refined(
                [self.topic.id],
                start=(now - timedelta(hours=2)).isoformat(),
                end=(now + timedelta(hours=1)).isoformat(),
                limit=5,
            )
            q.top_keywords_refined(
                [self.topic.id],
                start=(now - timedelta(hours=3)).isoformat(),
                end=(now + timedelta(hours=1)).isoformat(),
                limit=5,
            )
        self.assertEqual(m.call_count, 2)

    def test_few_candidates_skips_llm(self):
        """候选词数不多于 limit 时直接返回统计结果，不触发 LLM。"""
        with mock.patch("analysis.services.llm.chat") as m:
            refined = q.top_keywords_refined([self.topic.id], limit=100)
        self.assertFalse(m.called)
        self.assertEqual(refined, q.top_keywords([self.topic.id], limit=100))

    def test_statistical_version_unchanged(self):
        """统计版 top_keywords（报告链路）仍按词频排序。"""
        rows = q.top_keywords([self.topic.id], limit=30)
        self.assertTrue(rows)
        counts = {r["keyword"]: r["count"] for r in rows}
        self.assertIn("剧情", counts)
        self.assertIn("演员", counts)
        self.assertEqual(counts["剧情"], counts["演员"])  # 同频词均出现
        self.assertEqual(rows, sorted(rows, key=lambda r: -r["count"]))


class ParseLLMKeywordsTests(TestCase):
    """_parse_llm_keywords：纯数组/对象包装/旧对象条目/垃圾输出。"""

    def test_plain_string_array(self):
        text = '```json\n["迪丽热巴", "演技"]\n```'
        self.assertEqual(q._parse_llm_keywords(text), ["迪丽热巴", "演技"])

    def test_object_wrapped_strings(self):
        text = '{"keywords": ["迪丽热巴", "演技"]}'
        self.assertEqual(q._parse_llm_keywords(text), ["迪丽热巴", "演技"])

    def test_legacy_object_items(self):
        text = '[{"keyword": "a", "count": 3}, "b", {"keyword": "", "count": 1}]'
        self.assertEqual(q._parse_llm_keywords(text), ["a", "b"])

    def test_garbage_returns_empty(self):
        self.assertEqual(q._parse_llm_keywords("抱歉我无法分析"), [])
        self.assertEqual(q._parse_llm_keywords(""), [])


class MergeRefinedCountsTests(TestCase):
    """_merge_refined_counts：精确命中 / 碎片累加 / 新词中位数兜底。"""

    def test_exact_match_and_fragment_sum(self):
        counter = Counter({"迪丽": 10, "热巴": 10, "演技": 5})
        self.assertEqual(q._merge_refined_counts(["迪丽热巴", "演技"], counter), [
            {"keyword": "迪丽热巴", "count": 20},
            {"keyword": "演技", "count": 5},
        ])

    def test_unknown_word_gets_median(self):
        counter = Counter({"a": 9, "b": 3, "c": 5})
        # 次数中位数为 5
        self.assertEqual(q._merge_refined_counts(["全新词"], counter), [{"keyword": "全新词", "count": 5}])

    def test_duplicates_and_blanks_dropped(self):
        counter = Counter({"a": 2})
        self.assertEqual(q._merge_refined_counts(["a", "a", "", "  "], counter), [{"keyword": "a", "count": 2}])


class KeywordSnapshotTests(TestCase):
    """预计算快照：读库秒回 / 快照缺失在线计算并回写自愈 / 定时刷新只算有新帖的。"""

    CONTENT = "剧情 演员 演技 台词 节奏 画面 配乐 结尾 男主 女主 配角 导演 编剧 服装 道具 特效 滤镜 剪辑 配音 字幕"

    def setUp(self):
        cache.clear()
        self.topic = Topic.objects.create(name="快照主题", platforms=["mock"])
        self.author = Author.objects.create(platform="mock", name="作者", follower_count=10)
        self.post = Post.objects.create(
            post_id="ks1", platform="mock", url="https://e.com/ks1",
            title="快照帖", content=self.CONTENT, like_count=1, author=self.author,
            published_at=timezone.now(),
        )
        PostTopicHit.objects.create(post=self.post, topic=self.topic, matched_count=1)

    def test_window_reads_snapshot_without_llm(self):
        """标准窗口命中快照：直接读库返回，不触发 LLM。"""
        from dashboard.models import TopicKeywordsSnapshot

        TopicKeywordsSnapshot.objects.create(
            topic=self.topic, window="7d", keywords=[{"keyword": "剧情", "count": 9}],
        )
        with mock.patch("analysis.services.llm.chat") as m:
            rows = q.top_keywords_refined([self.topic.id], window="7d")
        self.assertFalse(m.called)
        self.assertEqual(rows, [{"keyword": "剧情", "count": 9}])

    def test_window_miss_falls_back_and_self_heals(self):
        """快照缺失：在线计算并回写快照，下次直接读库。"""
        from dashboard.models import TopicKeywordsSnapshot

        payload = json.dumps(["剧情"], ensure_ascii=False)
        with mock.patch("analysis.services.llm.chat", return_value=payload) as m:
            rows = q.top_keywords_refined([self.topic.id], window="7d", limit=5)
        self.assertTrue(m.called)
        self.assertEqual(rows, [{"keyword": "剧情", "count": 1}])
        snap = TopicKeywordsSnapshot.objects.get(topic=self.topic, window="7d")
        self.assertEqual(snap.keywords, rows)

    def test_refresh_snapshot_for_active_topics(self):
        """定时刷新：为活跃主题和「全部主题」写入快照。"""
        from dashboard.models import TopicKeywordsSnapshot
        from dashboard.services import snapshots

        payload = json.dumps(["剧情"], ensure_ascii=False)
        with mock.patch("analysis.services.llm.chat", return_value=payload):
            refreshed = snapshots.refresh_keyword_snapshots(limit=5)
        self.assertEqual(refreshed, 2)
        self.assertTrue(TopicKeywordsSnapshot.objects.filter(topic=self.topic, window="7d").exists())
        self.assertTrue(TopicKeywordsSnapshot.objects.filter(topic__isnull=True, window="7d").exists())

    def test_refresh_skips_unchanged_topic(self):
        """快照之后没有新帖子的目标不重算，不消耗 LLM 调用。"""
        from dashboard.models import TopicKeywordsSnapshot
        from dashboard.services import snapshots

        TopicKeywordsSnapshot.objects.create(
            topic=self.topic, window="7d", keywords=[{"keyword": "剧情", "count": 1}],
        )
        TopicKeywordsSnapshot.objects.create(
            topic=None, window="7d", keywords=[{"keyword": "剧情", "count": 1}],
        )
        with mock.patch("analysis.services.llm.chat") as m:
            refreshed = snapshots.refresh_keyword_snapshots()
        self.assertFalse(m.called)
        self.assertEqual(refreshed, 0)

    def test_empty_snapshot_treated_as_missing(self):
        """空快照不阻塞：视为缺失，走在线计算（新建主题帖子进来后立即可见）。"""
        from dashboard.models import TopicKeywordsSnapshot

        TopicKeywordsSnapshot.objects.create(topic=self.topic, window="7d", keywords=[])
        payload = json.dumps(["剧情"], ensure_ascii=False)
        with mock.patch("analysis.services.llm.chat", return_value=payload) as m:
            rows = q.top_keywords_refined([self.topic.id], window="7d", limit=5)
        self.assertTrue(m.called)
        self.assertEqual(rows, [{"keyword": "剧情", "count": 1}])

    def test_empty_result_not_stored(self):
        """无帖子算出的空结果不写入快照，帖子进来后下次请求直接在线计算。"""
        from dashboard.models import TopicKeywordsSnapshot

        empty_topic = Topic.objects.create(name="空主题", platforms=["mock"])
        with mock.patch("analysis.services.llm.chat") as m:
            rows = q.top_keywords_refined([empty_topic.id], window="7d")
        self.assertFalse(m.called)
        self.assertEqual(rows, [])
        self.assertFalse(
            TopicKeywordsSnapshot.objects.filter(topic=empty_topic, window="7d").exists()
        )


class ParseFiltersDefaultWindowTests(TestCase):
    """看板去掉时间筛选后：未传 start/end 默认取最近 30 天。"""

    def test_default_30_day_window(self):
        from datetime import datetime

        from django.test import RequestFactory
        from django.utils import timezone
        from rest_framework.request import Request

        from dashboard.services.query import _parse_filters

        req = Request(RequestFactory().get("/dashboard/overview/"))
        _, _, start, end = _parse_filters(req)
        s = timezone.make_aware(datetime.fromisoformat(start))
        e = timezone.make_aware(datetime.fromisoformat(end))
        now = timezone.now()
        self.assertAlmostEqual((now - s).total_seconds(), 30 * 86400, delta=120)
        self.assertAlmostEqual((e - now).total_seconds(), 0, delta=120)

    def test_explicit_window_preserved(self):
        """显式传入 start/end 时保持原值（报告/自定义查询不受默认窗口影响）。"""
        from django.test import RequestFactory
        from rest_framework.request import Request

        from dashboard.services.query import _parse_filters

        req = Request(RequestFactory().get(
            "/dashboard/overview/?start=2026-08-01T00:00:00&end=2026-08-02T00:00:00"
        ))
        _, _, start, end = _parse_filters(req)
        self.assertEqual(start, "2026-08-01T00:00:00")
        self.assertEqual(end, "2026-08-02T00:00:00")
