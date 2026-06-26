"""
计划生成器 —— Agent 层编排入口。
整合：上下文管理 → 意图分类 → 参数提取 → 计划组装 → 安全校验。
"""
import time
import json
from datetime import datetime
from pathlib import Path

from backend.agent.context_manager import (
    resolve_references,
    get_context,
    add_turn,
)
from backend.agent.deepseek_client import get_client, get_usage_stats
from backend.agent.keyword_router import route as keyword_route
from backend.agent.security_validator import validate_plan, sanitize_path
from backend.utils.known_folders import get_known_folder


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def process_query(query: str) -> dict:
    """
    处理用户自然语言输入，返回 AgentResponse dict。

    参数:
        query: 用户自然语言字符串

    返回:
        AgentResponse 兼容 dict
    """
    # 1. 空输入检查
    if not query or not query.strip():
        return {
            "success": False,
            "error": "请输入指令，例如："把下载文件夹的PDF移到D盘"",
        }

    query = query.strip()

    # 2. 上下文引用解析
    ref_slots = resolve_references(query)
    if ref_slots:
        # 将上一轮的 slots 附加到 query 末尾，帮助后续模块理解
        ref_hints = []
        if ref_slots.get("source"):
            ref_hints.append(f"源目录: {ref_slots['source']}")
        if ref_slots.get("filter"):
            ref_hints.append(f"文件类型: {ref_slots['filter']}")
        if ref_hints:
            query = f"{query}\n[上下文: {'; '.join(ref_hints)}]"

    # 3. 主路径：DeepSeek API
    client = get_client()
    fallback_used = False
    result = None

    if client.is_available():
        result = client.classify_and_extract(query, get_context())

    if result is None or "error" in result:
        # 4. 降级路径：关键词规则
        result = keyword_route(query)
        fallback_used = True

    # 5. 澄清检查
    if result.get("needs_clarification"):
        return _build_clarify_response(result, fallback_used)

    intent = result.get("intent", "clarify")
    confidence = result.get("confidence", 0.0)

    # 置信度过低 → 澄清
    threshold = 0.7 if not fallback_used else 0.5
    if confidence < threshold and intent != "clarify":
        return _build_clarify_response(result, fallback_used)

    # 6. 意图分发 → 构建 Plan
    if intent == "move":
        response = _build_move_response(result, fallback_used)
    elif intent == "search":
        response = _build_search_response(result, fallback_used)
    elif intent == "cleanup":
        response = _build_cleanup_response(result, fallback_used)
    elif intent == "analyze":
        response = _build_analyze_response(result, fallback_used)
    else:
        return _build_clarify_response(result, fallback_used)

    # 7. 安全校验（对 move 类型必须做）
    if intent == "move" and response.get("plan"):
        plan = response["plan"]
        safety = validate_plan(plan)
        if not safety["valid"]:
            return {
                "success": False,
                "error": safety["error"],
                "intent": intent,
                "confidence": confidence,
                "fallback_used": fallback_used,
            }

    # 8. 记录上下文
    add_turn(query, {
        "intent": intent,
        "source": result.get("source"),
        "target": result.get("target"),
        "filter": result.get("filter"),
        "time_range": result.get("time_range"),
        "results": response.get("results", []),
    })

    return response


# ---------------------------------------------------------------------------
# 各意图 Plan 构建
# ---------------------------------------------------------------------------

