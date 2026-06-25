"""
扫描器 —— os.scandir 递归遍历，yield 逐条返回文件元数据。
主动跳过系统目录和禁止路径。
"""
import os
import time
from pathlib import Path
from collections.abc import Generator
from datetime import datetime

from backend.utils.security import is_safe_path, FORBIDDEN_PREFIXES
from backend.core.db import get_connection

# ---------------------------------------------------------------------------
# 额外跳过目录（除系统黑名单外）
# ---------------------------------------------------------------------------
SKIP_DIR_NAMES: set[str] = {
    "AppData",
    "$RECYCLE.BIN",
    "System Volume Information",
    "node_modules",
    ".git",
}

SKIP_PREFIXES: list[str] = [
    os.environ.get("TEMP", ""),
    os.environ.get("TMP", ""),
    *FORBIDDEN_PREFIXES,
]


def _should_skip_dir(dir_path: str) -> bool:
    """判断目录是否应该跳过（不递归进入）。"""
    name = Path(dir_path).name
    if name in SKIP_DIR_NAMES:
        return True
    # 跳过隐藏目录（以 . 开头，但保留当前目录概念）
    if name.startswith(".") and name not in (".", ".."):
        return True
    # 安全检查
    if not is_safe_path(dir_path):
        return True
    # Temp 目录
    for prefix in SKIP_PREFIXES:
        if prefix and str(dir_path).startswith(prefix):
            return True
    return False


def _parse_file_info(entry: os.DirEntry) -> dict:
    """从 os.DirEntry 提取文件元数据。"""
    try:
        stat = entry.stat()
        size = stat.st_size
        modified_time = stat.st_mtime
    except OSError:
        size = 0
        modified_time = None

    full_path = entry.path
    extension = Path(full_path).suffix.lstrip(".").lower()

    return {
        "path": full_path,
        "name": entry.name,
        "extension": extension,
        "size": size,
        "modified_time": modified_time,
        "is_active": True,
    }


# ---------------------------------------------------------------------------
# 主扫描函数
# ---------------------------------------------------------------------------

def scan_directory(
    root_path: str,
    yield_every: int = 100,
    insert_to_db: bool = True,
) -> Generator[dict, None, None]:
    """
    递归扫描目录，逐条 yield 文件元数据。

    参数:
        root_path:    扫描根目录（绝对路径）
        yield_every:  每 N 个文件 yield 一次进度事件
        insert_to_db: 是否同时写入 file_metadata 表

    Yields:
        {"type": "file", "data": {...}}   — 文件元数据
        {"type": "progress", ...}         — 进度事件
        {"type": "done", ...}             — 扫描完成汇总
    """
    root = Path(root_path).resolve()
    if not root.exists():
        yield {"type": "error", "message": f"Path does not exist: {root_path}"}
        return
    if not root.is_dir():
        yield {"type": "error", "message": f"Path is not a directory: {root_path}"}
        return
    if not is_safe_path(str(root)):
        yield {"type": "error", "message": f"Path is in forbidden zone: {root_path}"}
        return

    conn = get_connection() if insert_to_db else None
    total_files = 0
    total_size = 0
    start_time = time.perf_counter()

    # 批量插入缓冲（减少 SQLite 事务开销）
    batch: list[dict] = []
    BATCH_SIZE = 200

    def _flush_batch():
        nonlocal batch
        if not batch or conn is None:
            batch.clear()
            return
        conn.executemany(
            """INSERT OR IGNORE INTO file_metadata (path, name, extension, size, modified_time, is_active)
               VALUES (:path, :name, :extension, :size, :modified_time, 1)""",
            batch,
        )
        conn.commit()
        batch.clear()

    try:
        # 使用栈迭代代替递归，避免 Python 递归深度限制
        dir_stack: list[str] = [str(root)]

        while dir_stack:
            current_dir = dir_stack.pop()

            try:
                entries = list(os.scandir(current_dir))
            except (PermissionError, OSError):
                continue

            for entry in entries:
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue

                if is_dir:
                    if not _should_skip_dir(entry.path):
                        dir_stack.append(entry.path)
                    continue

                # ---- 处理文件 ----
                info = _parse_file_info(entry)
                total_files += 1
                total_size += info["size"]

                # 入库
                if conn is not None:
                    batch.append(info)
                    if len(batch) >= BATCH_SIZE:
                        _flush_batch()

                yield {"type": "file", "data": info}

                # 进度事件
                if total_files % yield_every == 0:
                    elapsed = time.perf_counter() - start_time
                    yield {
                        "type": "progress",
                        "files_so_far": total_files,
                        "total_size_so_far": total_size,
                        "current_dir": current_dir,
                        "elapsed_sec": round(elapsed, 2),
                    }

        # 冲刷剩余缓冲
        _flush_batch()

        elapsed = time.perf_counter() - start_time
        yield {
            "type": "done",
            "total_files": total_files,
            "total_size": total_size,
            "duration_sec": round(elapsed, 3),
        }

    except Exception:
        _flush_batch()
        raise


# ---------------------------------------------------------------------------
# 便捷封装：扫描并返回摘要（不逐条产出，适合 RPC 直接调用）
# ---------------------------------------------------------------------------

def scan_and_summarize(root_path: str) -> dict:
    """扫描目录并返回汇总结果（阻塞式，适合 JSON-RPC 单次调用）。"""
    last_event: dict = {}
    for event in scan_directory(root_path, yield_every=500, insert_to_db=True):
        last_event = event
    return last_event
