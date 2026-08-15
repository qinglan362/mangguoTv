"""采集器 API 视图：注册状态查询与测试采集（仅管理员）。"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsAdmin
from collectors.registry import get_collector, list_collectors
from collectors.schemas import CollectQuery


@api_view(["GET"])
def collector_list(request):
    """列出已注册采集器及就绪状态（所有登录用户可查，用于主题配置时的平台可用性提示）。"""
    return Response(list_collectors())


@api_view(["POST"])
@permission_classes([IsAdmin])
def collector_test(request, platform):
    """手动测试一次采集，返回示例数据。"""
    collector = get_collector(platform)
    if collector is None:
        return Response({"error": "采集器 %s 未启用或未注册" % platform}, status=400)
    query = CollectQuery(
        topic_id=0,
        keywords=["芒果TV", "测试"],
        platform=platform,
        limit=5,
    )
    result = collector.search(query)
    return Response({
        "platform": platform,
        "count": len(result.posts),
        "sample": [p.to_dict() for p in result.posts[:3]],
    })
