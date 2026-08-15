"""小红书 x-s 签名实现。

xhs 0.2.13 要求 XhsClient(sign=...) 传入一个可调用对象：
    sign(uri, data=None, a1="", web_session="") -> {"x-s": ..., "x-t": ...}

官方推荐方案（见 https://reajason.github.io/xhs/basic ）：
用 Playwright 打开真实浏览器执行 window._webmsxyw(url, data) 获取签名，
配合 stealth.min.js 绕过环境检测。本模块按该方案实现，并缓存浏览器实例复用。

也可配置 XHS_SIGN_SERVER 环境变量指向独立签名服务（官方 Flask/Docker 方案），
格式：POST {server}/sign  body={"uri","data","a1","web_session"} -> {"x-s","x-t"}。
"""
import atexit
import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_STEALTH_JS = Path(__file__).resolve().parent / "stealth.min.js"

# ---------- 内置 Playwright 签名（进程内单例，复用浏览器） ----------
_pw = None
_page = None
_sign_lock = threading.Lock()
_current_a1 = None
_closed = False


def _ensure_page():
    """惰性启动 Playwright 浏览器并注入 stealth.min.js（进程内复用）。"""
    global _pw, _page
    if _page is not None and not _page.is_closed():
        return _page
    from playwright.sync_api import sync_playwright

    _pw = sync_playwright().start()
    browser = _pw.chromium.launch(headless=True)
    context = browser.new_context()
    context.add_init_script(path=str(_STEALTH_JS))
    _page = context.new_page()
    _page.goto("https://www.xiaohongshu.com", wait_until="domcontentloaded", timeout=30000)
    return _page


def _shutdown():
    global _pw, _page, _closed
    if _closed:
        return
    _closed = True
    try:
        if _pw is not None:
            _pw.stop()
    except Exception:
        pass
    _pw = None
    _page = None


atexit.register(_shutdown)


def playwright_sign(uri, data=None, a1="", web_session=""):
    """内置签名：Playwright + stealth.min.js 执行 window._webmsxyw。"""
    global _current_a1
    if not _STEALTH_JS.exists():
        raise RuntimeError("缺少 stealth.min.js（采集器插件不完整）")
    with _sign_lock:  # 签名串行化：同一浏览器页面不支持并发 evaluate
        last_exc = None
        for attempt in range(3):
            try:
                page = _ensure_page()
                # a1 变化或首次才需要注入 cookie 并刷新页面（官方示例做法）
                if _current_a1 != a1:
                    page.context.add_cookies([
                        {"name": "a1", "value": a1, "domain": ".xiaohongshu.com", "path": "/"},
                    ])
                    page.reload(wait_until="domcontentloaded", timeout=30000)
                    # 等签名函数注入完成（比固定 sleep 更稳，超时也不阻断，evaluate 失败会重试）
                    try:
                        page.wait_for_function("typeof window._webmsxyw === 'function'", timeout=20000)
                    except Exception:
                        pass
                    _current_a1 = a1
                encrypt_params = page.evaluate(
                    "([url, data]) => window._webmsxyw(url, data)", [uri, data],
                )
                return {
                    "x-s": encrypt_params["X-s"],
                    "x-t": str(encrypt_params["X-t"]),
                }
            except Exception as exc:
                last_exc = exc
                logger.warning("xhs playwright sign attempt %s failed: %s", attempt + 1, exc)
                _current_a1 = None  # 下次重试重新注入 cookie 刷新
                time.sleep(1)
        raise RuntimeError(
            "小红书签名多次失败（%s）。可尝试：稍后重试 / 配置 XHS_SIGN_SERVER 独立签名服务"
            % type(last_exc).__name__ if last_exc else "未知原因",
        )


# ---------- 独立签名服务（可选，XHS_SIGN_SERVER） ----------
def make_server_signer(server_url: str):
    """返回调用官方 Flask 签名服务的 sign 函数。"""
    import requests

    base = server_url.rstrip("/")

    def sign(uri, data=None, a1="", web_session=""):
        resp = requests.post(
            base + "/sign",
            json={"uri": uri, "data": data, "a1": a1, "web_session": web_session},
            timeout=30,
        )
        resp.raise_for_status()
        signs = resp.json()
        return {"x-s": signs["x-s"], "x-t": signs["x-t"]}

    return sign


def build_signer(server_url: str = ""):
    """按配置返回签名函数：优先独立服务，否则内置 Playwright。"""
    if server_url:
        return make_server_signer(server_url)
    return playwright_sign