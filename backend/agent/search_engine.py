"""
混合语义搜索引擎 —— BM25 (FTS5) + Embedding (DeepSeek) 双路召回 → RRF 融合排序。
"""
import json
import math
import os
from pathlib import Path

from backend.core.db import get_connection
from backend.agent.deepseek_client import get_client, get_usage_stats

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
RRF_K = 60  # RRF 平滑参数
BM25_TOP = 50
EMBED_TOP = 50
FUSION_TOP = 10

# DeepSeek Embedding 模型
EMBED_MODEL = "deepseek-chat"  # DeepSeek 暂用 chat 模型做语义改写
# 注: DeepSeek 目前没有独立 embedding API, 改用 LLM 做查询语义改写 + FTS5 多关键词召回


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

def hybrid_search(query: str, limit: int = 10) -> dict:
    """
    混合语义搜索。

    参数:
        query: 用户搜索查询
        limit: 返回结果数

    返回:
        {"results": [...], "method": "hybrid", "bm25_hits": int, "semantic_hits": int}
    """
    if not query or not query.strip():
        return {"results": [], "method": "hybrid", "error": "Empty query"}

    query = query.strip()

    # ---- 路径 1: BM25 关键词匹配 (FTS5) ----
    bm25_results = _bm25_search(query, BM25_TOP)

    # ---- 路径 2: 语义扩展搜索 ----
    semantic_results = _semantic_search(query, EMBED_TOP)

    # ---- 路径 3: RRF 融合排序 ----
    fused = _rrf_fusion(bm25_results, semantic_results, FUSION_TOP)

    # 截取 limit
    fused = fused[:limit]

    return {
        "results": fused,
        "method": "hybrid",
        "bm25_hits": len(bm25_results),
        "semantic_hits": len(semantic_results),
        "total_fused": len(fused),
    }


# ---------------------------------------------------------------------------
# BM25 路径 (FTS5)
# ---------------------------------------------------------------------------

def _bm25_search(query: str, top: int = 50) -> list[dict]:
    """FTS5 关键词搜索。"""
    conn = get_connection()
    # FTS5 MATCH 不支持前缀通配符，使用简单 token 匹配
    try:
        rows = conn.execute(
            """SELECT fm.id, fm.name, fm.path, fm.size, fm.extension, fm.modified_time
               FROM file_fts fts
               JOIN file_metadata fm ON fts.rowid = fm.id
               WHERE file_fts MATCH ? AND fm.is_active = 1
               ORDER BY rank
               LIMIT ?""",
            (query, top),
        ).fetchall()
    except Exception:
        # FTS5 语法错误时（特殊字符等），降级为 LIKE
        like_pattern = f"%{query}%"
        rows = conn.execute(
            """SELECT id, name, path, size, extension, modified_time
               FROM file_metadata
               WHERE is_active = 1 AND (name LIKE ? OR path LIKE ?)
               ORDER BY size DESC
               LIMIT ?""",
            (like_pattern, like_pattern, top),
        ).fetchall()

    return [_row_to_dict(r, "bm25") for r in rows]


# ---------------------------------------------------------------------------
# 语义路径（DeepSeek 查询改写 + 多关键词 FTS5）
# ---------------------------------------------------------------------------

def _semantic_search(query: str, top: int = 50) -> list[dict]:
    """
    语义搜索：用 DeepSeek 将用户查询改写为多个搜索关键词，
    然后用 FTS5 搜索并合并结果。
    """
    client = get_client()
    if not client.is_available():
        return []

    # 调用 DeepSeek 做查询语义改写
    try:
        expanded_terms = _expand_query_with_llm(query, client)
    except Exception:
        return []

    if not expanded_terms:
        return []

    # 用所有扩展词搜索 FTS5
    conn = get_connection()
    seen_ids: set[int] = set()
    results: list[dict] = []

    for term in expanded_terms:
        try:
            rows = conn.execute(
                """SELECT fm.id, fm.name, fm.path, fm.size, fm.extension, fm.modified_time
                   FROM file_fts fts
                   JOIN file_metadata fm ON fts.rowid = fm.id
                   WHERE file_fts MATCH ? AND fm.is_active = 1
                   ORDER BY rank
                   LIMIT ?""",
                (term, top // len(expanded_terms) + 5),
            ).fetchall()
        except Exception:
            continue

        for r in rows:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                results.append(_row_to_dict(r, "semantic"))

    return results[:top]


def _expand_query_with_llm(query: str, client) -> list[str]:
    """
    用 DeepSeek 将自然语言查询改写为多个 FTS5 友好的搜索关键词。
    """
    import httpx

    response = httpx.Client(timeout=15.0).post(
        f"{client.base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {client.api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": client.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是一个文件搜索引擎的查询改写器。将用户的自然语言查询转换为3-5个适合"
                        "文件名关键词搜索的词组，每个词组1-4个词，用英文逗号分隔。\n"
                        "规则：\n"
                        "1. 中英文混合查询要同时保留中英文关键词\n"
                        "2. 用户想找'合同'就输出: 合同,contract,协议\n"
                        "3. 用户想找'照片'就输出: 照片,photo,IMG,image\n"
                        "4. 只输出关键词，不要任何解释"
                    ),
                },
                {"role": "user", "content": query},
            ],
            "temperature": 0.1,
            "max_tokens": 100,
        },
    )
    response.raise_for_status()
    data = response.json()
    content = data["choices"][0]["message"]["content"].strip()

    # 解析逗号分隔的关键词
    terms = [t.strip() for t in content.replace("\n", ",").split(",") if t.strip()]
    return terms[:5]


# ---------------------------------------------------------------------------
# RRF 融合排序
# ---------------------------------------------------------------------------

def _rrf_fusion(
    bm25_results: list[dict],
    semantic_results: list[dict],
    top: int = 10,
) -> list[dict]:
    """Reciprocal Rank Fusion 融合两个召回源的排序结果。"""
    # 构建 id → 条目映射
    id_to_item: dict[int, dict] = {}
    rrf_scores: dict[int, float] = {}

    # BM25 排名分数
    for rank, item in enumerate(bm25_results, 1):
        fid = item["id"]
        id_to_item[fid] = item
        rrf_scores[fid] = rrf_scores.get(fid, 0.0) + 1.0 / (RRF_K + rank)

    # 语义排名分数
    for rank, item in enumerate(semantic_results, 1):
        fid = item["id"]
        if fid not in id_to_item:
            id_to_item[fid] = item
        rrf_scores[fid] = rrf_scores.get(fid, 0.0) + 1.0 / (RRF_K + rank)

    # 按 RRF 分数降序排列
    sorted_ids = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)

    results = []
    for fid in sorted_ids[:top]:
        item = dict(id_to_item[fid])
        item["rrf_score"] = round(rrf_scores[fid], 6)
        # 标记匹配来源
        item["match_source"] = _get_match_source(fid, bm25_results, semantic_results)
        results.append(item)

    return results


def _get_match_source(
    fid: int,
    bm25_results: list[dict],
    semantic_results: list[dict],
) -> str:
    """判断条目来自哪个召回源。"""
    in_bm25 = any(r["id"] == fid for r in bm25_results)
    in_semantic = any(r["id"] == fid for r in semantic_results)
    if in_bm25 and in_semantic:
        return "both"
    elif in_bm25:
        return "bm25"
    elif in_semantic:
        return "semantic"
    return "unknown"


def _row_to_dict(row, source: str = "") -> dict:
    """将 SQLite Row 转换为 dict。"""
    d = dict(row)
    d["match_source"] = source
    return d
