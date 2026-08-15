from django.apps import AppConfig


class CollectorsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "collectors"

    def ready(self):
        # 注册内置采集器（mock 始终注册；真实爬虫接入后自动注册）
        from . import mock_collector  # noqa: F401
        try:
            from . import real_collectors  # noqa: F401
        except ImportError:
            pass
