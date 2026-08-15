"""posts 模块核心逻辑测试：去重分组 / 入库 / 互动更新。"""
from django.test import TestCase
from django.utils import timezone

from collectors.schemas import AuthorInfo, RawPost
from posts.models import Post
from posts.services import ingest
from posts.services.dedupe import assign_dedup_groups
from topics.models import Topic, TopicKeyword


def make_raw(post_id, title="", content="", platform="mock", **kw):
    return RawPost(
        post_id=post_id,
        platform=platform,
        url="https://example.com/%s" % post_id,
        title=title,
        content=content,
        author=AuthorInfo(platform=platform, author_id="u1", name="作者A"),
        published_at=timezone.now(),
        collected_at=timezone.now(),
        like_count=kw.get("like_count", 0),
        comment_count=kw.get("comment_count", 0),
        share_count=kw.get("share_count", 0),
        favorite_count=kw.get("favorite_count", 0),
    )


class DedupeGroupTests(TestCase):
    def test_gid_unique_across_batches(self):
        """C3 回归：不同批次的相似分组 id 不得复用，否则跨批次误判重复丢数据。"""
        batch_a = [
            {"content": "这是第一个人工智能新闻内容呀", "hash": "a1"},
            {"content": "这是第一个人工智能新闻内容呀的搬运版", "hash": "a2"},
        ]
        batch_b = [{"content": "这是一个完全不同的天气报道内容哦", "hash": "b1"}]
        gids_a = {v for v in assign_dedup_groups(batch_a).values() if v}
        gids_b = {v for v in assign_dedup_groups(batch_b).values() if v}
        self.assertTrue(gids_a)
        self.assertTrue(gids_b)
        self.assertTrue(gids_a.isdisjoint(gids_b))

    def test_similar_merged_within_batch(self):
        batch = [
            {"content": "芒果TV新综艺上线引发网友热议讨论热烈期待满满", "hash": "h1"},
            {"content": "芒果TV新综艺上线引发网友热议讨论热烈期待满满呀", "hash": "h2"},
        ]
        m = assign_dedup_groups(batch)
        self.assertEqual(m["h1"], m["h2"])


class IngestTests(TestCase):
    def setUp(self):
        self.topic = Topic.objects.create(name="测试主题", platforms=["mock"], collection_interval=30)
        TopicKeyword.objects.create(topic=self.topic, word="芒果TV", kind="core")

    def test_basic_ingest(self):
        result = ingest.ingest_batch(self.topic, [make_raw("p1", content="芒果TV 内容一")])
        self.assertEqual(result.new_count, 1)
        self.assertEqual(Post.objects.count(), 1)
        self.assertEqual(result.fetched_count, 1)

    def test_none_interactions_not_crash(self):
        """M8 回归：采集器返回 None 互动值不得崩溃整批。"""
        raw = make_raw("p2", content="芒果TV 内容二", like_count=None, comment_count=None)
        result = ingest.ingest_batch(self.topic, [raw])
        self.assertEqual(result.new_count, 1)
        p = Post.objects.get(post_id="p2")
        self.assertEqual(p.like_count, 0)

    def test_duplicate_pid_merged(self):
        ingest.ingest_batch(self.topic, [make_raw("p5", content="芒果TV 内容五")])
        result = ingest.ingest_batch(self.topic, [make_raw("p5", content="芒果TV 内容五")])
        self.assertEqual(Post.objects.count(), 1)
        self.assertEqual(result.duplicate_count, 1)

    def test_excluded_author_uses_run_platform(self):
        """H7 回归：排除用户按本次采集平台过滤，而非主题第一个平台。"""
        from tasks.models import CollectionRun
        from topics.models import TopicExclusionUser

        topic = Topic.objects.create(name="多平台主题", platforms=["xiaohongshu", "weibo"], collection_interval=30)
        TopicKeyword.objects.create(topic=topic, word="芒果TV", kind="core")
        TopicExclusionUser.objects.create(topic=topic, platform="xiaohongshu", author_name="作者A")

        # 本次采集微博 → 小红书的排除用户不生效
        run_weibo = CollectionRun.objects.create(topic=topic, platform="weibo")
        result = ingest.ingest_batch(topic, [make_raw("p6", content="芒果TV 内容六", platform="weibo")], run=run_weibo)
        self.assertEqual(result.new_count, 1)

        # 本次采集小红书 → 小红书排除用户生效，帖子被过滤
        run_xhs = CollectionRun.objects.create(topic=topic, platform="xiaohongshu")
        result2 = ingest.ingest_batch(topic, [make_raw("p7", content="芒果TV 内容七", platform="xiaohongshu")], run=run_xhs)
        self.assertEqual(result2.new_count, 0)
        self.assertEqual(result2.filtered_count, 1)

    def test_exclude_keyword_filters(self):
        TopicKeyword.objects.create(topic=self.topic, word="广告", kind="exclude")
        result = ingest.ingest_batch(self.topic, [make_raw("p8", content="芒果TV 广告推广信息")])
        self.assertEqual(result.new_count, 0)
        self.assertEqual(result.filtered_count, 1)
