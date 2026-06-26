"""
关键词规则路由器 —— DeepSeek API 不可用时的降级方案。
基于 intents.json 关键词匹配 + 正则参数提取。
"""
import json
import re
from pathlib import Path
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# 加载意图模板
# ---------------------------------------------------------------------------
_INTENTS_PATH = Path(__file__).resolve().parent / "intents.json"
with open(_INTENTS_PATH, "r", encoding="utf-8") as f:
    INTENT_TEMPLATES: list[dict] = json.load(f)

# ---------------------------------------------------------------------------
# 已知目录名正则
# ---------------------------------------------------------------------------
_KNOWN_FOLDER_PATTERNS = re.compile(
    r"(桌面|下载|文档|图片|音乐|视频|Desktop|Downloads|Documents|Pictures|Music|Videos)"
)

_KNOWN_FOLDER_MAP: dict[str, str] = {
    "桌面": "Desktop",
    "下载": "Downloads",
    "文档": "Documents",
    "图片": "Pictures",
    "音乐": "Music",
    "视频": "Videos",
}

# ---------------------------------------------------------------------------
# 盘符正则
# ---------------------------------------------------------------------------
_DRIVE_PATTERN = re.compile(r"([D-Zd-z])\s*[盘:：]")

# ---------------------------------------------------------------------------
# 扩展名正则
# ---------------------------------------------------------------------------
_EXT_PATTERN = re.compile(
    r"\.?([a-z]{2,4})\s*(?:文件|格式|类型)?",
    re.IGNORECASE,
)
_EXT_ALIASES: dict[str, str] = {
    "pdf": "pdf", "doc": "docx", "docx": "docx",
    "xls": "xlsx", "xlsx": "xlsx", "ppt": "pptx", "pptx": "pptx",
    "txt": "txt", "zip": "zip", "rar": "rar",
    "jpg": "jpg", "jpeg": "jpg", "png": "png", "gif": "gif",
    "mp4": "mp4", "mkv": "mkv", "mp3": "mp3",
    "图片": "jpg,png,gif", "照片": "jpg,png",
    "文档": "pdf,docx,txt", "视频": "mp4,mkv",
    "音乐": "mp3", "压缩包": "zip,rar,7z",
}

# ---------------------------------------------------------------------------
# 时间表达正则
# ---------------------------------------------------------------------------
_TIME_PATTERNS: list[tuple[re.Pattern, callable]] = []


def _register_time_patterns():
    """注册时间表达映射（动态计算，处理相对时间）。"""
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    def _fmt(d: datetime) -> str:
        return d.strftime("%Y-%m-%d")

    _TIME_PATTERNS.clear()

    # 上个月
    if today.month == 1:
        last_month_start = today.replace(year=today.year - 1, month=12, day=1)
    else:
        last_month_start = today.replace(month=today.month - 1, day=1)
    if today.month == 1:
        last_month_end = today.replace(day=1) - timedelta(days=1)
    else:
        last_month_end = today.replace(month=today.month, day=1) - timedelta(days=1)

    _TIME_PATTERNS.append((
        re.compile(r"上个月|上(一|个)月"),
        lambda: [_fmt(last_month_start), _fmt(last_month_end)],
    ))

    # 上周
    last_week_start = today - timedelta(days=today.weekday() + 7)
    last_week_end = last_week_start + timedelta(days=6)
    _TIME_PATTERNS.append((
        re.compile(r"上(?:星|个)?周|上星期|上周"),
        lambda: [_fmt(last_week_start), _fmt(last_week_end)],
    ))

    # 昨天
    _TIME_PATTERNS.append((
        re.compile(r"昨天"),
        lambda: [_fmt(today - timedelta(days=1)), _fmt(today - timedelta(days=1))],
    ))

    # 今天
    _TIME_PATTERNS.append((
        re.compile(r"今天"),
        lambda: [_fmt(today), _fmt(today)],
    ))

    # 最近 N 天
    _TIME_PATTERNS.append((
        re.compile(r"最近\s*(\d+)\s*天"),
        lambda m: [_fmt(today - timedelta(days=int(m.group(1)))), _fmt(today)]
        if m else None,
    ))

    # 今年
    _TIME_PATTERNS.append((
        re.compile(r"今年"),
        lambda: [_fmt(today.replace(month=1, day=1)), _fmt(today)],
    ))

    # 去年
    _TIME_PATTERNS.append((
        re.compile(r"去年"),
        lambda: [_fmt(today.replace(year=today.year - 1, month=1, day=1)),
                  _fmt(today.replace(month=1, day=1) - timedelta(days=1))],
    ))


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

def classify_intent(query: str) -> dict:
    """
    关键词匹配意图分类。
    返回: {"intent": str, "confidence": float, "matched_keywords": [...]}
    """
    best_intent = "clarify"
    best_score = 0
    best_keywords: list[str] = []

    for template in INTENT_TEMPLATES:
        keywords = template.get("keywords", [])
        matched = [kw for kw in keywords if kw in query]
        score = len(matched)

        if score > best_score:
            best_score = score
            best_intent = template["id"]
            best_keywords = matched

    # 归一化置信度
    confidence = min(0.7, best_score / 5.0) if best_score > 0 else 0.0

    return {
        "intent": best_intent,
        "confidence": round(confidence, 2),
        "matched_keywords": best_keywords,
    }


def extract_slots(query: str) -> dict:
    """
    正则提取参数槽位。
    返回: {"source": str|None, "target": str|None, "filter": str|None, "time_range": list|None}
    """
    slots: dict = {
        "source": None,
        "target": None,
        "filter": None,
        "time_range": None,
    }

    # ---- source: 已知目录 ----
    source_match = _KNOWN_FOLDER_PATTERNS.search(query)
    if source_match:
        raw = source_match.group(1)
        slots["source"] = _KNOWN_FOLDER_MAP.get(raw, raw)

    # ---- target: 盘符 ----
    drive_match = _DRIVE_PATTERN.search(query)
    if drive_match:
        slots["target"] = drive_match.group(1).upper() + ":"

    # ---- filter: 扩展名 ----
    ext_match = _EXT_PATTERN.search(query)
    if ext_match:
        ext_raw = ext_match.group(1).lower()
        slots["filter"] = _EXT_ALIASES.get(ext_raw, ext_raw)

    # ---- time_range ----
    _register_time_patterns()
    for pattern, resolver in _TIME_PATTERNS:
        m = pattern.search(query)
        if m:
            try:
                result = resolver(m) if m.groups() else resolver()
            except TypeError:
                result = resolver()
            if result:
                slots["time_range"] = result
            break

    return slots


def route(query: str) -> dict:
    """
    关键词路由：意图分类 + 参数提取，返回合并结果。
    """
    intent_result = classify_intent(query)
    slots = extract_slots(query)

    return {
        "intent": intent_result["intent"],
        "confidence": intent_result["confidence"],
        "matched_keywords": intent_result["matched_keywords"],
        "source": slots["source"],
        "target": slots["target"],
        "filter": slots["filter"],
        "time_range": slots["time_range"],
        "explanation": "",
        "needs_clarification": intent_result["confidence"] < 0.5,
        "clarification_question": None,
    }
