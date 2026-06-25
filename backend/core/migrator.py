"""
迁移引擎 —— Plan 生成 → 文件复制 → 校验 → Commit（软删除 + Junction）。
"""
import os
import time
import shutil
from pathlib import Path
from datetime import datetime
from multiprocessing import Queue

from backend.core.db import get_connection
from backend.core.scanner import scan_directory
from backend.utils.junction import create_junction, remove_junction, is_junction
from backend.utils.security import is_safe_path

# ---------------------------------------------------------------------------
# Plan 阶段
# ---------------------------------------------------------------------------


def create_migration_plan(
    source: str,
    target: str,
    filters: list[str] | None = None,
) -> dict:
    """
    生成迁移计划，写入 migration_manifest。

    参数:
        source:  源目录（如 C:\\Users\\A\\Downloads）
        target:  目标根目录（如 D:\\ArchivedData）
        filters: 文件扩展名过滤列表（如 ["pdf", "docx"]），None 表示全部

    返回:
        {"plan_id": int, "source": str, "target": str, "file_count": int,
         "total_size": int, "status": "pending"}
    """
    if not is_safe_path(source):
        raise PermissionError(f"Source path is forbidden: {source}")
    if not is_safe_path(target):
        raise PermissionError(f"Target path is forbidden: {target}")

    source_path = Path(source).resolve()
    target_path = Path(target).resolve()

    if not source_path.exists():
        raise FileNotFoundError(f"Source does not exist: {source}")
    if source_path == target_path:
        raise ValueError("Source and target must be different directories")

    # 确保目标根目录存在
    target_path.mkdir(parents=True, exist_ok=True)

    # 统计源目录文件
    file_count = 0
    total_size = 0
    files: list[dict] = []

    for event in scan_directory(str(source_path), yield_every=500, insert_to_db=False):
        if event["type"] == "file":
            info = event["data"]
            ext = info.get("extension", "")
            # 过滤
            if filters and ext not in [f.strip(".").lower() for f in filters]:
                continue
            file_count += 1
            total_size += info["size"]
            files.append(info)
        elif event["type"] == "error":
            raise RuntimeError(f"Scan error: {event['message']}")

    # 写入 migration_manifest
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO migration_manifest
           (source_path, target_path, file_count, total_size, status)
           VALUES (?, ?, ?, ?, 'pending')""",
        (str(source_path), str(target_path), file_count, total_size),
    )
    conn.commit()
    plan_id = cursor.lastrowid

    return {
        "plan_id": plan_id,
        "source": str(source_path),
        "target": str(target_path),
        "file_count": file_count,
        "total_size": total_size,
        "status": "pending",
    }


# ---------------------------------------------------------------------------
# 执行阶段（文件复制 + 校验）
# ---------------------------------------------------------------------------


def execute_migration(plan_id: int, task_queue: Queue, result_queue: Queue) -> bool:
    """
    将迁移计划中的文件逐个推入 Worker 队列进行复制和校验。

    参数:
        plan_id:       迁移计划 ID
        task_queue:    主进程 → Worker 的任务队列
        result_queue:  Worker → 主进程的结果队列

    返回:
        True: 全部文件复制并校验通过
        False: 存在失败文件
    """
    conn = get_connection()

    # 读取 Plan
    manifest = conn.execute(
        "SELECT * FROM migration_manifest WHERE id = ?", (plan_id,)
    ).fetchone()
    if manifest is None:
        raise LookupError(f"Migration plan not found: plan_id={plan_id}")
    if manifest["status"] not in ("pending", "copying"):
        raise RuntimeError(
            f"Plan {plan_id} status is '{manifest['status']}', "
            f"expected 'pending' or 'copying'"
        )

    source_path = manifest["source_path"]
    target_path = manifest["target_path"]

    # 更新状态为 copying
    conn.execute(
        "UPDATE migration_manifest SET status='copying' WHERE id=?",
        (plan_id,),
    )
    conn.commit()

    # 扫描源目录，逐文件推入 Worker
    sent_count = 0
    for event in scan_directory(source_path, yield_every=200, insert_to_db=False):
        if event["type"] != "file":
            continue

        info = event["data"]
        source_file = info["path"]
        # 保持相对路径结构
        rel_path = os.path.relpath(source_file, source_path)
        target_root = os.path.join(target_path, Path(source_path).name)

        task_queue.put({
            "action": "copy",
            "source": source_file,
            "target_root": target_root,
            "file": {
                "rel_path": rel_path,
                "size": info["size"],
                "name": info["name"],
            },
        })
        sent_count += 1

    # 等待 Worker 完成所有文件
    failed = []
    for _ in range(sent_count):
        result = result_queue.get(timeout=300)  # 5 分钟超时
        if not result.get("ok"):
            failed.append(result)

    if failed:
        conn.execute(
            "UPDATE migration_manifest SET status='pending' WHERE id=?",
            (plan_id,),
        )
        conn.commit()
        # 写入失败详情到审计日志
        _write_audit_log(plan_id, failed)
        return False

    # 校验全部通过，标记 verified
    conn.execute(
        "UPDATE migration_manifest SET status='verified' WHERE id=?",
        (plan_id,),
    )
    conn.commit()
    return True


# ---------------------------------------------------------------------------
# Commit 阶段（软删除 + Junction 创建）
# ---------------------------------------------------------------------------


def commit_migration(plan_id: int) -> bool:
    """
    提交迁移：① 将源目录重命名为 {name}_Archived_{YYYYMMDD}
              ② 记录 source_renamed_to
              ③ 在源位置创建指向目标目录的 Junction
              ④ 状态标记 committed

    注意：此操作需要管理员权限（mklink /J）。
    """
    conn = get_connection()
    manifest = conn.execute(
        "SELECT * FROM migration_manifest WHERE id = ?", (plan_id,)
    ).fetchone()

    if manifest is None:
        raise LookupError(f"Migration plan not found: plan_id={plan_id}")
    if manifest["status"] != "verified":
        raise RuntimeError(
            f"Plan {plan_id} status is '{manifest['status']}', "
            f"must be 'verified' before commit"
        )

    source = Path(manifest["source_path"])
    target_root = Path(manifest["target_path"])
    target_dir = target_root / source.name

    # ① 软删除：重命名源目录
    date_tag = datetime.now().strftime("%Y%m%d")
    renamed = source.with_name(f"{source.name}_Archived_{date_tag}")

    # 处理重名冲突
    counter = 1
    while renamed.exists():
        renamed = source.with_name(f"{source.name}_Archived_{date_tag}_{counter}")
        counter += 1

    os.rename(str(source), str(renamed))

    # ② 记录重命名路径
    conn.execute(
        "UPDATE migration_manifest SET source_renamed_to=? WHERE id=?",
        (str(renamed), plan_id),
    )
    conn.commit()

    # ③ 创建 Junction：原路径 → 目标路径
    try:
        create_junction(str(source), str(target_dir))
    except Exception:
        # Junction 创建失败 → 回滚重命名
        os.rename(str(renamed), str(source))
        conn.execute(
            "UPDATE migration_manifest SET source_renamed_to=NULL WHERE id=?",
            (plan_id,),
        )
        conn.commit()
        raise

    # ④ 更新 file_metadata 中的 is_active 标记
    conn.execute(
        """UPDATE file_metadata SET is_active=0
           WHERE path LIKE ?""",
        (str(renamed) + "%",),
    )
    conn.commit()

    # ⑤ 标记 committed
    conn.execute(
        "UPDATE migration_manifest SET status='committed', committed_at=strftime('%s','now') WHERE id=?",
        (plan_id,),
    )
    conn.commit()

    return True


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _write_audit_log(plan_id: int, failures: list[dict]) -> None:
    """写入迁移失败审计日志。"""
    log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"migration_failed_{plan_id}_{ts}.json"

    import json
    log_path.write_text(
        json.dumps({
            "plan_id": plan_id,
            "timestamp": ts,
            "failures": failures,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_plan_status(plan_id: int) -> dict:
    """查询迁移计划状态。"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM migration_manifest WHERE id = ?", (plan_id,)
    ).fetchone()
    if row is None:
        raise LookupError(f"Plan not found: {plan_id}")
    return dict(row)
