"""MediaCrawler 命令执行器。

由前端按钮触发：在 {MEDIACRAWLER_DIR} 目录执行
    uv run main.py --platform xhs --lt qrcode --type search --keywords "k1,k2" ...
MediaCrawler 会自己弹出浏览器并显示登录二维码，用户扫码后开始抓取；
进程结束后自动解析其 data 目录下的 JSONL 并导入平台（见 importer.py）。
"""
import logging
import os
import shutil
import subprocess
import threading
from datetime import datetime

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

_proc = None
_proc_lock = threading.Lock()
_pending_run_ids: list = []  # 排队等待执行的 run id（单进程顺序执行）


def _media_dir() -> str:
    """MediaCrawler 项目目录（settings.MEDIACRAWLER_DIR，需包含 main.py）。"""
    media_dir = getattr(settings, "MEDIACRAWLER_DIR", "")
    if not media_dir:
        raise RuntimeError("未配置 MEDIACRAWLER_DIR")
    return str(media_dir)


def _log_dir() -> str:
    d = os.path.join(settings.BASE_DIR, "mediacrawler_logs")
    os.makedirs(d, exist_ok=True)
    return d


def get_running_process():
    """返回当前仍在运行的子进程（没有则 None）。"""
    global _proc
    with _proc_lock:
        p = _proc
        if p is not None and p.poll() is None:
            return p
        return None


def is_running() -> bool:
    return get_running_process() is not None


def has_pending() -> bool:
    """是否还有排队中的任务。"""
    return bool(_pending_run_ids)


def stop_run():
    """终止正在运行的 MediaCrawler 子进程（尽力杀掉进程树）。"""
    global _proc
    with _proc_lock:
        p = _proc
    if p is None:
        return False
    try:
        if p.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                               capture_output=True)
            else:
                p.terminate()
        return True
    except Exception as exc:
        logger.warning("stop mediacrawler failed: %s", exc)
        return False


def _snapshot_data_files(platform: str) -> dict:
    """快照该平台数据目录下所有 jsonl 文件的当前行数（{相对路径: 行数}）。

    爬虫为单进程串行执行，任务启动时的行数快照即可精确切分「本任务爬取的数据」：
    导入时只处理快照之后新增的行，使主题归属 = 任务来源。
    """
    import glob

    snapshot = {}
    base = _media_dir()
    folder = "xhs" if platform == "xhs" else "weibo"
    data_dir = os.path.join(base, "data", folder, "jsonl")
    for path in glob.glob(os.path.join(data_dir, "search_*.jsonl")):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                line_count = sum(1 for _ in fh)
        except OSError:
            continue
        rel = os.path.relpath(path, base).replace("\\", "/")
        snapshot[rel] = line_count
    return snapshot


def _build_command(platform: str, keywords: list, max_notes: int) -> list:
    """构造 uv run main.py 命令。login 交给 MediaCrawler（浏览器弹二维码）。"""
    uv = shutil.which("uv") or "uv"
    keyword_str = ",".join([k.strip() for k in keywords if k and k.strip()])
    if not keyword_str:
        raise ValueError("主题没有可用关键词（核心/关联词至少一个）")
    return [
        uv, "run", "main.py",
        "--platform", platform,
        "--lt", "qrcode",
        "--type", "search",
        "--keywords", keyword_str,
        "--crawler_max_notes_count", str(max_notes),
        "--save_data_option", "jsonl",
    ]


