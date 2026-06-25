"""
Junction 管理器 —— 封装 Windows mklink /J 命令。
Junction 是一种目录符号链接，对应用程序透明。
"""
import os
import subprocess
from pathlib import Path


def is_junction(path: str | Path) -> bool:
    """
    检查路径是否为 Junction（目录联接）。
    通过 os.path.islink（Python 3.12+ 在 Windows 上支持）+ 目录判断。
    """
    p = Path(path)
    if not p.exists():
        return False
    # Junction 在 Windows 上被识别为 reparse point + directory
    try:
        is_reparse = bool(p.stat().st_file_attributes & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
        return is_reparse and p.is_dir()
    except OSError:
        return False


def create_junction(source: str, target: str) -> bool:
    """
    在 source 位置创建指向 target 的 Junction。

    参数:
        source: Junction 的创建位置（原目录路径）
        target: Junction 指向的目标（数据实际存储位置）

    返回:
        True 成功

    异常:
        OSError: source 已存在且不是 Junction
        subprocess.CalledProcessError: mklink 命令失败
    """
    source_path = Path(source)
    target_path = Path(target)

    # 前置检查
    if source_path.exists():
        if is_junction(source_path):
            # 已存在 Junction → 删除后重建
            os.rmdir(str(source_path))
        else:
            raise OSError(
                f"Cannot create Junction: '{source}' already exists and is not a Junction. "
                f"Remove it manually or choose a different path."
            )

    # 确保目标目录存在
    target_path.mkdir(parents=True, exist_ok=True)

    # 调用 mklink /J（需要管理员权限或在开发模式下）
    try:
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(source_path), str(target_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, f"mklink /J {source} {target}",
                output=result.stdout, stderr=result.stderr,
            )
        return True
    except subprocess.TimeoutExpired:
        raise OSError(f"mklink /J timed out for '{source}' -> '{target}'")


def remove_junction(junction_path: str) -> bool:
    """
    安全删除 Junction（仅删除链接，不删除目标数据）。

    参数:
        junction_path: Junction 路径

    返回:
        True: 成功删除
        False: 路径不是 Junction，拒绝删除（防止误删真实目录）
    """
    p = Path(junction_path)

    if not p.exists():
        return True  # 已经不存在，幂等

    if not is_junction(p):
        return False  # 不是 Junction，拒绝删除

    # os.rmdir 删除 Junction 时只删链接，不影响目标目录
    os.rmdir(str(p))
    return True


def resolve_junction(path: str | Path) -> str | None:
    """
    如果路径是 Junction，返回其指向的目标路径；否则返回 None。
    """
    p = Path(path)
    if not is_junction(p):
        return None

    try:
        result = subprocess.run(
            ["cmd", "/c", "dir", "/AL", str(p.parent)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # 解析输出: 2026/01/26  10:00    <JUNCTION>     name [D:\target\path]
        for line in result.stdout.splitlines():
            if p.name in line and "[" in line and "]" in line:
                bracket = line[line.index("[") + 1:line.index("]")]
                return bracket
    except Exception:
        pass
    return None
