"""内容识别路由。

仅注册帖子详情页「人工修正」动作；分析列表/实体/观点/聚类/摘要接口已随
前端主题详情页的「分析」标签页一并移除。
"""
from django.urls import path

from analysis.views import AnalysisResultViewSet

app_name = "analysis"

urlpatterns = [
    path(
        "<int:pk>/correct/",
        AnalysisResultViewSet.as_view({"post": "correct"}),
        name="analysis-correct",
    ),
]
