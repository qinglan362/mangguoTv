"""为 Viewpoint 增加 created_at（观点时间范围统计用）。

auto_now_add 无法为存量行填充，故在 AddField 中提供 default 迁移期回填，
preserve_default=False 使库表不保留该默认值。
"""
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("analysis", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="viewpoint",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
                verbose_name="创建时间",
            ),
            preserve_default=False,
        ),
    ]
