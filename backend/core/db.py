"""
SQLite 数据库管理 —— 建表、FTS5 虚拟表、连接池（单连接）。
数据库文件：%APPDATA%/Archivisor/data.db
"""
import os
import sqlite3
import threading
from pathlib import Path

# ---------------------------------------------------------------------------
# 数据库路径
# ---------------------------------------------------------------------------
DB_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Archivisor"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "data.db"

# ---------------------------------------------------------------------------
# 连接管理（线程本地，单连接复用）
# ---------------------------------------------------------------------------
_local = threading.local()


def get_connection() -> sqlite3.Connection:
    """获取当前线程的数据库连接（自动创建）。"""
    if not hasattr(_local, "conn") or _local.conn is None:
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA mmap_size=268435456")  # 256MB
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return _local.conn


def close_connection() -> None:
    """关闭当前线程的数据库连接。"""
    if hasattr(_local, "conn") and _local.conn is not None:
        _local.conn.close()
        _local.conn = None


# ---------------------------------------------------------------------------
# 建表 SQL
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
-- 文件元数据表（自增 id 主键，path 仅 UNIQUE）
CREATE TABLE IF NOT EXISTS file_metadata (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    path            TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    extension       TEXT DEFAULT '',
    size            INTEGER DEFAULT 0,
    modified_time   REAL,
    is_active       INTEGER DEFAULT 1   -- 0 = 已迁移/软删除
);

CREATE INDEX IF NOT EXISTS idx_path ON file_metadata (path);
CREATE INDEX IF NOT EXISTS idx_is_active ON file_metadata (is_active);

-- FTS5 全文搜索虚拟表
CREATE VIRTUAL TABLE IF NOT EXISTS file_fts USING fts5(
    name,
    path,
    content=file_metadata,
    content_rowid=id
);

-- FTS5 同步触发器：INSERT
CREATE TRIGGER IF NOT EXISTS file_fts_ai AFTER INSERT ON file_metadata BEGIN
    INSERT INTO file_fts(rowid, name, path) VALUES (new.id, new.name, new.path);
END;

-- FTS5 同步触发器：DELETE
CREATE TRIGGER IF NOT EXISTS file_fts_ad AFTER DELETE ON file_metadata BEGIN
    INSERT INTO file_fts(file_fts, rowid, name, path) VALUES ('delete', old.id, old.name, old.path);
END;

-- FTS5 同步触发器：UPDATE
CREATE TRIGGER IF NOT EXISTS file_fts_au AFTER UPDATE ON file_metadata BEGIN
    INSERT INTO file_fts(file_fts, rowid, name, path) VALUES ('delete', old.id, old.name, old.path);
    INSERT INTO file_fts(rowid, name, path) VALUES (new.id, new.name, new.path);
END;

-- 迁移清单表
CREATE TABLE IF NOT EXISTS migration_manifest (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path         TEXT NOT NULL,
    target_path         TEXT NOT NULL,
    source_renamed_to   TEXT,                        -- 软删除时重命名的路径
    status              TEXT DEFAULT 'pending',      -- pending | copying | verified | committed | rolled_back
    file_count          INTEGER DEFAULT 0,
    total_size          INTEGER DEFAULT 0,
    files_copied        INTEGER DEFAULT 0,           -- 实时进度: 已复制文件数
    created_at          REAL DEFAULT (strftime('%s', 'now')),
    committed_at        REAL
);

CREATE INDEX IF NOT EXISTS idx_manifest_status ON migration_manifest (status);
"""


def init_db() -> None:
    """初始化数据库：建表 + 创建索引 + FTS5 虚拟表。幂等，可重复调用。"""
    conn = get_connection()
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def optimize_db() -> None:
    """数据库维护：重建 FTS5 索引 + 分析统计信息。"""
    conn = get_connection()
    conn.execute("INSERT INTO file_fts(file_fts) VALUES ('optimize')")
    conn.execute("ANALYZE")
    conn.commit()


# ---------------------------------------------------------------------------
# 模块加载时自动初始化
# ---------------------------------------------------------------------------
init_db()
