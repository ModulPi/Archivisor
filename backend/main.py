"""
Archivisor — 本地优先文件治理引擎
入口：stdio JSON-RPC 服务
"""
import sys
import json
import time
import threading
import traceback
import multiprocessing
from pathlib import Path

# 确保项目根目录在 sys.path（兼容 python backend/main.py 和 PyInstaller）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# 日志目录（异常时写入 crash 报告）
# ---------------------------------------------------------------------------
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


def write_crash_report(exc: Exception, context: dict | None = None) -> Path:
    """写入崩溃报告到 logs/crash_<timestamp>.json"""
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"crash_{ts}.json"
    report = {
        "timestamp": ts,
        "error": str(exc),
        "traceback": traceback.format_exc(),
        "context": context or {},
    }
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 轻量实现
# ---------------------------------------------------------------------------

def make_response(req_id: int, result: dict | None = None) -> dict:
    return {"id": req_id, "result": result or {}}


def make_error(req_id: int, code: int, message: str) -> dict:
    return {"id": req_id, "error": {"code": code, "message": message}}


# ===========================================================================
# 方法处理函数（按需延迟导入，避免启动时加载所有模块）
# ===========================================================================

# ---- 全局 Worker 引用（迁移时复用）----
_worker_process = None
_task_queue = None
_result_queue = None


def _ensure_worker():
    """延迟创建 Worker 进程（首次迁移时 spawn）。"""
    global _worker_process, _task_queue, _result_queue
    from multiprocessing import Queue
    from backend.worker.io_worker import spawn_worker

    if _worker_process is None or not _worker_process.is_alive():
        _task_queue = Queue()
        _result_queue = Queue()
        _worker_process = spawn_worker(_task_queue, _result_queue)
    return _task_queue, _result_queue


# ---- scan ----

def handle_scan(params: dict) -> dict:
    """
    扫描指定目录。
    params: {"root_path": "C:\\Users\\A\\Desktop"} 或 {"root_path": "Desktop"}
    """
    from backend.core.scanner import scan_and_summarize
    from backend.utils.known_folders import get_known_folder

    root_path = params.get("root_path", "")
    if not root_path:
        return {"error": "Missing required param: root_path"}

    # 尝试解析为已知目录名
    try:
        root_path = str(get_known_folder(root_path))
    except (ValueError, OSError):
        pass  # 不是已知目录名，当做原始路径使用

    return scan_and_summarize(root_path)


# ---- migrate ----

def handle_migrate(params: dict) -> dict:
    """
    迁移操作（多步）。
    params:
      - {"action": "create_plan", "source": "...", "target": "...", "filters": [...]}
      - {"action": "execute", "plan_id": 1}
      - {"action": "commit", "plan_id": 1}
      - {"action": "status", "plan_id": 1}
    """
    from backend.core.migrator import (
        create_migration_plan,
        execute_migration,
        commit_migration,
        get_plan_status,
    )

    action = params.get("action", "")

    if action == "create_plan":
        from backend.utils.known_folders import get_known_folder
        source = params["source"]
        target = params["target"]
        # 解析已知目录名 → 绝对路径
        try:
            source = str(get_known_folder(source))
        except (ValueError, OSError):
            pass
        plan = create_migration_plan(
            source=source,
            target=target,
            filters=params.get("filters"),
        )
        return {"plan": plan}

    elif action == "execute":
        plan_id = params["plan_id"]
        tq, rq = _ensure_worker()
        # 异步执行，不阻塞 RPC 响应
        def _run():
            try:
                execute_migration(plan_id, tq, rq)
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()
        return {"plan_id": plan_id, "started": True, "message": "迁移已开始，请轮询 status 获取进度"}

    elif action == "commit":
        plan_id = params["plan_id"]
        ok = commit_migration(plan_id)
        return {"plan_id": plan_id, "commit_ok": ok}

    elif action == "status":
        plan_id = params["plan_id"]
        status = get_plan_status(plan_id)
        return {"plan": status}

    else:
        raise ValueError(
            f"Unknown migrate action: '{action}'. "
            f"Valid: create_plan, execute, commit, status"
        )


# ---- rollback ----

def handle_rollback(params: dict) -> dict:
    """
    回滚指定迁移。
    params: {"plan_id": 1}
    """
    from backend.core.rollback import rollback_migration

    plan_id = params.get("plan_id")
    if plan_id is None:
        return {"error": "Missing required param: plan_id"}

    return rollback_migration(plan_id)


# ---- query (看板) ----

def handle_query(params: dict) -> dict:
    """
    查询看板数据。
    params: {"type": "dashboard" | "disk_usage" | "top_large" | "unmigrated"}
    """
    qtype = params.get("type", "dashboard")
    limit = params.get("limit", 20)

    if qtype == "disk_usage":
        return {"disks": _query_disk_usage()}

    elif qtype == "top_large":
        return {"files": _query_top_large(limit)}

    elif qtype == "unmigrated":
        return {"unmigrated": _query_unmigrated()}

    elif qtype == "migration_history":
        return {"history": _query_migration_history()}

    elif qtype == "known_folders":
        return {"folders": _query_known_folders()}

    elif qtype == "dashboard":
        return {
            "disks": _query_disk_usage(),
            "top_large_files": _query_top_large(limit),
            "unmigrated": _query_unmigrated(),
        }

    else:
        raise ValueError(f"Unknown query type: '{qtype}'")