def _build_move_response(result: dict, fallback_used: bool) -> dict:
    """构建移动/归档计划。"""
    source = result.get("source") or ""
    target = result.get("target") or "D:"
    file_filter = result.get("filter") or ""
    time_range = result.get("time_range")

    # 解析源路径
    try:
        source_path = str(get_known_folder(source)) if source else ""
    except (ValueError, OSError):
        source_path = source

    # 解析目标路径
    target_path = target.rstrip(":\\/")
    if len(target_path) == 1:
        target_path = target_path + ":"
    target_dir = f"{target_path}\\ArchivisorArchive"
    if source:
        target_dir = f"{target_dir}\\{source}"

    # 组装 operations
    operations: list[dict] = []
    if source_path:
        operations.append({"type": "scan", "path": source_path})
    else:
        operations.append({"type": "scan", "path": None})

    extensions = [f.strip() for f in file_filter.split(",") if f.strip()] if file_filter else None
    operations.append({
        "type": "filter",
        "extensions": extensions,
        "time_range": time_range,
        "path": None,
        "target_root": None,
    })
    operations.append({
        "type": "copy",
        "extensions": None,
        "time_range": None,
        "path": None,
        "target_root": target_dir,
    })
    operations.append({
        "type": "verify",
        "extensions": None,
        "time_range": None,
        "path": None,
        "target_root": None,
    })
    operations.append({
        "type": "commit_soft_delete",
        "extensions": None,
        "time_range": None,
        "path": None,
        "target_root": None,
    })

    plan_id = f"agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{int(time.time() * 1000) % 1000:03d}"

    # 构建解释
    parts = []
    parts.append(result.get("explanation", ""))
    if fallback_used:
        parts.append("(离线模式)")

    return {
        "success": True,
        "intent": "move",
        "confidence": result.get("confidence", 0.0),
        "plan": {
            "plan_id": plan_id,
            "intent": "move",
            "operations": operations,
            "source_path": source_path or None,
            "target_path": target_dir,
            "estimated_file_count": None,
            "estimated_size": None,
            "requires_confirmation": True,
            "explanation": " ".join(parts).strip(),
        },
        "fallback_used": fallback_used,
    }


def _build_search_response(result: dict, fallback_used: bool) -> dict:
    """构建搜索计划。"""
    file_filter = result.get("filter") or ""
    source = result.get("source") or ""

    params: dict = {"keyword": file_filter}
    if source:
        params["source"] = source

    return {
        "success": True,
        "intent": "search",
        "confidence": result.get("confidence", 0.0),
        "plan": {
            "plan_id": f"agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "intent": "search",
            "operations": [{
                "type": "search",
                "extensions": [file_filter] if file_filter else None,
                "time_range": result.get("time_range"),
                "path": source or None,
                "target_root": None,
            }],
            "source_path": None,
            "target_path": None,
            "estimated_file_count": None,
            "estimated_size": None,
            "requires_confirmation": False,
            "explanation": result.get("explanation", f"搜索 {file_filter or '全部'} 文件"),
        },
        "fallback_used": fallback_used,
    }


def _build_cleanup_response(result: dict, fallback_used: bool) -> dict:
    """构建清理计划。"""
    return {
        "success": True,
        "intent": "cleanup",
        "confidence": result.get("confidence", 0.0),
        "plan": {
            "plan_id": f"agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "intent": "cleanup",
            "operations": [
                {"type": "find_duplicates", "extensions": None, "time_range": None, "path": None, "target_root": None},
                {"type": "find_temp_files", "extensions": None, "time_range": None, "path": None, "target_root": None},
            ],
            "source_path": None,
            "target_path": None,
            "estimated_file_count": None,
            "estimated_size": None,
            "requires_confirmation": True,
            "explanation": result.get("explanation", "扫描重复文件和临时文件，估算可释放空间"),
        },
        "fallback_used": fallback_used,
    }


def _build_analyze_response(result: dict, fallback_used: bool) -> dict:
    """构建分析/查看计划。"""
    return {
        "success": True,
        "intent": "analyze",
        "confidence": result.get("confidence", 0.0),
        "plan": {
            "plan_id": f"agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "intent": "analyze",
            "operations": [{
                "type": "dashboard",
                "extensions": None,
                "time_range": None,
                "path": None,
                "target_root": None,
            }],
            "source_path": None,
            "target_path": None,
            "estimated_file_count": None,
            "estimated_size": None,
            "requires_confirmation": False,
            "explanation": result.get("explanation", "查看磁盘占用和文件分布概况"),
        },
        "fallback_used": fallback_used,
    }


def _build_clarify_response(result: dict, fallback_used: bool) -> dict:
    """构建澄清响应。"""
    clarification = result.get("clarification_question") or "抱歉，我不太确定您的意图。您是想：\nA. 移动/整理文件\nB. 搜索文件\nC. 清理释放空间\nD. 查看磁盘概况"
    return {
        "success": True,
        "intent": "clarify",
        "confidence": result.get("confidence", 0.0),
        "clarification": clarification,
        "fallback_used": fallback_used,
    }


# ---------------------------------------------------------------------------
# 上下文管理（对外暴露）
# ---------------------------------------------------------------------------

def get_conversation_context() -> list[dict]:
    """获取对话上下文（供 UI 查询）。"""
    return get_context()


def clear_context() -> None:
    """清空对话上下文。"""
    from backend.agent.context_manager import clear
    clear()
