"""内容识别 API 视图。

仅保留帖子详情页「人工修正」接口（POST /api/analysis/<pk>/correct/）。
主题级实体/观点/聚类/摘要展示页已从前端移除，对应接口与模型已删除；
实体/观点数据仍由分析流水线写入，经看板与帖子详情聚合展示。
"""
import re

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from analysis.models import AnalysisResult, ManualCorrection
from analysis.serializers import AnalysisResultSerializer


class AnalysisResultViewSet(viewsets.GenericViewSet):
    """分析结果人工修正（仅 correct 动作注册路由，前端不再需要列表/详情）。"""

    queryset = AnalysisResult.objects.select_related("post", "topic").all()
    serializer_class = AnalysisResultSerializer

    @staticmethod
    def _coerce_list(value, field_name):
        """把修正值规整为列表：支持 JSON 字符串、列表、逗号分隔文本。"""
        import json
        if isinstance(value, (list, tuple)):
            return list(value)
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        return parsed
                except (json.JSONDecodeError, ValueError):
                    pass
            return [s.strip() for s in re.split(r"[,，]", stripped) if s.strip()]
        return []

    @action(detail=True, methods=["post"])
    def correct(self, request, pk=None):
        """人工修正：写修正记录并同步 AnalysisResult。"""
        analysis = self.get_object()
        field = request.data.get("field")
        corrected_value = request.data.get("corrected_value")
        note = request.data.get("note", "")
        if field not in ("sentiment", "related", "viewpoint", "entities"):
            return Response({"error": "field 不合法"}, status=400)
        # 只拒绝「缺值」，不拒绝假值：related 修正为 False、sentiment_score 为 0 都是合法修正
        if corrected_value is None or corrected_value == "":
            return Response({"error": "corrected_value 不能为空"}, status=400)

        original = {
            "sentiment": analysis.sentiment,
            "related": analysis.is_related,
            "viewpoint": analysis.key_viewpoints,
            "entities": analysis.key_entities,
        }.get(field)

        ManualCorrection.objects.create(
            post=analysis.post,
            analysis=analysis,
            field=field,
            original_value=str(original),
            corrected_value=str(corrected_value),
            corrected_by=request.user if request.user.is_authenticated else None,
            note=note,
        )

        # 同步主表
        updates = {"sentiment_source": "manual"}
        if field == "sentiment":
            updates["sentiment"] = corrected_value
        elif field == "related":
            updates["is_related"] = str(corrected_value).lower() in ("1", "true", "yes", "是")
        elif field == "viewpoint":
            updates["key_viewpoints"] = self._coerce_list(corrected_value, "key_viewpoints")
        elif field == "entities":
            updates["key_entities"] = self._coerce_list(corrected_value, "key_entities")
        AnalysisResult.objects.filter(pk=analysis.pk).update(**updates)

        return Response(AnalysisResultSerializer(AnalysisResult.objects.get(pk=analysis.pk)).data)
