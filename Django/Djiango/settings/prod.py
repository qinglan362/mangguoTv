"""生产环境设置。"""
import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403

DEBUG = False

# 生产禁止使用 base.py 的开发兜底密钥：未显式配置 DJANGO_SECRET_KEY 直接启动失败。
if not os.environ.get("DJANGO_SECRET_KEY"):
    raise ImproperlyConfigured("生产环境必须设置环境变量 DJANGO_SECRET_KEY，禁止使用内置开发密钥")

# 注意：空字符串 split 结果为 [""]（truthy），因此先判空再回退，避免 ALLOWED_HOSTS=[""] 导致全站 400。
_hosts = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]
ALLOWED_HOSTS = _hosts or ["localhost"]

# 通过 DJANGO_DB_ENGINE 切换数据库：mysql / postgresql / sqlite（默认 sqlite）
_engine = os.environ.get("DJANGO_DB_ENGINE", "sqlite")
if _engine == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.environ.get("DJANGO_DB_NAME", "sentiment"),
            "USER": os.environ.get("DJANGO_DB_USER", "root"),
            "PASSWORD": os.environ.get("DJANGO_DB_PASSWORD", ""),
            "HOST": os.environ.get("DJANGO_DB_HOST", "127.0.0.1"),
            "PORT": os.environ.get("DJANGO_DB_PORT", "3306"),
            "CONN_MAX_AGE": 60,
        }
    }
elif _engine == "postgresql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DJANGO_DB_NAME", "sentiment"),
            "USER": os.environ.get("DJANGO_DB_USER", "postgres"),
            "PASSWORD": os.environ.get("DJANGO_DB_PASSWORD", ""),
            "HOST": os.environ.get("DJANGO_DB_HOST", "127.0.0.1"),
            "PORT": os.environ.get("DJANGO_DB_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.environ.get("DJANGO_DB_NAME", str(BASE_DIR / "db.sqlite3")),
        }
    }

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = os.environ.get("DJANGO_CORS_ORIGINS", "").split(",") or []

EMAIL_NOTIFY_ENABLED = os.environ.get("DJANGO_EMAIL_ENABLED") == "1"
if EMAIL_NOTIFY_ENABLED:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ.get("DJANGO_EMAIL_HOST", "smtp.example.com")
    EMAIL_PORT = int(os.environ.get("DJANGO_EMAIL_PORT", "465"))
    EMAIL_USE_SSL = True
    EMAIL_HOST_USER = os.environ.get("DJANGO_EMAIL_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("DJANGO_EMAIL_PASSWORD", "")
    DEFAULT_FROM_EMAIL = EMAIL_HOST_USER
