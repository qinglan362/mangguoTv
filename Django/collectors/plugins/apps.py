"""采集器插件应用配置（小红书 / 微博真实平台采集）。

本目录是独立插件，可整体删除回滚，不修改核心采集/调度代码：
- 采集器实现 collectors.BaseCollector 接口并注册到 registry；
- 评论数据落本应用自有表 PostComment，不修改 posts 等核心模型；
- 回滚方式：删除 collectors/plugins 整个目录，并移除
  1) settings/base.py INSTALLED_APPS 中的 "collectors.plugins"
  2) Djiango/api_urls.py 中的 crawler 路由
  3) requirements.txt 中的 xhs / requests（如不再需要）
"""
from django.apps import AppConfig


class CollectorsPluginsConfig(AppConfig):
    name = "collectors.plugins"
    verbose_name = "采集器插件（小红书/微博）"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # 注册真实平台采集器。依赖包缺失（未安装 xhs/requests）时静默跳过，
        # 保证删除本目录或依赖未安装都不影响平台启动。
        try:
            from . import xiaohongshu  # noqa: F401
        except ImportError:
            pass
        try:
            from . import weibo  # noqa: F401
        except ImportError:
            pass
        from . import signals  # noqa: F401