def _query_disk_usage() -> list[dict]:
    """查询各磁盘占用及用户数据量。"""
    import psutil

    from backend.core.db import get_connection
    conn = get_connection()

    results = []
    for part in psutil.disk_partitions():
        if "fixed" not in part.opts and "removable" not in part.opts:
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except PermissionError:
            continue

        drive = part.mountpoint.rstrip("\\")
        # 该盘上用户文件总量（已索引的）
        row = conn.execute(
            "SELECT COALESCE(SUM(size), 0) FROM file_metadata WHERE path LIKE ? AND is_active=1",
            (drive + "%",),
        ).fetchone()

        results.append({
            "drive": part.device,
            "mountpoint": drive,
            "total_gb": round(usage.total / (1024 ** 3), 2),
            "used_gb": round(usage.used / (1024 ** 3), 2),
            "free_gb": round(usage.free / (1024 ** 3), 2),
            "indexed_gb": round(row[0] / (1024 ** 3), 2),
        })

    return results


def _query_known_folders() -> dict:
    """返回已知目录名 → 绝对路径映射。"""
    from backend.utils.known_folders import get_known_folder
    folders = {}
    for name in ["Desktop", "Downloads", "Documents", "Pictures", "Music", "Videos"]:
        try:
            folders[name] = str(get_known_folder(name))
        except Exception:
            folders[name] = ""
    # 加中文别名
    name_map = {
        "Desktop": "桌面", "Downloads": "下载", "Documents": "文档",
        "Pictures": "图片", "Music": "音乐", "Videos": "视频",
    }
    for eng, chn in name_map.items():
        if eng in folders:
            folders[chn] = folders[eng]
    return folders


def _query_migration_history() -> list[dict]:
    """查询迁移历史列表。"""
    from backend.core.db import get_connection
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM migration_manifest ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    return [dict(r) for r in rows]


def _query_top_large(limit: int = 20, drives: list[str] | None = None) -> dict:
    """查询每个盘最大的 N 个文件，返回 {drive: [files]}。"""
    from backend.core.db import get_connection
    conn = get_connection()

    if drives is None:
        drives = []
        for part in __import__('psutil').disk_partitions():
            if "fixed" in part.opts or "removable" in part.opts:
                drives.append(part.mountpoint.rstrip("\\"))

    result = {}
    for drive in drives:
        rows = conn.execute(
            """SELECT id, name, path, size FROM file_metadata
               WHERE is_active = 1 AND path LIKE ?
               ORDER BY size DESC LIMIT ?""",
            (drive + "%", limit),
        ).fetchall()
        result[drive] = [
            {"id": r["id"], "name": r["name"], "path": r["path"], "size": r["size"]}
            for r in rows
        ]

    return result


def _query_unmigrated() -> dict:
    """查询未迁移文件汇总（is_active=1 且路径在 C 盘用户目录）。"""
    from backend.core.db import get_connection
    conn = get_connection()

    # C 盘用户目录下的活跃文件
    row = conn.execute(
        """SELECT COUNT(*) AS cnt, COALESCE(SUM(size), 0) AS total_sz
           FROM file_metadata
           WHERE is_active = 1 AND path LIKE 'C:\\Users\\%'"""
    ).fetchone()

    # Top 目录（按文件数量和大小）
    top_dirs = conn.execute(
        """SELECT
               substr(path, 1, length(path) - length(replace(path, '\', ''))) AS depth_hint,
               path
           FROM file_metadata
           WHERE is_active = 1 AND path LIKE 'C:\\Users\\%'
           LIMIT 1"""
    ).fetchall()
    # 简化：直接按扩展名分组统计
    by_ext = conn.execute(
        """SELECT extension, COUNT(*) AS cnt, SUM(size) AS sz
           FROM file_metadata
           WHERE is_active = 1 AND path LIKE 'C:\\Users\\%'
           GROUP BY extension
           ORDER BY sz DESC
           LIMIT 10"""
    ).fetchall()

    return {
        "file_count": row["cnt"],
        "total_size": row["total_sz"],
        "by_extension": [
            {"extension": r["extension"] or "(none)", "count": r["cnt"], "total_size": r["sz"]}
            for r in by_ext
        ],
    }


# ---- heartbeat probe ----

def handle_ping(params: dict) -> dict:
    """心跳探测响应。"""
    return {"pong": True, "time": time.time()}


# ===========================================================================
# 路由表
# ===========================================================================

METHOD_TABLE: dict[str, callable] = {
    "scan": handle_scan,
    "migrate": handle_migrate,
    "rollback": handle_rollback,
    "query": handle_query,
    "ping": handle_ping,
}


# ---------------------------------------------------------------------------
# 心跳线程
# ---------------------------------------------------------------------------

def heartbeat_worker(interval: float = 5.0) -> None:
    """每 interval 秒向 stdout 输出心跳，使前端感知后端存活。"""
    while True:
        time.sleep(interval)
        try:
            sys.stdout.write(json.dumps({"type": "heartbeat"}, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        except Exception:
            break


# ---------------------------------------------------------------------------
# 主循环
# ---------------------------------------------------------------------------

def _shutdown_worker() -> None:
    """优雅关闭 Worker 进程。"""
    global _worker_process, _task_queue
    if _task_queue is not None:
        try:
            _task_queue.put(None, timeout=1)
        except Exception:
            pass
    if _worker_process is not None and _worker_process.is_alive():
        _worker_process.join(timeout=5)
        if _worker_process.is_alive():
            _worker_process.terminate()


def main() -> None:
    """stdio JSON-RPC 主循环。"""

    heartbeat_thread = threading.Thread(target=heartbeat_worker, daemon=True)
    heartbeat_thread.start()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        req_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})

        handler = METHOD_TABLE.get(method)
        if handler is None:
            resp = make_error(req_id, -32601, f"Method not found: {method}")
        else:
            try:
                result = handler(params)
                resp = make_response(req_id, result)
            except Exception as exc:
                path = write_crash_report(exc, {"method": method, "params": params})
                resp = make_error(req_id, -32603, f"Internal error (log: {path.name})")

        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    _shutdown_worker()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
