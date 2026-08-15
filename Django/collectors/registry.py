"""采集器注册表。"""
from django.conf import settings

_REGISTRY: dict = {}


def register(platform: str):
    """装饰器：注册采集器类。"""

    def decorator(cls):
        cls.platform = cls.platform or platform
        _REGISTRY[platform] = cls
        return cls

    return decorator


def get_collector(platform: str):
    """返回采集器实例（未启用返回 None）。"""
    if not settings.COLLECTORS_ENABLED.get(platform):
        return None
    cls = _REGISTRY.get(platform)
    if not cls:
        return None
    config = settings.COLLECTOR_CONFIG.get(platform, {}) if hasattr(settings, "COLLECTOR_CONFIG") else {}
    return cls(config=config)


def list_collectors() -> list[dict]:
    """列出所有已注册采集器及就绪状态。"""
    result = []
    for platform, cls in _REGISTRY.items():
        enabled = settings.COLLECTORS_ENABLED.get(platform, False)
        # 无论是否启用都实例化检查配置缺失项：未启用的真实采集器
        # （如缺 Cookie）也能在系统设置页看到「还差什么才能启用」
        collector = cls()
        result.append({
            "platform": platform,
            "display_name": cls.display_name or platform,
            "enabled": enabled,
            "issues": collector.validate() if collector else [],
        })
    return result
