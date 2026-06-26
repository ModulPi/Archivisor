"""
Agent 计划安全校验 —— 所有 Agent 生成的 Plan 必经此关。
"""
from pathlib import Path

from backend.utils.security import is_safe_path
from backend.utils.known_folders import get_known_folder


def validate_plan(plan: dict) -> dict:
    """
    校验 Agent Plan 中的所有路径是否安全。

    参数:
        plan: Agent 生成的 Plan dict，含 source_path / target_path

    返回:
        {"valid": True} 或
        {"valid": False, "forbidden_paths": [...], "error": "..."}
    """
    forbidden: list[str] = []

    for key in ("source_path", "target_path"):
        path = plan.get(key)
        if not path:
            continue
        # 规范化路径
        try:
            normalized = str(Path(path).resolve())
        except (OSError, ValueError):
            forbidden.append(f"{key}: {path} (无法解析)")
            continue

        if not is_safe_path(normalized):
            forbidden.append(f"{key}: {normalized}")

    if forbidden:
        return {
            "valid": False,
            "forbidden_paths": forbidden,
            "error": f"安全校验失败：以下路径在系统保护区域，操作已拒绝。\n" +
                     "\n".join(f"  • {p}" for p in forbidden),
        }

    return {"valid": True}


def sanitize_path(path: str) -> str:
    """
    清洗路径：统一分隔符、去尾部斜杠、移除 .. 遍历。
    """
    p = str(path).replace("/", "\\").rstrip("\\")
    # 拒绝含 .. 的路径穿越
    if ".." in p:
        raise ValueError(f"Path traversal detected: {path}")
    return p
