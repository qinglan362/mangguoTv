"""启动调度器 + 派发线程（规范启动方式）。

用法：python manage.py runscheduler
注意：调度器只能跑在恰好一个进程中，切勿多进程同时启动。
"""
import signal
import sys
import time

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "启动 APScheduler 调度器与采集派发线程"

    def handle(self, *args, **options):
        from tasks.services.scheduler import ensure_started, shutdown

        ensure_started()
        self.stdout.write(self.style.SUCCESS("调度器已启动，按 Ctrl+C 停止"))

        stop_requested = {"value": False}

        def _handle_signal(signum, frame):
            stop_requested["value"] = True

        try:
            signal.signal(signal.SIGINT, _handle_signal)
            signal.signal(signal.SIGTERM, _handle_signal)
        except (ValueError, OSError):
            pass  # Windows 下部分信号不可注册

        while not stop_requested["value"]:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                stop_requested["value"] = True

        self.stdout.write("正在停止调度器...")
        shutdown()
        sys.exit(0)
