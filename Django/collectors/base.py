"""采集器抽象基类。

真实爬虫接入方式：
1. 继承 BaseCollector，实现 search / fetch_interactions（可选 validate）；
2. 在 collectors 应用下创建模块，注册 platform；
3. 将 settings.COLLECTORS_ENABLED[platform] 置 True 并配置对应采集参数。
其余模块（调度/清洗/分析）无需任何改动。
"""
from abc import ABC, abstractmethod

from .schemas import CollectQuery, CollectResult, PostStats


class BaseCollector(ABC):
    platform = ""        # 平台标识：xiaohongshu / weibo / mock
    display_name = ""    # 展示名

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    @abstractmethod
    def search(self, query: CollectQuery) -> CollectResult:
        """按主题关键词执行一次采集，返回标准化帖子。"""

    @abstractmethod
    def fetch_interactions(self, post_ids: list[str]) -> dict:
        """批量刷新互动数据，返回 {post_id: PostStats}。"""

    def validate(self) -> list[str]:
        """返回未就绪的配置项（如缺 cookie/API key），用于前端展示采集器状态。"""
        return []
