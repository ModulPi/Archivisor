"""
路径安全校验 —— 白名单/黑名单，防止误触系统目录。
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# 白名单：允许扫描的用户目录（相对于用户主目录）
# ---------------------------------------------------------------------------
ALLOWED_ROOTS: list[str] = [
    "Desktop",
    "Downloads",
    "Documents",
    "Pictures",
    "Music",
    "Videos",
]

# ---------------------------------------------------------------------------
# 黑名单：绝对禁止触碰的系统路径前缀
# ---------------------------------------------------------------------------
FORBIDDEN_PREFIXES: list[str] = [
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    "C:\\System Volume Information",
    "C:\\$Recycle.Bin",
]


def is_safe_path(path: str | Path) -> bool:
    """检查路径是否安全（不在禁止前缀中）。返回 True 表示安全。"""
    p = str(path).rstrip("\\").replace("/", "\\")
    for forbidden in FORBIDDEN_PREFIXES:
        fp = forbidden.rstrip("\\")
        # 精确匹配或前缀匹配（以 \\ 为边界）
        if p == fp or p.startswith(fp + "\\"):
            return False
    return True


def is_allowed_root(rel_path: str) -> bool:
    """检查相对路径是否在允许的根目录列表中。"""
    normalized = rel_path.strip("\\").replace("/", "\\")
    # 取第一级目录名
    first_part = normalized.split("\\")[0] if "\\" in normalized else normalized
    return first_part in ALLOWED_ROOTS


def get_forbidden_error(path: str) -> str:
    """生成禁止路径的错误消息。"""
    return f"Access denied: path '{path}' is in the system-protected zone. Operation refused."
