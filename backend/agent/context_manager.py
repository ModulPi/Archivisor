"""
上下文管理器 —— 环形缓冲区，支持多轮对话指代消解。
进程退出即清空，无持久化。
"""
import re
from collections import deque

# ---------------------------------------------------------------------------
# 环形缓冲区（最近 3 轮）
# ---------------------------------------------------------------------------
_buffer: deque[dict] = deque(maxlen=3)

# 指代词模式
_REFERENCE_PATTERNS = [
    re.compile(r"这些"),
    re.compile(r"它们?"),
    re.compile(r"那个|那些"),
    re.compile(r"把(它|这些|那些)"),
    re.compile(r"上面(的|这些)?"),
]


def add_turn(query: str, result: dict) -> None:
    """记录一轮对话。"""
    _buffer.append({
        "query": query,
        "intent": result.get("intent"),
        "slots": {
            "source": result.get("source"),
            "target": result.get("target"),
            "filter": result.get("filter"),
            "time_range": result.get("time_range"),
        },
        "results": result.get("results", []),
    })


def get_context() -> list[dict]:
    """返回最近对话历史（用于注入 LLM prompt）。"""
    return list(_buffer)


def resolve_references(query: str) -> dict | None:
    """
    检测指代词，返回上一轮的 slots 作为引用解析。
    返回 None 表示未检测到指代。
    """
    has_reference = any(p.search(query) for p in _REFERENCE_PATTERNS)
    if not has_reference or len(_buffer) == 0:
        return None
    return _buffer[-1]["slots"]


def clear() -> None:
    """清空上下文缓冲区。"""
    _buffer.clear()


def get_last_turn() -> dict | None:
    """获取最近一轮对话。"""
    return _buffer[-1] if _buffer else None
