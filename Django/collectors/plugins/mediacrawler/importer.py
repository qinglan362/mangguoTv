"""MediaCrawler 数据导入器。

扫描 {MEDIACRAWLER_DIR}/data/xhs/jsonl/ 下的 search_contents_*.jsonl 与
search_comments_*.jsonl，把新行（按文件记录已导入行数增量处理）解析为
标准 RawPost / 评论，走平台既有流水线：
    清洗去重(ingest_batch) → 内容识别(规则+LLM) → 预警检查 → 看板展示。
"""
import glob
import json
import logging
import os
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.utils import timezone

from collectors.schemas import AuthorInfo, RawPost
from posts.services.ingest import ingest_batch
from tasks.models import CollectionRun

from ..comments_service import store_comments

logger = logging.getLogger(__name__)


def _data_dir(platform: str) -> str:
    """MediaCrawler 数据目录：xhs → data/xhs/jsonl，wb → data/weibo/jsonl。"""
    media_dir = str(getattr(settings, "MEDIACRAWLER_DIR", ""))
    folder = "xhs" if platform == "xhs" else "weibo"
    return os.path.join(media_dir, "data", folder, "jsonl")


def _ms_to_datetime(value):
    """毫秒时间戳 → 带时区 datetime；失败返回 None。"""
    if not value:
        return None
    try:
        ts = float(value)
        if ts > 1e12:
            ts = ts / 1000
        return datetime.fromtimestamp(ts, tz=dt_timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _num(value, default=0):
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


def _split_csv(value) -> list:
    if not value:
        return []
    return [p.strip() for p in str(value).split(",") if p.strip()]


def _file_state(path: str):
    """取文件的导入进度记录（不写库，成功后由调用方保存）。"""
    from ..models import MediaCrawlerFileState

    rel = os.path.relpath(path, str(settings.MEDIACRAWLER_DIR)).replace("\\", "/")
    state, _ = MediaCrawlerFileState.objects.get_or_create(path=rel, defaults={"imported_lines": 0})
    if not os.path.exists(path):
        return state, [], 0
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        all_lines = fh.readlines()
    start = min(state.imported_lines, len(all_lines))
    return state, all_lines[start:], len(all_lines)


def _content_to_raw(item: dict, now=None) -> RawPost:
    """MediaCrawler search_contents 行 → RawPost。"""
    now = now or timezone.now()
    note_id = str(item.get("note_id") or "")
    images = _split_csv(item.get("image_list"))
    tags = _split_csv(item.get("tag_list"))
    return RawPost(
        post_id=note_id,
        platform="xiaohongshu",
        url=item.get("note_url") or (f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else ""),
        title=(item.get("title") or "")[:512],
        content=item.get("desc") or "",
        author=AuthorInfo(
            platform="xiaohongshu",
            author_id=str(item.get("creator_hash") or "") or None,
            name=item.get("nickname") or "",
        ),
        published_at=_ms_to_datetime(item.get("time")),
        collected_at=now,
        like_count=_num(item.get("liked_count")),
        comment_count=_num(item.get("comment_count")),
        share_count=_num(item.get("share_count")),
        favorite_count=_num(item.get("collected_count")),
        hashtags=[f"#{t}" for t in tags],
        cover_url=images[0] if images else None,
        images=images,
    )


def _comment_to_dict(item: dict) -> dict:
    """MediaCrawler search_comments 行 → store_comments 入参。"""
    return {
        "comment_id": str(item.get("comment_id") or ""),
        "author_name": item.get("nickname") or "",
        "content": item.get("content") or "",
        "like_count": _num(item.get("like_count")),
        "published_at": _ms_to_datetime(item.get("create_time")),
    }


def _comment_to_dict_weibo(item: dict) -> dict:
    """MediaCrawler 微博评论行 → store_comments 入参（like 字段名不同，时间为秒级）。"""
    return {
        "comment_id": str(item.get("comment_id") or ""),
        "author_name": item.get("nickname") or "",
        "content": item.get("content") or "",
        "like_count": _num(item.get("comment_like_count")),
        "published_at": _sec_to_datetime(item.get("create_time")),
    }


def _sec_to_datetime(value):
    """秒级时间戳 → 带时区 datetime（微博 create_time 为秒级）。"""
    if not value:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=dt_timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _weibo_content_to_raw(item: dict, now=None) -> RawPost:
    """MediaCrawler 微博 search_contents 行 → RawPost。"""
    now = now or timezone.now()
    note_id = str(item.get("note_id") or "")
    content = item.get("content") or ""
    return RawPost(
        post_id=note_id,
        platform="weibo",
        url=item.get("note_url") or (f"https://m.weibo.cn/detail/{note_id}" if note_id else ""),
        title="",  # 微博无标题
        content=content,
        author=AuthorInfo(
            platform="weibo",
            author_id=str(item.get("creator_hash") or "") or None,
            name=item.get("nickname") or "",
        ),
        published_at=_sec_to_datetime(item.get("create_time")),
        collected_at=now,
        like_count=_num(item.get("liked_count")),
        comment_count=_num(item.get("comments_count")),
        share_count=_num(item.get("shared_count")),
        favorite_count=0,
        hashtags=[],
        cover_url=None,
        images=[],
    )


def import_new_data(run) -> dict:
    """导入 MediaCrawler 新抓取的数据到 run.topic，并跑分析与预警。

    按 run.platform（xhs/wb）选择数据目录与字段映射；
    返回统计 {fetched, new, duplicate, updated, comments}。
    文件进度只在数据成功入库后推进，失败可重试不丢数据。
    """
    from analysis.services.pipeline import run_for_topic
    from alerts.services.engine import check_after_collection

    topic = run.topic
    if topic is None:
        raise ValueError("运行未关联主题，无法导入")

    mc_platform = run.platform or "xhs"
    site_platform = "weibo" if mc_platform == "wb" else "xiaohongshu"
    content_parser = _weibo_content_to_raw if mc_platform == "wb" else _content_to_raw
    comment_parser = _comment_to_dict_weibo if mc_platform == "wb" else _comment_to_dict

    data_dir = _data_dir(mc_platform)
    contents_files = sorted(glob.glob(os.path.join(data_dir, "search_contents_*.jsonl")))
    comments_files = sorted(glob.glob(os.path.join(data_dir, "search_comments_*.jsonl")))

    now = timezone.now()

    # ---- 1. 解析阶段（不落库）：帖子 ----
    raw_posts: list[RawPost] = []
    contents_progress = []  # [(state, total_lines)] 入库成功后推进进度
    for path in contents_files:
        state, new_lines, total_lines = _file_state(path)
        for line in new_lines:
            line = line.strip()
            if not line:
                continue
            try:
                raw_posts.append(content_parser(json.loads(line), now))
            except (json.JSONDecodeError, KeyError, TypeError):
                logger.warning("skip bad jsonl line in %s", path)
        contents_progress.append((state, total_lines))

    # ---- 2. 解析阶段：评论（暂存 note_id -> 评论列表） ----
    comments_by_note: dict = {}
    comments_progress = []
    for path in comments_files:
        state, new_lines, total_lines = _file_state(path)
        for line in new_lines:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            note_id = str(item.get("note_id") or "")
            if not note_id:
                continue
            comments_by_note.setdefault(note_id, []).append(comment_parser(item))
        comments_progress.append((state, total_lines))

    # ---- 3. 入库：评论（帖子入库后由信号回填外键） ----
    comment_total = 0
    for note_id, comment_list in comments_by_note.items():
        comment_total += store_comments(site_platform, note_id, comment_list)

    # ---- 4. 入库：帖子（清洗/去重走既有 ingest 流水线） ----
    collection_run = CollectionRun.objects.create(
        topic=topic, platform=site_platform,
        trigger_type="manual", status="running", started_at=now,
    )
    try:
        if raw_posts:
            result = ingest_batch(topic, raw_posts, run=collection_run)
        else:
            from posts.services.ingest import IngestResult

            result = IngestResult()
        collection_run.fetched_count = len(raw_posts)
        collection_run.new_count = result.new_count
        collection_run.duplicate_count = result.duplicate_count
        collection_run.updated_count = result.updated_count
        collection_run.status = "success"
        collection_run.finished_at = timezone.now()
        collection_run.save()

        # ---- 5. 内容识别流水线（规则 + LLM），分批处理直至主题内新帖分析完 ----
        if result.new_count > 0:
            while True:
                processed = run_for_topic(topic, limit=500)
                if processed <= 0 or processed < 500:
                    break

        # ---- 6. 预警引擎（按本次导入涉及的帖子扫描） ----
        try:
            check_after_collection(topic, run=collection_run, post_ids=list(result.touched_post_ids))
        except Exception:
            logger.exception("alert check after mediacrawler import failed")

        # ---- 7. 全部成功后推进文件进度 ----
        for state, total_lines in contents_progress:
            state.imported_lines = total_lines
            state.save(update_fields=["imported_lines"])
        for state, total_lines in comments_progress:
            state.imported_lines = total_lines
            state.save(update_fields=["imported_lines"])

        return {
            "fetched": len(raw_posts),
            "new": result.new_count,
            "duplicate": result.duplicate_count,
            "updated": result.updated_count,
            "comments": comment_total,
        }
    except Exception:
        collection_run.status = "failed"
        collection_run.error_message = "MediaCrawler 数据导入失败"
        collection_run.finished_at = timezone.now()
        collection_run.save(update_fields=["status", "error_message", "finished_at"])
        raise