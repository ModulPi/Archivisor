"""
Pydantic 数据模型 —— FileInfo / ScanResult / MigrationManifest / MigrationPlan
"""
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 文件元数据
# ---------------------------------------------------------------------------

class FileInfo(BaseModel):
    """单个文件的元数据（对应 file_metadata 表）。"""
    id: int | None = None
    path: str
    name: str
    extension: str = ""
    size: int = 0
    modified_time: float | None = None
    is_active: bool = True


# ---------------------------------------------------------------------------
# 扫描结果
# ---------------------------------------------------------------------------

class ScanProgress(BaseModel):
    """扫描进度事件（yield 给前端）。"""
    type: str = "scan_progress"
    files_so_far: int
    current_dir: str


class ScanResult(BaseModel):
    """扫描完成汇总。"""
    total_files: int
    total_size: int  # bytes
    duration_sec: float


# ---------------------------------------------------------------------------
# 迁移清单 / Plan
# ---------------------------------------------------------------------------

class MigrationStatus(str, Enum):
    PENDING = "pending"
    COPYING = "copying"
    VERIFIED = "verified"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"


class MigrationManifest(BaseModel):
    """迁移清单记录（对应 migration_manifest 表）。"""
    id: int | None = None
    source_path: str
    target_path: str
    source_renamed_to: str | None = None
    status: MigrationStatus = MigrationStatus.PENDING
    file_count: int = 0
    total_size: int = 0
    created_at: float | None = None
    committed_at: float | None = None


class MigrationOperation(BaseModel):
    """迁移计划中的单个操作步骤。"""
    type: str  # scan | filter | copy | verify | commit_soft_delete
    path: str | None = None
    extensions: list[str] | None = None
    time_range: list[str] | None = None  # ["2025-12-01", "2025-12-31"]
    target_root: str | None = None


class MigrationPlan(BaseModel):
    """迁移计划（Agent 生成，用户确认后提交给执行引擎）。"""
    plan_id: str
    operations: list[MigrationOperation]
    requires_confirmation: bool = True


# ---------------------------------------------------------------------------
# 看板数据
# ---------------------------------------------------------------------------

class DiskUsage(BaseModel):
    """磁盘占用信息。"""
    drive: str
    total_gb: float
    used_gb: float
    free_gb: float
    user_data_gb: float  # 该盘上用户文件总量


class TopLargeFile(BaseModel):
    """大文件 Top N 条目。"""
    id: int
    name: str
    path: str
    size: int  # bytes


class UnmigratedSummary(BaseModel):
    """未迁移文件汇总。"""
    file_count: int
    total_size: int  # bytes
    top_dirs: list[dict]  # [{path, file_count, total_size}, ...]


class DashboardData(BaseModel):
    """看板完整数据。"""
    disk_usages: list[DiskUsage]
    top_large_files: list[TopLargeFile]
    unmigrated: UnmigratedSummary
