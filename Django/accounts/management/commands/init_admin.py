"""创建初始管理员账号（不存在 staff 用户时）。

安全约定：不提供任何内置默认口令。密码优先取 YQ_ADMIN_PASSWORD 环境变量；
未设置时随机生成强密码并仅打印一次（登录后请立即修改）。
"""
import os
import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "创建初始管理员账号（已存在 staff 用户则跳过）"

    def handle(self, *args, **options):
        User = get_user_model()
        if User.objects.filter(is_staff=True).exists():
            self.stdout.write(self.style.WARNING("已存在管理员账号，跳过"))
            return
        username = os.environ.get("YQ_ADMIN_USERNAME", "admin")
        password = os.environ.get("YQ_ADMIN_PASSWORD", "")
        generated = False
        if not password:
            password = secrets.token_urlsafe(12)
            generated = True
        User.objects.create_superuser(username=username, password=password, first_name="系统管理员")
        if generated:
            self.stdout.write(self.style.SUCCESS(
                f"初始管理员已创建：{username}\n密码（随机生成，仅显示这一次）：{password}\n请立即登录并修改密码。"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(f"初始管理员已创建：{username}（密码来自 YQ_ADMIN_PASSWORD，登录后请尽快修改）"))
