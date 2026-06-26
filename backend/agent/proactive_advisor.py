"""
主动建议系统 —— 基于行为基线的文件整理提醒。
触发条件：写入量异常 / C盘空间不足 / 单次写入超大 → 24h 冷却期。
"""
import os
import time
import json
from pathlib import Path
from datetime import datetime

from backend.core.db import get_connection
from backend.utils.known_folders import get_known_folder


# ---------------------------------------------------------------------------
# 阈值常量
# ---------------------------------------------------------------------------
DISK_FREE_THRESHOLD_GB = 5       # C 盘剩余 < 5GB 触发
SINGLE_WRITE_THRESHOLD_GB = 2    # 单次新增 > 2GB 触发
STD_DEVIATION_MULTIPLIER = 3.0   # 写入量 > μ + 3σ 触发
COOLDOWN_HOURS = 24              # 同目录冷却时间


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

def check_suggestions() -> dict:
    """
    检查所有触发条件，返回建议列表（可能为空）。

    返回:
        {"suggestions": [...], "checked_at": timestamp}
    """
    suggestions: list[dict] = []

    # 1. C 盘空间检查
    disk_alert = _check_disk_space()
    if disk_alert:
        suggestions.append(disk_alert)

    # 2. 大写入检查
    write_alert = _check_recent_writes()
    if write_alert:
        suggestions.append(write_alert)

    # 3. 行为基线异常检查
    anomaly_alert = _check_behavior_anomaly()
    if anomaly_alert:
        suggestions.append(anomaly_alert)

    return {
        "suggestions": suggestions,
        "checked_at": time.time(),
        "has_suggestions": len(suggestions) > 0,
    }


def update_behavior_stats(directory: str, file_count: int, total_size: int) -> dict:
    """
    更新行为基线统计（扫描或迁移完成后调用）。

    参数:
        directory:   监控目录路径
        file_count:  本次文件数
        total_size:  本次总大小（字节）

    返回:
        {"updated": True, "anomaly": bool, ...}
    """
    conn = get_connection()
    now = time.time()

    existing = conn.execute(
        "SELECT * FROM behavior_stats WHERE directory = ?",
        (directory,),
    ).fetchone()

    if existing:
        new_sample_count = existing["sample_count"] + 1
        # 新写入事件
        new_events = existing["write_events"] + 1
        new_total_size = existing["total_size"] + total_size
        new_file_count = existing["file_count"] + file_count

        # 更新均值与标准差（Welford 在线算法简化版——指数移动平均）
        alpha = 0.1  # 平滑系数
        new_mean = existing["baseline_mean"] * (1 - alpha) + total_size * alpha
        new_std = existing["baseline_std"] * (1 - alpha) + abs(total_size - existing["baseline_mean"]) * alpha * 2

        conn.execute(
            """UPDATE behavior_stats SET
               file_count=?, total_size=?, write_events=?,
               last_write_at=?, baseline_mean=?, baseline_std=?,
               sample_count=?
               WHERE directory=?""",
            (new_file_count, new_total_size, new_events,
             now, new_mean, new_std, new_sample_count,
             directory),
        )
    else:
        conn.execute(
            """INSERT INTO behavior_stats
               (directory, file_count, total_size, write_events, last_write_at,
                baseline_mean, baseline_std, sample_count)
               VALUES (?, ?, ?, 1, ?, ?, ?, 1)""",
            (directory, file_count, total_size, now, float(total_size), 0.0),
        )

    conn.commit()

    # 检查是否异常
    anomaly = _check_single_directory_anomaly(directory)

    return {
        "updated": True,
        "anomaly": anomaly["is_anomaly"],
        "anomaly_detail": anomaly,
    }


# ---------------------------------------------------------------------------
# 私有检测函数
# ---------------------------------------------------------------------------

def _check_disk_space() -> dict | None:
    """检查 C 盘剩余空间。"""
    try:
        import psutil
        usage = psutil.disk_usage("C:\\")
        free_gb = usage.free / (1024 ** 3)
        if free_gb < DISK_FREE_THRESHOLD_GB:
            return {
                "type": "disk_low",
                "title": f"C盘仅剩 {free_gb:.1f} GB",
                "detail": f"C盘剩余空间不足 {DISK_FREE_THRESHOLD_GB} GB，建议整理文件释放空间。",
                "severity": "warning",
                "action": "migrate",
                "action_label": "去迁移文件",
            }
    except Exception:
        pass
    return None


def _check_recent_writes() -> dict | None:
    """检查是否有单次超大写入。"""
    conn = get_connection()
    now = time.time()
    # 最近 1 小时内新增的文件
    cutoff = now - 3600
    row = conn.execute(
        """SELECT COALESCE(SUM(size), 0) AS total_sz, COUNT(*) AS cnt
           FROM file_metadata
           WHERE is_active = 1 AND modified_time > ?""",
        (cutoff,),
    ).fetchone()

    if row and row["total_sz"] > SINGLE_WRITE_THRESHOLD_GB * (1024 ** 3):
        return {
            "type": "large_write",
            "title": f"检测到大量新文件 ({row['cnt']} 个)",
            "detail": f"最近 1 小时新增 {row['total_sz'] / (1024**3):.1f} GB 文件，可能需要整理归类。",
            "severity": "info",
            "action": "scan",
            "action_label": "查看文件",
        }
    return None


def _check_behavior_anomaly() -> dict | None:
    """检查所有监控目录的行为基线异常。"""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM behavior_stats
           WHERE sample_count >= 5 AND baseline_std > 0"""
    ).fetchall()

    now = time.time()
    for row in rows:
        # 冷却检查
        if row["last_suggest_at"] and (now - row["last_suggest_at"]) < COOLDOWN_HOURS * 3600:
            continue

        # 最近一次写入量是否超出 μ + 3σ
        if row["last_write_at"] and (now - row["last_write_at"]) < 3600:
            threshold = row["baseline_mean"] + STD_DEVIATION_MULTIPLIER * row["baseline_std"]
            if row["total_size"] > threshold and row["baseline_mean"] > 0:
                # 记录建议时间
                conn.execute(
                    "UPDATE behavior_stats SET last_suggest_at=? WHERE id=?",
                    (now, row["id"]),
                )
                conn.commit()

                return {
                    "type": "anomaly_write",
                    "title": f"{Path(row['directory']).name} 目录写入量异常",
                    "detail": (
                        f"目录 {row['directory']} 当前数据量 {row['total_size'] / (1024**3):.1f} GB，"
                        f"显著高于历史均值 {row['baseline_mean'] / (1024**3):.2f} GB。"
                        f"建议检查是否有大量文件需要整理。"
                    ),
                    "severity": "info",
                    "action": "migrate",
                    "action_label": "去整理",
                }

    return None


def _check_single_directory_anomaly(directory: str) -> dict:
    """检查单个目录的写入异常。"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM behavior_stats WHERE directory = ? AND sample_count >= 5",
        (directory,),
    ).fetchone()

    if not row:
        return {"is_anomaly": False}

    threshold = row["baseline_mean"] + STD_DEVIATION_MULTIPLIER * row["baseline_std"]
    is_anomaly = row["total_size"] > threshold and row["baseline_mean"] > 0

    return {
        "is_anomaly": is_anomaly,
        "directory": directory,
        "current_size_gb": round(row["total_size"] / (1024 ** 3), 2),
        "baseline_mean_gb": round(row["baseline_mean"] / (1024 ** 3), 2),
        "threshold_gb": round(threshold / (1024 ** 3), 2),
    }
