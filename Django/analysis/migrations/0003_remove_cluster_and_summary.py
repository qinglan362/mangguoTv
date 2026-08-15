"""随前端移除主题详情「分析」页：删除观点聚类与阶段摘要模型。

- ViewpointCluster / ThemeSummary：前端不再展示聚类与摘要页面；
- Viewpoint.cluster 字段一并移除（观点本身仍保留，供看板热门观点展示）。
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("analysis", "0002_viewpoint_created_at"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="viewpoint",
            name="cluster",
        ),
        migrations.DeleteModel(
            name="ViewpointCluster",
        ),
        migrations.DeleteModel(
            name="ThemeSummary",
        ),
    ]
