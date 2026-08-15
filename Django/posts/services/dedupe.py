"""帖子去重：精确哈希去重 + simhash 相似去重。

- 精确去重：content_hash 相同 → 同一条帖，仅更新互动数据。
- 相似去重：simhash 海明距离 <= 阈值 → 归入同一 dedup_group（跨平台搬运/改写）。
"""
import re
import uuid

import simhash

_HAMMING_THRESHOLD = 6  # 相似度阈值（2-gram 下：微改 3~5、无关帖 30+）
_MIN_GRAM = 8            # 参与相似判定所需最少字 2-gram 数（过短文本跳过）

# 参与相似度计算的词元（过滤标点/停用词）
_STOPWORDS = set("的了和是在不就都而及与或一个我你他她它们这那有也还要呢吗吧啊哦呃于与")


def _tokens(text: str) -> list[str]:
    """字级 2-gram 词元。

    中文按字滑窗取 2-gram，搬运/改写（改个别字词、加前缀）
    只影响局部 gram，海明距离明显小于无关帖。
    """
    if not text:
        return []
    parts = re.split(r"[^一-龥A-Za-z0-9]+", text)
    grams = []
    for p in parts:
        for i in range(len(p) - 1):
            grams.append(p[i : i + 2])
    return grams


def _simhash_value(text: str):
    return simhash.Simhash(" ".join(_tokens(text))).value


def _hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def find_similar_groups(items: list) -> dict:
    """输入 [{"content": str, "hash": str, ...}]，输出相似去重组映射 {hash: group_id}。

    算法：线性扫描 + 距离剪枝（生产可换 minhash LSH，数据量大时再优化）。
    """
    groups: dict = {}
    group_counter = [0]
    for i, item in enumerate(items):
        hv = _simhash_value(item["content"])
        found = None
        # 与已分配组代表比较
        for rep_hash, rep_hv in groups.get("_reps", {}).items():
            if _hamming_distance(hv, rep_hv) <= _HAMMING_THRESHOLD:
                found = rep_hash
                break
        if found:
            gid = groups[found]
        else:
            gid = "group_%d" % group_counter[0]
            group_counter[0] += 1
            groups.setdefault("_reps", {})
            groups["_reps"][item["hash"]] = hv
            groups[item["hash"]] = gid
        groups[item["hash"]] = gid
    groups.pop("_reps", None)
    return groups


def find_similar_groups_fast(items: list) -> dict:
    """简化版：直接返回空映射（精确去重已覆盖大多数；相似去重 M8 阶段启用）。"""
    return {}


def assign_dedup_groups(items: list) -> dict:
    """对一批帖子的内容做 simhash 相似分组，返回 {hash: group_id|None}。

    相似（海明距离 <= _HAMMING_THRESHOLD）的帖子归入同一 group_id；
    独立帖返回 None。代表与组内各帖逐个比较，batch 规模 O(n) 比较。
    """
    if not items:
        return {}
    reps: list = []  # [(rep_hash, rep_hv, gid)]
    result: dict = {}
    gid_counter = 0
    # 每次调用生成唯一批次前缀：Post.dedup_group 是持久化字段，若不唯一，
    # 后续批次新组的 "sim_0" 会撞上历史批次无关帖，导致新帖被误判重复丢弃。
    batch_key = uuid.uuid4().hex[:12]
    for item in items:
        tokens = _tokens(item.get("content", ""))
        if len(tokens) < _MIN_GRAM:  # 过短文本不参与相似判定
            result[item.get("hash", "")] = None
            continue
        hv = _simhash_value(item.get("content", ""))
        matched_gid = None
        for rep_hash, rep_hv, gid in reps:
            if _hamming_distance(hv, rep_hv) <= _HAMMING_THRESHOLD:
                matched_gid = gid
                break
        if matched_gid is None:
            gid = "sim_%s_%d" % (batch_key, gid_counter)
            gid_counter += 1
            reps.append((item.get("hash", ""), hv, gid))
            result[item.get("hash", "")] = gid  # 代表帖自己也入组
        else:
            result[item.get("hash", "")] = matched_gid
    return result
