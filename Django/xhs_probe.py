# -*- coding: utf-8 -*-
"""小红书采集器独立连通性测试。

用法（在项目根目录执行，或用完整路径）：
    Django/.venv/Scripts/python.exe Django/test_xhs.py [关键词] [每关键词条数]

不需要打开 COLLECTORS_ENABLED 开关，直接实例化采集器发起真实请求；
会展示：配置状态 -> 原始搜索探测 -> 标准化帖子映射 -> 评论抓取。
"""
import logging
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Djiango.settings")

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")

import django

django.setup()

from collectors.plugins.xiaohongshu import XiaohongshuCollector
from collectors.schemas import CollectQuery
from collectors.plugins.models import PostComment

def _arg(index, default):
    """取命令行参数：被 manage.py test 误扫到时也能安全退出。"""
    if len(sys.argv) > index and not str(sys.argv[index]).startswith("-"):
        return sys.argv[index]
    return default


keyword = str(_arg(1, "芒果TV"))
limit = int(_arg(2, "10"))

print("=" * 60)
print("小红书采集器连通性测试  关键词=%s  每词最多=%s 条" % (keyword, limit))
print("=" * 60)

collector = XiaohongshuCollector()
issues = collector.validate()
print("")
print("[1] 配置检查: Cookie 长度=%s  %s" % (len(collector.cookie), "OK" if not issues else "缺失"))
if issues:
    for i in issues:
        print("   -", i)
    sys.exit(1)

# Cookie 必需字段自检（小红书官方要求 a1 / webId / web_session 三个字段）
missing = [f for f in ("a1", "webId", "web_session") if ("; " + f + "=") not in ("; " + collector.cookie) and not collector.cookie.startswith(f + "=")]
if missing:
    print("   Cookie 缺少关键字段: %s" % "、".join(missing))
    if "web_session" in missing:
        print("   >> web_session 是登录后才会写入的字段：请先在 www.xiaohongshu.com 登录账号，")
        print("   >> 再重新 F12 复制 Cookie（Cookie 里应能看到 web_session=...）")
        sys.exit(1)

print("")
print("[2] 原始搜索探测（xhs.get_note_by_keyword）...")
try:
    # 走采集器内置客户端（自动带上 Playwright/签名服务签名）
    client = collector._get_client()
    raw = client.get_note_by_keyword(keyword, page=1, page_size=min(limit, 20))
    items = (raw or {}).get("items") or ((raw or {}).get("data") or {}).get("items") or []
    print("   OK 接口返回 %s 条原始笔记" % len(items))
    if items:
        first = items[0]
        card = first.get("note_card") or {}
        print("   样例字段: id =", first.get("id"))
        print("             display_title =", (card.get("display_title") or "")[:60])
        print("             interact_info =", card.get("interact_info"))
except Exception as exc:
    print("   失败: %s: %s" % (type(exc).__name__, exc))
    hints = {
        "SignError": "x-s 签名错误：稍后重试，或配置 XHS_SIGN_SERVER 独立签名服务",
        "IPBlockError": "IP 被风控：换网络/稍后再试，或过一下官网人机验证",
        "NeedVerifyError": "账号需要验证：在浏览器里完成验证码后再复制新 Cookie",
        "DataFetchError": "数据请求失败：Cookie 可能过期，请重新登录复制新 Cookie",
    }
    hint = hints.get(type(exc).__name__, "")
    if hint:
        print("   提示:", hint)
    sys.exit(2)

print("")
print("[3] 采集器完整链路（标准化帖子 + 评论抓取）...")
query = CollectQuery(topic_id=0, keywords=[keyword], platform="xiaohongshu", limit=limit)
try:
    result = collector.search(query)
except Exception as exc:
    print("   失败: %s: %s" % (type(exc).__name__, exc))
    sys.exit(3)

print("   OK 标准化帖子 %s 条" % len(result.posts))
for i, p in enumerate(result.posts[:5], 1):
    text = (p.title or p.content or "")[:46]
    print("     %s. [%s] %s" % (i, p.post_id, text))
    author = p.author.name if p.author else "未知"
    print("        作者=%s 赞=%s 评=%s 转=%s 藏=%s" % (author, p.like_count, p.comment_count, p.share_count, p.favorite_count))
if result.posts:
    top = max(result.posts, key=lambda p: p.like_count)
    cnt = PostComment.objects.filter(platform="xiaohongshu", platform_post_id=top.post_id).count()
    print("")
    print("   评论抓取：互动最高帖 %s 已入库 %s 条评论（0 表示该帖暂无评论或接口未返回）" % (top.post_id, cnt))
    print("   帖子链接: %s" % top.url)

print("")
print("=" * 60)
print("测试完成：接口连通、帖子获取、评论抓取均正常" if result.posts else "测试完成：未获取到帖子，请检查上方错误提示")
print("=" * 60)