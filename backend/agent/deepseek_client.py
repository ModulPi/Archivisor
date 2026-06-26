"""
DeepSeek API 客户端 —— 意图分类 + 参数提取 + 计划生成（单次调用）。
内置日调用上限(50次)和 .env 配置支持。
"""
import json
import os
import re
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# .env 加载
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv

    _ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"
    if _ENV_FILE.exists():
        load_dotenv(_ENV_FILE)
except ImportError:
    pass  # python-dotenv 未安装时静默跳过


# ---------------------------------------------------------------------------
# Rate Limit
# ---------------------------------------------------------------------------
_daily_count: int = 0
_last_reset_date: str = ""


def _check_rate_limit(daily_limit: int = 50) -> bool:
    """检查日调用上限，跨天自动重置。"""
    global _daily_count, _last_reset_date
    today = datetime.now().strftime("%Y%m%d")
    if today != _last_reset_date:
        _daily_count = 0
        _last_reset_date = today
    return _daily_count < daily_limit


def _increment_count() -> None:
    global _daily_count
    _daily_count += 1


def get_usage_stats() -> dict:
    """返回当前用量统计。"""
    _check_rate_limit()
    return {
        "daily_count": _daily_count,
        "daily_limit": 50,
        "remaining": max(0, 50 - _daily_count),
    }


# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """你是一个 Windows 文件治理 Agent 的规划层。你的任务是从用户的自然语言指令中提取结构化信息。

## 可用操作类型
- move: 移动/归档/整理文件（用户想把文件从某处移到某处）
- search: 搜索/查找文件（用户想找某个文件）
- cleanup: 清理文件/释放空间（用户想删除临时文件、重复文件）
- analyze: 分析/查看概况（用户想了解磁盘占用、文件分布）

## 文件过滤类型
- 按扩展名: pdf, docx, xlsx, pptx, txt, zip, rar, 7z, jpg, png, gif, mp4, mkv, mp3 等
- 按时间: 上个月 / 上周 / 昨天 / 今天 / 最近7天 / 今年 / 去年 / 最近30天
- 按大小: > 100MB / > 1GB 等
- 按来源目录: 桌面(Desktop), 下载(Downloads), 文档(Documents), 图片(Pictures), 音乐(Music), 视频(Videos)

## 输出要求
请输出严格 JSON（不要 markdown 代码块标记）：
{
  "intent": "move|search|cleanup|analyze",
  "confidence": 0.0~1.0,
  "source": "源路径名(如Desktop/Downloads) 或 null",
  "target": "目标盘符(如D:/E:) 或 null",
  "filter": "文件扩展名过滤 或 null (如pdf,docx 多个用逗号分隔)",
  "time_range": ["开始日期","结束日期"] 或 null,
  "explanation": "中文简短解释(1-2句)",
  "needs_clarification": true/false,
  "clarification_question": "如果需要澄清,给用户的中文问题 或 null"
}

## 重要规则
1. 如果用户指令模糊不清,needs_clarification 设为 true,并提供 clarification_question
2. 如果用户没有指定目标盘,对 move 意图默认 target 为 "D:"
3. source 使用英文已知文件夹名(Desktop/Downloads/Documents/Pictures/Music/Videos),不要用中文
4. 时间范围按 YYYY-MM-DD 格式输出
5. 不要编造用户没说过的参数"""


# ---------------------------------------------------------------------------
# DeepSeek Client
# ---------------------------------------------------------------------------

class DeepSeekClient:
    """DeepSeek API 客户端（单例）。"""

    def __init__(self):
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        self.base_url = "https://api.deepseek.com/v1"
        self.model = "deepseek-chat"
        self.timeout = 30.0
        self._available = bool(self.api_key)

    def is_available(self) -> bool:
        """API 是否可用（已配置 key 且未超日限）。"""
        return self._available and _check_rate_limit()

    def classify_and_extract(self, query: str, context: list[dict] | None = None) -> dict:
        """
        调用 DeepSeek 进行意图分类 + 参数提取。

        参数:
            query:   用户自然语言输入
            context: 最近对话历史（环形缓冲区）

        返回:
            {"intent", "confidence", "source", "target", "filter",
             "time_range", "explanation", "needs_clarification",
             "clarification_question"} 或 {"error": "..."}
        """
        if not self.is_available():
            return {"error": "api_unavailable"}

        _increment_count()

        try:
            import httpx
        except ImportError:
            return {"error": "httpx_not_installed"}

        # 构建消息
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # 注入上下文
        if context:
            ctx_text = _format_context(context)
            if ctx_text:
                messages.append({
                    "role": "system",
                    "content": f"## 最近对话历史\n{ctx_text}\n\n请结合上述对话历史理解用户当前指令中的指代关系。",
                })

        messages.append({"role": "user", "content": query})

        try:
            client = httpx.Client(timeout=self.timeout)
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.1,
                    "max_tokens": 1024,
                },
            )
            response.raise_for_status()
            data = response.json()

            content = data["choices"][0]["message"]["content"]
            return _parse_response(content)

        except httpx.TimeoutException:
            return {"error": "connection_failed", "detail": "请求超时"}
        except httpx.ConnectError:
            return {"error": "connection_failed", "detail": "无法连接 DeepSeek API"}
        except httpx.HTTPStatusError as exc:
            return {"error": "api_error", "status": exc.response.status_code}
        except Exception as exc:
            return {"error": "unknown", "detail": str(exc)}


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _format_context(context: list[dict]) -> str:
    """将环形缓冲区格式化为 LLM 可读文本。"""
    lines = []
    for i, turn in enumerate(context, 1):
        lines.append(f"第{i}轮: 用户: \"{turn.get('query', '')}\"")
        if turn.get("intent"):
            lines.append(f"      意图: {turn['intent']}, 参数: {turn.get('slots', {})}")
    return "\n".join(lines)


def _parse_response(content: str) -> dict:
    """解析 DeepSeek 返回的 JSON 内容。"""
    # 去除可能的 markdown 代码块标记
    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        # 尝试从内容中提取 JSON 片段
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            try:
                result = json.loads(match.group())
            except json.JSONDecodeError:
                return {"error": "parse_error", "raw": content[:500]}
        else:
            return {"error": "parse_error", "raw": content[:500]}

    # 规范化字段
    return {
        "intent": result.get("intent", "clarify"),
        "confidence": float(result.get("confidence", 0.5)),
        "source": result.get("source"),
        "target": result.get("target"),
        "filter": result.get("filter"),
        "time_range": result.get("time_range"),
        "explanation": result.get("explanation", ""),
        "needs_clarification": bool(result.get("needs_clarification", False)),
        "clarification_question": result.get("clarification_question"),
    }


# ---------------------------------------------------------------------------
# 模块级单例
# ---------------------------------------------------------------------------
_client: DeepSeekClient | None = None


def get_client() -> DeepSeekClient:
    """获取 DeepSeekClient 单例。"""
    global _client
    if _client is None:
        _client = DeepSeekClient()
    return _client
