"""开发环境设置。"""
import os

from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# 开发期放开跨域（前端 vite dev server 走 /api proxy 时本身无跨域，此处兜底）
CORS_ALLOW_ALL_ORIGINS = True

# 开发期默认内联启动调度器：直接 python manage.py runserver 即可定时采集，
# 无需额外跑 manage.py runscheduler（tasks/apps.py 只在 reloader 子进程内启动，避免双启动）。
# 设 DJANGO_AUTO_START_SCHEDULER=0 可关闭（改由单独进程 runscheduler 承担）。
SCHEDULER["auto_start"] = os.environ.get("DJANGO_AUTO_START_SCHEDULER", "1") != "0"

# ===== 预警邮件通知（与 prod 同款 .env 开关；base 默认关闭，这里不填 DJANGO_EMAIL_ENABLED 就维持关闭）=====
# 在 Django/.env 配置后开启，例如 QQ 邮箱：
#   DJANGO_EMAIL_ENABLED=1
#   DJANGO_EMAIL_USER=xxx@qq.com
#   DJANGO_EMAIL_PASSWORD=<邮箱设置里生成的 SMTP 授权码，不是登录密码>
# 修改 .env 后需重启 runserver 才生效。
EMAIL_NOTIFY_ENABLED = os.environ.get("DJANGO_EMAIL_ENABLED") == "1"
if EMAIL_NOTIFY_ENABLED:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ.get("DJANGO_EMAIL_HOST", "smtp.qq.com")
    EMAIL_PORT = int(os.environ.get("DJANGO_EMAIL_PORT", "465"))
    EMAIL_USE_SSL = True
    EMAIL_HOST_USER = os.environ.get("DJANGO_EMAIL_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("DJANGO_EMAIL_PASSWORD", "")
    # QQ 等主流 SMTP 要求发件人 = 授权账号，这里强制对齐
    DEFAULT_FROM_EMAIL = EMAIL_HOST_USER
