"""
回滚引擎 —— 撤销迁移操作（删除 Junction，恢复源目录）。
原子化操作：每一步失败都有降级策略。
"""
import os
import json
from pathlib import Path
from datetime import datetime

from backend.core.db import get_connection
from backend.utils.junction import remove_junction, is_junction, create_junction


def rollback_migration(plan_id: int) -> dict:
    """
    回滚指定迁移计划。

    操作顺序：
      1. 删除 Junction（os.rmdir —— 只删链接，不删目标数据）
      2. 将 source_renamed_to 重命名回原始路径
      3. 状态标记 rolled_back

    错误处理：
      - 若 Junction 已不存在 → 跳过
      - 若目标盘数据已被用户手动删除 → 跳过恢复，仅重建 Junction
      - 若 source_renamed_to 已不存在 → 跳过恢复

    返回:
        {"plan_id": int, "status": "rolled_back", "warnings": [...]}
    """
    conn = get_connection()
    manifest = conn.execute(
        "SELECT * FROM migration_manifest WHERE id = ?", (plan_id,)
    ).fetchone()

    if manifest is None:
        raise LookupError(f"Migration plan not found: plan_id={plan_id}")

    if manifest["status"] == "rolled_back":
        return {"plan_id": plan_id, "status": "rolled_back", "warnings": ["Already rolled back"]}

    if manifest["status"] not in ("committed", "verified"):
        raise RuntimeError(
            f"Cannot rollback plan {plan_id}: status is '{manifest['status']}'. "
            f"Only 'committed' or 'verified' plans can be rolled back."
        )

    source_path = Path(manifest["source_path"])
    target_path = Path(manifest["target_path"])
    source_renamed_to = (
        Path(manifest["source_renamed_to"])
        if manifest["source_renamed_to"]
        else None
    )

    warnings: list[str] = []
    junction_rebuilt = False

    # -------------------------------------------------------------------
    # Step 1: 删除 Junction（如果存在）
    # -------------------------------------------------------------------
    if source_path.exists() and is_junction(source_path):
        ok = remove_junction(str(source_path))
        if not ok:
            warnings.append(
                f"Failed to remove Junction at '{source_path}'. "
                f"May not be a Junction or permission denied."
            )
    elif source_path.exists() and not is_junction(source_path):
        # 已经是真实目录（可能是之前回滚失败的残留），跳过
        warnings.append(
            f"Path '{source_path}' exists but is not a Junction — skipping removal."
        )
    elif not source_path.exists():
        warnings.append(
            f"Junction '{source_path}' already removed."
        )

    # -------------------------------------------------------------------
    # Step 2: 恢复源目录（从 source_renamed_to 重命名回来）
    # -------------------------------------------------------------------
    if source_renamed_to and source_renamed_to.exists():
        if source_path.exists():
            warnings.append(
                f"Source path '{source_path}' already exists while trying to restore. "
                f"Skipping rename."
            )
        else:
            try:
                os.rename(str(source_renamed_to), str(source_path))
            except OSError as exc:
                warnings.append(f"Failed to rename '{source_renamed_to}' → '{source_path}': {exc}")

    elif source_renamed_to and not source_renamed_to.exists():
        # 软删除目录已被用户手动删除（或 7 天清理）
        warnings.append(
            f"Archived directory '{source_renamed_to}' no longer exists. "
            f"Target data at '{target_path}' remains intact."
        )

        # 若目标数据还在，重建 Junction 恢复透明访问
        target_dir = target_path / source_path.name
        if target_dir.exists() and not source_path.exists():
            try:
                create_junction(str(source_path), str(target_dir))
                junction_rebuilt = True
                warnings.append(
                    f"Junction rebuilt: '{source_path}' → '{target_dir}'"
                )
            except Exception as exc:
                warnings.append(f"Failed to rebuild Junction: {exc}")

    # -------------------------------------------------------------------
    # Step 3: 更新 file_metadata 中的 is_active 标记
    # -------------------------------------------------------------------
    if source_renamed_to:
        conn.execute(
            """UPDATE file_metadata SET is_active=1
               WHERE path LIKE ?""",
            (str(source_renamed_to) + "%",),
        )
    conn.commit()

    # -------------------------------------------------------------------
    # Step 4: 标记 rolled_back
    # -------------------------------------------------------------------
    conn.execute(
        "UPDATE migration_manifest SET status='rolled_back' WHERE id=?",
        (plan_id,),
    )
    conn.commit()

    # 审计日志
    _write_rollback_log(plan_id, warnings, junction_rebuilt)

    return {
        "plan_id": plan_id,
        "status": "rolled_back",
        "junction_rebuilt": junction_rebuilt,
        "warnings": warnings,
    }


def _write_rollback_log(plan_id: int, warnings: list[str], junction_rebuilt: bool) -> None:
    """记录回滚审计日志。"""
    log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"rollback_{plan_id}_{ts}.json"

    log_path.write_text(
        json.dumps({
            "plan_id": plan_id,
            "timestamp": ts,
            "junction_rebuilt": junction_rebuilt,
            "warnings": warnings,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
