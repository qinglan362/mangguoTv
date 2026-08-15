# 采集器插件：小红书 / 微博（可整体删除回滚）

本目录是**独立插件应用**，实现 collectors.BaseCollector 接口，按主题关键词
从小红书、微博抓取帖子和评论。核心平台代码（调度/清洗/分析）未做任何修改。
## MediaCrawler 集成（真实采集，前端一键触发）

前端主题详情页的「MediaCrawler 采集」按钮（仅管理员可见）会调用后端接口，
后端在 Media 项目目录执行：

    uv run main.py --platform xhs --lt qrcode --type search --keywords <主题关键词>

- 命令由本机 MediaCrawler 自己弹出浏览器显示登录二维码，扫码后开始抓取；
- 抓取结果写入 Media/data/xhs/jsonl/（search_contents_*.jsonl / search_comments_*.jsonl）；
- 进程结束后自动增量导入：解析 JSONL → 平台清洗去重 → 内容识别(规则+LLM) → 预警 → 看板；
- 也可以点「仅导入已有数据」把 MediaCrawler 手动抓取的文件导入指定主题；
- 依赖：settings.MEDIACRAWLER_DIR（默认项目根目录下 Media），本机需安装 uv；
- 删除本插件的 mediacrawler/ 目录即可整体回滚该集成。


## 启用步骤

### 第一步：填写 Cookie（推荐放 Django/.env 文件）

复制 Django/.env.example 为 Django/.env 并填写（.env 已被 gitignore，不会提交）：

    XHS_COOKIE=小红书登录后的完整Cookie
    WEIBO_COOKIE=微博登录后的完整Cookie

也可以写成 Windows 系统环境变量（setx XHS_COOKIE "..."），
二选一即可；改完必须重启 Django 服务（runserver / runscheduler）才生效。

Cookie 获取方式：
- 小红书：浏览器登录 https://www.xiaohongshu.com ，F12 → Network → 任意请求 →
  复制请求头里的完整 Cookie（含 a1/webId/gid/web_session 等）；
- 微博：浏览器登录 https://m.weibo.cn ，F12 → Network → 任意 api 请求 →
  复制请求头里的完整 Cookie（含 SUB/SUBP 等）。

### 第二步：打开采集开关

Djiango/settings/base.py 中：

    COLLECTORS_ENABLED = {"mock": True, "xiaohongshu": True, "weibo": True}

### 其他可选环境变量

- XHS_SIGN_SERVER：可选，独立签名服务地址（官方 Flask/Docker 方案，POST {地址}/sign）；
  留空则用插件内置的 Playwright + stealth.min.js 自动签名（需 pip install playwright 且 playwright install chromium）；
- XHS_USER_AGENT：登录浏览器的 UA，风控严时填写；
- XHS_COMMENT_TOP_N / WEIBO_COMMENT_TOP_N：每次采集抓评论的帖子数（默认 5，0 关闭）。

## 行为说明

- 搜索：按主题的核心/关联关键词逐个搜索，每个关键词抓取一页（最多 20 条），
  带 0.5s 左右请求间隔以降低风控；
- 评论：每次采集对互动量最高的前 N 条帖子各抓一页热评（约 20 条/帖），
  写入本插件自己的表 PostComment（不修改核心 posts 模型）；
- 评论在帖子入库前先以 (platform, post_id) 暂存，帖子入库后由 post_save 信号回填外键；
- 未配置 Cookie 时 validate() 会报告缺失项（系统设置→采集器状态可见），
  强制采集会得到明确的错误信息而不是静默失败；
- 启用开关在 COLLECTORS_ENABLED，未启用时平台其余功能不受影响。

## 评论数据查询

- API：GET /api/crawler/comments/?post=<帖子DB id>
- 前端：帖子详情页「平台评论」卡片（有评论数据时显示）。

## 回滚方法（不成功可直接删除）

1. 删除本目录 Django/collectors/plugins/；
2. 移除 Django/Djiango/settings/base.py INSTALLED_APPS 中的 collectors.plugins；
3. 移除 Django/Djiango/api_urls.py 中的 crawler 路由一行；
4. requirements.txt 中的 xhs / requests 如无其他用途可一并移除；
5. 若已执行过 migrate，回滚迁移：python manage.py migrate plugins zero。

删除后平台完全回到只有模拟数据源的状态。

## 备注

- 两个平台均无官方公开搜索 API，接口随时可能调整/风控升级，失败时请更新 Cookie 或 UA；
- 采集频率请遵守平台规则（本平台单主题建议 >=10 分钟一次，插件内置请求间隔）；
- Cookie 属于敏感凭证，不要提交到代码库。
