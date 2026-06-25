"""
I/O Worker 进程 —— 在子进程中执行文件复制与 MD5 校验。
Windows 必须使用 spawn 而非 fork。
"""
import os
import shutil
import hashlib
import time
from pathlib import Path
from multiprocessing import Process, Queue, get_context
from datetime import datetime

from backend.core.db import get_connection, init_db

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
SMALL_FILE_THRESHOLD = 10 * 1024 * 1024  # 10MB —— 小文件用 size+mtime 比对
READ_CHUNK_SIZE = 8 * 1024 * 1024         # 8MB 读块


# ---------------------------------------------------------------------------
# 校验函数
# ---------------------------------------------------------------------------

def _md5_of_file(file_path: str) -> str:
    """计算文件 MD5 哈希（分块读取，大文件友好）。"""
    md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(READ_CHUNK_SIZE)
            if not chunk:
                break
            md5.update(chunk)
    return md5.hexdigest()


def _verify_small_file(source: str, target: str) -> bool:
    """小文件校验：比对 size + modified_time（快速路径）。"""
    try:
        src_stat = os.stat(source)
        tgt_stat = os.stat(target)
        return (
            src_stat.st_size == tgt_stat.st_size
            and abs(src_stat.st_mtime - tgt_stat.st_mtime) < 1.0  # 容忍 1 秒偏差
        )
    except OSError:
        return False


def _verify_large_file(source: str, target: str) -> bool:
    """大文件校验：MD5 比对（安全路径）。"""
    try:
        return _md5_of_file(source) == _md5_of_file(target)
    except OSError:
        return False


def verify_file(source: str, target: str, size: int) -> dict:
    """
    根据文件大小选择校验策略。
    返回: {"ok": bool, "method": "size_mtime" | "md5", "error": str | None}
    """
    if not os.path.exists(target):
        return {"ok": False, "method": "none", "error": "Target file does not exist"}

    if size < SMALL_FILE_THRESHOLD:
        ok = _verify_small_file(source, target)
        return {"ok": ok, "method": "size_mtime", "error": None if ok else "Size or mtime mismatch"}
    else:
        ok = _verify_large_file(source, target)
        return {"ok": ok, "method": "md5", "error": None if ok else "MD5 mismatch"}


# ---------------------------------------------------------------------------
# Worker 任务函数
# ---------------------------------------------------------------------------

def _copy_task(
    task_queue: Queue,
    result_queue: Queue,
    db_path: str,
) -> None:
    """
    在子进程中执行的文件复制任务。

    从 task_queue 读取文件列表（dict: {id, path, name, size}），
    复制到 target_root，校验完成后通过 result_queue 回报状态。

    task_queue 中放入 None 表示任务结束。
    """
    # 子进程中需要独立初始化数据库连接
    init_db()
    conn = get_connection()

    while True:
        item = task_queue.get()
        if item is None:
            break  # 终止信号

        action = item.get("action", "copy")

        if action == "copy":
            source_path = item["source"]
            target_root = item["target_root"]
            file_info = item.get("file", {})

            result = _do_copy_one(source_path, target_root, file_info)

        elif action == "commit":
            # Commit 阶段：更新 manifest 状态
            plan_id = item["plan_id"]
            conn.execute(
                "UPDATE migration_manifest SET status='committed', committed_at=strftime('%s','now') WHERE id=?",
                (plan_id,),
            )
            conn.commit()
            result = {"action": "commit", "plan_id": plan_id, "ok": True}

        else:
            result = {"action": action, "ok": False, "error": f"Unknown action: {action}"}

        result_queue.put(result)

    conn.close()


def _do_copy_one(source_path: str, target_root: str, file_info: dict) -> dict:
    """复制单个文件到目标目录（保持相对路径结构）。"""
    try:
        rel_path = file_info.get("rel_path", Path(source_path).name)
        target_path = os.path.join(target_root, rel_path)

        # 确保目标父目录存在
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        # 跳过已存在且校验通过的文件
        if os.path.exists(target_path):
            verify = verify_file(source_path, target_path, file_info.get("size", 0))
            if verify["ok"]:
                return {
                    "action": "copy",
                    "source": source_path,
                    "target": target_path,
                    "ok": True,
                    "skipped": True,
                }

        # 复制（保留元数据）
        shutil.copy2(source_path, target_path)

        # 校验
        verify = verify_file(source_path, target_path, file_info.get("size", 0))
        return {
            "action": "copy",
            "source": source_path,
            "target": target_path,
            "ok": verify["ok"],
            "verify_method": verify["method"],
            "error": verify.get("error"),
        }

    except Exception as exc:
        return {
            "action": "copy",
            "source": source_path,
            "ok": False,
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# 公开 API：启动 Worker
# ---------------------------------------------------------------------------

def spawn_worker(
    task_queue: Queue,
    result_queue: Queue,
    db_path: str = "",
) -> Process:
    """
    启动一个 I/O Worker 子进程（spawn 模式，Windows 兼容）。

    参数:
        task_queue:  主进程 → Worker 的任务队列
        result_queue: Worker → 主进程的结果队列
        db_path:     数据库路径（Worker 需要独立连接）

    返回:
        multiprocessing.Process 实例（已 start）
    """
    ctx = get_context("spawn")
    worker = ctx.Process(
        target=_copy_task,
        args=(task_queue, result_queue, db_path),
        name="Archivisor-IO-Worker",
        daemon=True,
    )
    worker.start()
    return worker
