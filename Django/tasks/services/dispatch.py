"""采集运行派发线程。

interval job 只负责入队（enqueue_run 创建 pending 记录）；
本线程每 N 秒按创建时间顺序取 pending 运行并发执行，与调度触发解耦。
"""
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings

from tasks.models import CollectionRun

logger = logging.getLogger(__name__)

_inflight_lock = threading.Lock()
_inflight: set = set()


def _claim_in_db(run_id: int) -> bool:
    """DB 层原子抢占：仅当仍为 pending 时置为 running，返回是否抢到。

    与内存 _inflight 双保险，跨线程/跨请求（API 手动触发、调度重试回调）
    都走同一抢占路径，避免同一 run 被并发执行。
    """
    return CollectionRun.objects.filter(pk=run_id, status="pending").update(status="running") == 1


def claim_runs(max_count: int) -> list:
    """按创建时间取回待执行运行并原子标记 in-flight（防重复执行）。"""
    with _inflight_lock:
        runs = (
            CollectionRun.objects.filter(status="pending")
            .order_by("created_at")
        )
        claimed = []
        for run in runs:
            if run.id in _inflight:
                continue
            if len(claimed) >= max_count:
                break
            if _claim_in_db(run.id):
                _inflight.add(run.id)
                claimed.append(run)
        return claimed


def claim_specific_run(run_id: int) -> bool:
    """按 id 抢占单个运行（重试/手动触发复用同一套 in-flight 保护）。"""
    with _inflight_lock:
        if run_id in _inflight:
            return False
        if _claim_in_db(run_id):
            _inflight.add(run_id)
            return True
        return False


def release_run(run_id: int):
    with _inflight_lock:
        _inflight.discard(run_id)


def dispatch_once(max_workers: int = None):
    """单次派发：取 pending 运行并真正并发执行（worker_concurrency 生效）。"""
    max_workers = max_workers or settings.SCHEDULER.get("worker_concurrency", 4)
    claimed = claim_runs(max_workers)
    if not claimed:
        return

    from tasks.services.dispatcher import execute_run

    def _run(run):
        try:
            execute_run(run.id)
        except Exception:
            logger.exception("dispatch execute run %s failed", run.id)
        finally:
            release_run(run.id)

    with ThreadPoolExecutor(max_workers=len(claimed)) as pool:
        list(pool.map(_run, claimed))


class DispatchManager:
    """后台派发线程（常驻）。"""

    def __init__(self):
        self._stop = threading.Event()
        self._thread = None

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.running:
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="collection-dispatch", daemon=True)
        self._thread.start()
        logger.info("dispatch manager started")
        return self

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._thread = None
        logger.info("dispatch manager stopped")

    def _loop(self):
        poll_seconds = settings.SCHEDULER.get("dispatch_poll_seconds", 5)
        while not self._stop.is_set():
            try:
                dispatch_once()
            except Exception:
                logger.exception("dispatch_once error")
            self._stop.wait(poll_seconds)

    def mark_interrupted(self):
        """进程关闭时，把 in-flight/running 的运行标记为失败（interrupted）。"""
        CollectionRun.objects.filter(status="running").update(
            status="failed", error_message="调度器关闭，运行被中断",
        )


# 全局单例
dispatch_manager = DispatchManager()
