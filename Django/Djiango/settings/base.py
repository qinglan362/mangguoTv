"""
Django 基础设置（Djiango 舆情收集平台）。

共享配置：所有环境（dev/prod）均继承此文件。
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# 开发环境从 Django/.env 读取本地配置（采集器 Cookie、密钥等）。
# 已存在的系统环境变量优先；.env 不存在或未安装 python-dotenv 时静默跳过。
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

# SECURITY WARNING: keep the secret key used in production secret!
# 生产环境必须通过 DJANGO_SECRET_KEY 提供；下方内置值仅作为开发兜底（prod.py 会强制校验）。
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-t)@&m2!lc9*mp7fs!$3tuoi3%ldpuh4a51e9u)5^wtj45=__+)",
)

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # 第三方
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    # 业务 app
    "topics",
    "collectors",
    "tasks",
    "posts",
    "analysis",
    "alerts",
    "reports",
    "dashboard",
    "accounts",
    # 采集器插件（小红书/微博真实采集，独立应用，删除目录并移除此行即可回滚）
    "collectors.plugins",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "Djiango.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "Djiango.wsgi.application"

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# 默认主键类型
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ============ Django REST Framework ============
REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "Djiango.pagination.StandardPageNumberPagination",
    "PAGE_SIZE": 20,
    # 前端可 ?page_size=N 覆盖每页条数（上限 200），见 Djiango/pagination.py（H14）
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    # 内部系统：默认要求登录；管理员高权限接口通过自定义 IsAdmin 控制。
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    # 登录接口限流（防爆破），其余接口走默认不受限。
    "DEFAULT_THROTTLE_RATES": {
        "login": "20/min",
    },
}

# ============ SimpleJWT ============
from datetime import timedelta  # noqa: E402

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=8),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "AUTH_HEADER_TYPES": ("Bearer",),
    # 刷新时轮换 refresh token 并黑名单旧 token：泄露的 refresh token 被使用一次即失效
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

# ============ MediaCrawler 集成（外部爬虫项目，可随时更换/删除） ============
# 前端触发后由本后端执行 uv run main.py，抓取结果落在 {MEDIACRAWLER_DIR}/data/ 下再被导入平台
MEDIACRAWLER_DIR = BASE_DIR.parent / 'Media'

# ============ 采集器配置 ============
# 内置采集器开关：mock 为演示数据源；
# 小红书/微博的真实采集改由 MediaCrawler 插件承担（主题页「立即采集」自动路由），
# 内置的 xhs/weibo 采集器保持禁用，避免两套真实采集路径互相干扰。
COLLECTORS_ENABLED = {
    "mock": True,
    "xiaohongshu": False,
    "weibo": False,
}

MOCK_COLLECTOR = {
    "per_run": [30, 200],           # 每次生成条数范围
    "sentiment_weights": {"positive": 0.62, "neutral": 0.24, "negative": 0.14},
    "negative_burst_hour": None,    # 整点后注入负面激增的小时数（None 关闭）
    "seed_per_topic": True,
    "hot_ratio": 0.04,              # 高热帖子占比（互动量放大）
    "key_author_names": ["芒果TV官方", "娱乐观察员", "瓜田情报站"],
    "exclude_author_names": ["官方运营号", "芒果TV会员助手"],
}

# ============ 内容识别 LLM 配置（全站统一：正负面分析/相关性/观点实体/报告摘要等） ============
# API Key 统一放在 Django/.env 的 DEEPSEEK_API_KEY（系统环境变量同名设置亦可）；
# 模型名 / API 地址可经 .env 的 LLM_MODEL / LLM_BASE_URL 覆盖。
ANALYSIS_LLM = {
    "provider": "deepseek",                       # deepseek（默认）/ anthropic（兼容保留）
    "model": os.environ.get("LLM_MODEL", "deepseek-v4-pro"),
    "api_key_env": "DEEPSEEK_API_KEY",
    "base_url": os.environ.get("LLM_BASE_URL", "https://api.deepseek.com"),
    "batch_size": 16,                 # 每请求处理的帖子数
    "concurrency": 3,                 # 并行 worker 数
    "max_tokens": 8192,
    "daily_token_budget": 40_000_000, # 单日 token 预算，超限降级规则层
    "timeout": 180,                   # LLM 接口超时（秒）：推理模型思考阶段耗时可达 2 分钟，过小会中断请求
    "retries": 3,
}

# ============ 调度器配置 ============
SCHEDULER = {
    "worker_concurrency": 4,        # 并发执行采集运行数
    "dispatch_poll_seconds": 5,     # 派发线程轮询间隔
    "max_retries": 3,               # 失败最大重试次数
    "retry_backoff_minutes": [1, 5, 15],
    "auto_start": False,            # 是否在 ready() 内联启动（开发用 DJANGO_AUTO_START_SCHEDULER=1）
}

# ============ 邮件通知 ============
EMAIL_NOTIFY_ENABLED = False
DEFAULT_FROM_EMAIL = "noreply@example.com"
EMAIL_HOST = ""
EMAIL_PORT = 465
EMAIL_USE_TLS = False
EMAIL_USE_SSL = True
EMAIL_HOST_USER = ""
EMAIL_HOST_PASSWORD = ""

# ============ 导出 ============
EXPORT_DIR = BASE_DIR / "exports"
