# 采集器接入指南

平台采用**可插拔采集器**架构：调度、清洗、去重、分析、预警等模块全部依赖 `BaseCollector` 抽象接口，
接入真实爬虫（小红书 / 微博）无需改动任何下游代码。

## 一、核心接口

```python
# collectors/base.py
class BaseCollector(ABC):
    platform = ""        # 平台标识：xiaohongshu / weibo / mock
    display_name = ""    # 展示名

    def __init__(self, config: dict | None = None): ...

    @abstractmethod
    def search(self, query: CollectQuery) -> CollectResult:
        """按主题关键词执行一次采集，返回标准化帖子。"""

    @abstractmethod
    def fetch_interactions(self, post_ids: list[str]) -> dict:
        """批量刷新互动数据，返回 {post_id: PostStats}。"""

    def validate(self) -> list[str]:
        """返回未就绪的配置项（如缺 cookie/API key），用于前端展示采集器状态。"""
```

## 二、数据契约（与平台约定）

`search()` 必须返回 `CollectResult(posts=[RawPost, ...], next_cursor=...)`。
`RawPost` 是唯一数据入口，字段约束如下：

| 字段 | 必填 | 说明 |
|------|------|------|
| `post_id` | ✅ | 平台侧帖子 ID，跨关键词去重的关键 |
| `platform` | ✅ | 与 `self.platform` 一致 |
| `url` | ✅ | 原始链接（唯一约束） |
| `title` / `content` | 至少其一 | 参与清洗、去重、情感分析 |
| `author` | ✅ | `AuthorInfo(platform, author_id, name)` |
| `published_at` | ✅ | 帖子发布时间（用于趋势/时间窗分析） |
| `collected_at` | ✅ | 采集时间 |
| `like/comment/share/favorite_count` | ✅ | 互动数据，供热度计算与快照 |
| `extra` | 可选 | 扩展字段，如 `{"is_key_author": true}` |

> 清洗层会自动过滤：广告文本（`is_ad`）、垃圾文本、主题排除词、排除作者。
> 平台侧完成关键词命中后，系统自动建立 `PostTopicHit` / `PostKeywordHit` 关联。

## 三、实现步骤

1. **创建采集器模块**：在 `collectors/` 下新建 `xiaohongshu.py` / `weibo.py`。

   ```python
   # collectors/xiaohongshu.py
   from .base import BaseCollector
   from .schemas import CollectQuery, CollectResult, RawPost, AuthorInfo, PostStats

   class XiaoHongShuCollector(BaseCollector):
       platform = "xiaohongshu"
       display_name = "小红书"

       def __init__(self, config=None):
           super().__init__(config)
           # 读取 settings.XIAOHONGSHU_COLLECTOR 的 cookie / 签名参数等

       def search(self, query: CollectQuery) -> CollectResult:
           # 1. 用 query.keywords 拼搜索请求（公开搜索页 / 自有爬虫）
           # 2. 解析出 RawPost 列表（遵守下文的限流与合规建议）
           # 3. 翻页游标写入 next_cursor
           raise NotImplementedError

       def fetch_interactions(self, post_ids: list[str]) -> dict:
           # 批量查询互动数据，返回 {post_id: PostStats}
           raise NotImplementedError

       def validate(self) -> list[str]:
           problems = []
           if not self.config.get("cookie"):
               problems.append("缺少 Cookie，采集可能被限流")
           return problems
   ```

2. **注册采集器**：在 `collectors/apps.py` 的 `ready()` 中注册。

   ```python
   from collectors.registry import register

   def ready(self):
       from collectors.mock_collector import MockCollector
       register(MockCollector)
       try:
           from collectors.xiaohongshu import XiaoHongShuCollector
           register(XiaoHongShuCollector)  # 平台开关由 settings.COLLECTORS_ENABLED 控制
       except ImportError:
           pass  # 未实现时静默跳过
   ```

3. **开启平台开关**：`settings/base.py`

   ```python
   COLLECTORS_ENABLED = {
       "mock": True,
       "xiaohongshu": True,   # ← 置 True 才会被调度
       "weibo": False,
   }
   ```

4. **配置采集参数**：建议新增 `XIAOHONGSHU_COLLECTOR = {...}` 配置块，在 `__init__` 中读取。

## 四、调度与监控

- 采集由 `tasks` 模块调度：topic 的 `platforms` 列表决定启用哪些采集器，`collection_interval` 决定频率。
- 一次运行 = 一个 `CollectionRun` 记录：`fetched/new/updated/duplicate_count` 与失败重试（1/5/15 分钟退避）自动统计。
- 平台开关关闭（`COLLECTORS_ENABLED[x] == False`）时，`get_collector(x)` 返回 `None`，运行直接失败并重试——请确保与主题配置一致。

## 五、接入自检清单

- [ ] 单测 `search()` 返回合法 `RawPost`（可用 `MockCollector` 的模板对照字段）
- [ ] 重复采集验证 `content_hash` / `post_id` 去重正确（`CollectionRun.duplicate_count`）
- [ ] `fetch_interactions` 返回快照与热度计算正确（对比 dashboard `interaction_trend`）
- [ ] 触发一次 `collect_now`，确认 `CollectionRun.status == success`
- [ ] 前端「采集器状态」面板显示 `validate()` 返回值
- [ ] 检查 IP 代理 / Cookie 过期 / 限流下的重试行为

## 六、合规与稳定性建议

- 优先使用平台公开 API / 官方开放能力；抓取行为请遵守平台服务条款与《个人信息保护法》。
- 设置合理采集频率（建议 ≥ 30 分钟/主题），避免高频请求被封。
- Cookie / token 加密存储，支持过期自动刷新与告警（可对接 `alerts` 规则）。
- 分布式部署时，可把 `search()` 做成独立服务，采集器通过 RPC 调用；接口契约不变。
