"""
智能清理分析 —— 使用 DeepSeek 评估文件清理安全性并生成清理建议。
"""
import time
import json
from pathlib import Path

from backend.core.db import get_connection
from backend.agent.deepseek_client import get_client, get_usage_stats


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

def analyze_cleanup_candidates(limit: int = 20) -> dict:
    """
    分析候选清理文件并生成建议。

    返回:
        {"candidates": [...], "total_waste_gb": float, "analysis": str}
    """
    # 1. 收集候选文件
    candidates = _collect_candidates(limit)

    if not candidates:
        return {
            "candidates": [],
            "total_waste_gb": 0,
            "analysis": "未发现可清理文件。当前磁盘文件管理良好。",
        }

    total_waste = sum(c["size"] for c in candidates) / (1024 ** 3)

    # 2. 用 DeepSeek 分析清理安全性
    client = get_client()
    if client.is_available():
        try:
            analysis = _llm_analyze_candidates(candidates, total_waste, client)
        except Exception:
            analysis = _rule_based_analysis(candidates, total_waste)
    else:
        analysis = _rule_based_analysis(candidates, total_waste)

    # 3. 组装结果
    cleaned_candidates = []
    for c in candidates:
        cleaned_candidates.append({
            "id": c["id"],
            "name": c["name"],
            "path": c["path"],
            "size": c["size"],
            "size_mb": round(c["size"] / (1024 ** 2), 1),
            "extension": c["extension"],
            "reason": c.get("reason", ""),
            "safe_to_delete": c.get("safe_to_delete", True),
        })

    return {
        "candidates": cleaned_candidates,
        "total_waste_gb": round(total_waste, 2),
        "candidate_count": len(candidates),
        "analysis": analysis,
        "fallback_used": not client.is_available(),
    }


# ---------------------------------------------------------------------------
# 候选文件收集
# ---------------------------------------------------------------------------

def _collect_candidates(limit: int = 20) -> list[dict]:
    """收集清理候选文件：临时文件 + 重复文件 + 长期未修改文件。"""
    conn = get_connection()
    candidates: list[dict] = []
    seen_ids: set[int] = set()

    import os as _os
    temp_dir = _os.environ.get("TEMP", "")

    # 类型 1: 临时文件 (*.tmp, ~$*)
    rows = conn.execute(
        """SELECT id, name, path, size, extension
           FROM file_metadata
           WHERE is_active = 1
             AND (extension = 'tmp' OR name LIKE '~$%')
           ORDER BY size DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    for r in rows:
        if r["id"] not in seen_ids:
            seen_ids.add(r["id"])
            candidates.append({
                "id": r["id"], "name": r["name"], "path": r["path"],
                "size": r["size"], "extension": r["extension"] or "tmp",
                "reason": "临时文件", "safe_to_delete": True,
            })

    # 类型 2: %TEMP% 目录下的大文件
    if temp_dir:
        rows = conn.execute(
            """SELECT id, name, path, size, extension
               FROM file_metadata
               WHERE is_active = 1 AND path LIKE ?
               ORDER BY size DESC
               LIMIT ?""",
            (temp_dir + "%", limit),
        ).fetchall()
        for r in rows:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                candidates.append({
                    "id": r["id"], "name": r["name"], "path": r["path"],
                    "size": r["size"], "extension": r["extension"] or "",
                    "reason": "临时目录文件", "safe_to_delete": True,
                })

    # 类型 3: 重复文件（同 size 分组）
    if len(candidates) < limit:
        dup_rows = conn.execute(
            """SELECT size, COUNT(*) as cnt
               FROM file_metadata
               WHERE is_active = 1 AND size > 1048576
               GROUP BY size HAVING cnt >= 2
               ORDER BY size DESC
               LIMIT 5"""
        ).fetchall()
        for dr in dup_rows:
            files = conn.execute(
                "SELECT id, name, path, size, extension FROM file_metadata WHERE size = ? AND is_active = 1 LIMIT 5",
                (dr["size"],),
            ).fetchall()
            for f in files:
                if f["id"] not in seen_ids and len(candidates) < limit:
                    seen_ids.add(f["id"])
                    candidates.append({
                        "id": f["id"], "name": f["name"], "path": f["path"],
                        "size": f["size"], "extension": f["extension"] or "",
                        "reason": f"重复文件 (同{dr['cnt']}个 {dr['size']/(1024**2):.0f}MB 文件)",
                        "safe_to_delete": False,  # 需用户确认
                    })

    return candidates[:limit]


# ---------------------------------------------------------------------------
# 分析
# ---------------------------------------------------------------------------

def _rule_based_analysis(candidates: list[dict], total_waste_gb: float) -> str:
    """基于规则的分析报告。"""
    if not candidates:
        return "未发现明显可清理文件。"

    by_type: dict[str, int] = {}
    for c in candidates:
        reason = c.get("reason", "其他")
        by_type[reason] = by_type.get(reason, 0) + 1

    lines = [
        f"共发现 {len(candidates)} 个清理候选文件，总计 {total_waste_gb:.2f} GB。\n",
        "分类统计:",
    ]
    for reason, count in by_type.items():
        lines.append(f"  • {reason}: {count} 个文件")

    lines.append(f"\n建议优先清理临时文件和 %TEMP% 目录文件（标记为安全），重复文件请手动确认后删除。")
    return "\n".join(lines)


def _llm_analyze_candidates(
    candidates: list[dict],
    total_waste_gb: float,
    client,
) -> str:
    """使用 DeepSeek 生成智能清理分析。"""
    import httpx

    # 构建文件列表摘要（避免发送完整路径到云端）
    file_summary = []
    for c in candidates[:15]:
        ext = c.get("extension", "")
        size_mb = c["size"] / (1024 ** 2)
        reason = c.get("reason", "")
        file_summary.append(
            f"- {c['name']} ({ext}, {size_mb:.1f}MB, {reason})"
        )

    prompt = f"""你是一个文件清理顾问。以下是 {len(candidates)} 个清理候选文件的分析：

总可清理空间: {total_waste_gb:.2f} GB

候选文件列表:
{chr(10).join(file_summary)}

请用中文简要分析 (2-4句话):
1. 哪些文件可以安全清理？为什么？
2. 哪些文件建议保留或手动确认？
3. 清理后可以释放多少空间？

直接回答，不要用 markdown 格式。"""

    response = httpx.Client(timeout=20.0).post(
        f"{client.base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {client.api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": client.model,
            "messages": [
                {"role": "system", "content": "你是文件清理分析助手，只提供建议不自动执行操作。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 300,
        },
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()
