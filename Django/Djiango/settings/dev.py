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
