"""分析看板聚合 API。"""
from rest_framework.decorators import api_view
from rest_framework.response import Response

from dashboard.services import query as q


def _filters(request):
    return q._parse_filters(request)


@api_view(["GET"])
def overview(request):
    topic_ids, platform, start, end = _filters(request)
    return Response(q.overview(topic_ids, platform, start, end))


@api_view(["GET"])
def trend(request):
    topic_ids, platform, start, end = _filters(request)
    bucket = request.query_params.get("bucket", "hour")
    return Response(q.trend(topic_ids, platform, start, end, bucket))


@api_view(["GET"])
def platform_distribution(request):
    topic_ids, platform, start, end = _filters(request)
    return Response(q.platform_distribution(topic_ids, start, end))


@api_view(["GET"])
def sentiment_distribution(request):
    topic_ids, platform, start, end = _filters(request)
    return Response(q.sentiment_distribution(topic_ids, platform, start, end))


@api_view(["GET"])
def interaction_trend(request):
    topic_ids, platform, start, end = _filters(request)
    bucket = request.query_params.get("bucket", "hour")
    return Response(q.interaction_trend(topic_ids, platform, start, end, bucket))


@api_view(["GET"])
def hot_posts(request):
    topic_ids, platform, start, end = _filters(request)
    limit = int(request.query_params.get("limit", 10))
    return Response(q.hot_posts(topic_ids, platform, start, end, limit))


@api_view(["GET"])
def negative_posts(request):
    topic_ids, platform, start, end = _filters(request)
    limit = int(request.query_params.get("limit", 10))
    return Response(q.negative_posts(topic_ids, platform, start, end, limit))


@api_view(["GET"])
def top_keywords(request):
    topic_ids, _, start, end = _filters(request)
    limit = int(request.query_params.get("limit", 30))
    window = request.query_params.get("window")
    if window:
        # 窗口模式：时间范围由窗口本身推导（7d 预计算快照），不走 30 天默认窗口
        start = end = None
    # window（如 7d）命中预计算快照直接读库秒回；快照缺失自动在线计算并回写
    return Response(q.top_keywords_refined(topic_ids, start, end, limit, window=window))


@api_view(["GET"])
def heat_trend(request):
    topic_ids, platform, start, end = _filters(request)
    bucket = request.query_params.get("bucket", "hour")
    return Response(q.heat_trend(topic_ids, platform, start, end, bucket))


@api_view(["GET"])
def key_authors(request):
    topic_ids, platform, start, end = _filters(request)
    limit = int(request.query_params.get("limit", 10))
    return Response(q.key_authors(topic_ids, platform, start, end, limit))


@api_view(["GET"])
def topic_compare(request):
    topic_ids, _, start, end = _filters(request)
    return Response(q.topic_compare(topic_ids, start, end))
