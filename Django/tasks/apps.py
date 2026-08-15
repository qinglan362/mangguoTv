import os
import sys

from django.apps import AppConfig


class TasksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tasks"

    def ready(self):
        from django.conf import settings

        if not settings.SCHEDULER.get("auto_start"):
            return

        # 仅 runserver 启动调度器，其他 manage.py 命令（migrate/shell/管理命令）
        # 一律不拉起调度线程，避免双调度器/命令误启动（L2）。
        if len(sys.argv) < 2 or sys.argv[1] != "runserver":
            return

        # runserver 带 autoreload 时会起「reloader 父进程 + 服务子进程」两个进程，
        # ready() 在两边都会执行；只让实际服务进程（RUN_MAIN=true）启动调度器，
        # 避免父进程也拉起一套调度/派发线程导致重复采集。--noreload 时单进程即服务进程。
        if "--noreload" not in sys.argv and os.environ.get("RUN_MAIN") != "true":
            return

        from tasks.services.scheduler import ensure_started
        ensure_started()