def start_run(run):
    """启动 MediaCrawler 子进程（run 为 MediaCrawlerRun 记录）。

    已有任务在运行时进入排队（run.status=queued），当前任务结束后自动执行；
    空闲则立即启动，另起守护线程等待进程结束 → 自动导入数据。
    """
    global _proc
    with _proc_lock:
        existing = _proc
        if existing is not None and existing.poll() is None:
            run.status = "queued"
            run.save(update_fields=["status"])
            _pending_run_ids.append(run.id)
            logger.info("mediacrawler run %s queued", run.id)
            return None

    keywords = [k.strip() for k in (run.keywords or "").split(",") if k.strip()]
    cmd = _build_command(run.platform, keywords, 20)
    log_path = os.path.join(_log_dir(), "mediacrawler_%s.log" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    run.log_path = log_path
    run.status = "running"
    # 启动前快照数据文件行数：本次任务爬到的数据 = 快照之后新增的行，
    # 导入时按该窗口归属到本任务主题（串行执行保证无其他写者）
    run.snapshot_lines = _snapshot_data_files(run.platform)
    run.save(update_fields=["log_path", "status", "snapshot_lines"])

    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")

    log_file = open(log_path, "w", encoding="utf-8", errors="replace")
    kwargs = {
        "cwd": _media_dir(),
        "stdout": log_file,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
        "env": env,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    proc = subprocess.Popen(cmd, **kwargs)
    proc._run_id = run.id  # 进程归属，供对账判断
    run.pid = proc.pid
    run.save(update_fields=["pid"])
    with _proc_lock:
        _proc = proc

    logger.info("mediacrawler started pid=%s cmd=%s", proc.pid, " ".join(cmd))

    # 守护线程：等待结束 → 关闭日志句柄 → 自动导入
    def _watch():
        try:
            exit_code = proc.wait()
        except Exception as exc:
            logger.exception("wait mediacrawler failed: %s", exc)
            exit_code = -1
        try:
            log_file.flush()
            log_file.close()
        except Exception:
            pass
        with _proc_lock:
            if _proc is proc:
                _proc = None

        from ..models import MediaCrawlerRun

        run_obj = MediaCrawlerRun.objects.filter(pk=run.pk).first()
        if run_obj is None:
            return
        was_stopped = run_obj.status == "stopped"  # 用户主动停止
        run_obj.exit_code = exit_code
        run_obj.finished_at = timezone.now()
        import_ok = True
        # 无论退出码都尝试导入：进程中断时 MediaCrawler 往往已写出部分数据文件，
        # 增量导入（按文件行数记录进度）保证只导入新行、可重复执行
        if run_obj.topic_id:
            try:
                from .importer import import_new_data

                run_obj.status = "importing"
                run_obj.save(update_fields=["status"])
                summary = import_new_data(run_obj)
                run_obj.fetched_count = summary.get("fetched", 0)
                run_obj.new_count = summary.get("new", 0)
                run_obj.duplicate_count = summary.get("duplicate", 0)
                run_obj.updated_count = summary.get("updated", 0)
                run_obj.comment_count = summary.get("comments", 0)
            except Exception:
                logger.exception("mediacrawler auto import failed")
                import_ok = False
        if exit_code == 0 and import_ok:
            run_obj.status = "finished"
        elif was_stopped:
            run_obj.status = "stopped"
            run_obj.error_message = "已停止；已抓取的数据已导入" if import_ok else "已停止；数据导入失败"
        elif import_ok:
            run_obj.status = "failed"
            run_obj.error_message = f"MediaCrawler 退出码 {exit_code}；已抓取的数据已导入，可查看日志了解中断原因"
        else:
            run_obj.status = "failed"
            run_obj.error_message = "导入数据失败，可在日志中查看详情"
        run_obj.save()
        logger.info("mediacrawler run %s finished status=%s", run.pk, run_obj.status)

        # 排队任务接力
        _start_next_pending()

    threading.Thread(target=_watch, name="mediacrawler-watch-%s" % run.pk, daemon=True).start()
    return proc


def _start_next_pending():
    """取出排队中的下一个任务执行。"""
    global _pending_run_ids
    if not _pending_run_ids:
        return
    from ..models import MediaCrawlerRun

    next_id = _pending_run_ids.pop(0)
    next_run = MediaCrawlerRun.objects.filter(pk=next_id).first()
    if next_run is None:
        _start_next_pending()
        return
    try:
        start_run(next_run)
    except Exception:
        logger.exception("start queued mediacrawler run %s failed", next_id)
        next_run.status = "failed"
        next_run.error_message = "排队任务启动失败"
        next_run.finished_at = timezone.now()
        next_run.save(update_fields=["status", "error_message", "finished_at"])
        _start_next_pending()




def reconcile_stale_runs():
    """服务重启/进程丢失后：把卡在 running/queued/importing 的记录标记为停止，
    并自动导入已抓取的数据（增量导入，按文件行数推进进度，可安全重复执行）。

    采集结束或服务断开后均自动上传数据，前端无需再点「导入」。
    """
    from ..models import MediaCrawlerRun

    p = get_running_process()
    current_run_id = getattr(p, "_run_id", None) if p is not None else None
    qs = MediaCrawlerRun.objects.filter(status__in=["running", "queued", "importing"])
    if current_run_id:
        qs = qs.exclude(pk=current_run_id)
    n = 0
    for run in list(qs):
        run.status = "stopped"
        if not (run.snapshot_lines or {}):
            # 排队中未实际启动的任务：没有行数快照，无法界定本任务的数据窗口，不导入
            run.error_message = "服务重启导致运行中断（排队中未开始，无数据可导入）"
            run.finished_at = run.finished_at or timezone.now()
            run.save()
            n += 1
            continue
        run.error_message = "服务重启导致运行中断；已抓取的数据已自动导入"
        try:
            from .importer import import_new_data

            summary = import_new_data(run)
            run.fetched_count = summary.get("fetched", 0)
            run.new_count = summary.get("new", 0)
            run.duplicate_count = summary.get("duplicate", 0)
            run.updated_count = summary.get("updated", 0)
            run.comment_count = summary.get("comments", 0)
        except Exception:
            logger.exception("stale mediacrawler run %s auto import failed", run.pk)
            run.error_message = "服务重启导致运行中断；自动导入失败，可在采集过程页面重试导入"
        run.finished_at = run.finished_at or timezone.now()
        run.save()
        n += 1
    if n:
        logger.info("reconciled %s stale mediacrawler runs (auto-imported)", n)
    return n


def read_log_tail(log_path: str, lines: int = 200) -> str:
    """读取日志尾部（供前端展示二维码等待提示等输出）。"""
    if not log_path or not os.path.exists(log_path):
        return ""
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
        return "\n".join(content.splitlines()[-lines:])
    except Exception:
        return ""