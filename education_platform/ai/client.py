"""DeepSeek AI 客户端。

DeepSeek 提供 OpenAI 兼容的 Chat Completions 接口，因此岗位生成和能力
图谱生成可以共用这个客户端，不再需要讯飞助手 ID、APPID 或 WebSocket 签名。
"""
import os
from pathlib import Path

from openai import OpenAI


def _load_local_env() -> None:
    """读取 education_platform/.env；系统环境变量优先。"""
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_local_env()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_BASE = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


def _validate_settings() -> None:
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("缺少 AI 环境变量：DEEPSEEK_API_KEY")


def call_assistant(prompt: str, temperature: float = 0.5, max_tokens: int = 4096) -> str:
    """调用 DeepSeek，返回完整回复文本。"""
    _validate_settings()
    client = OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_API_BASE,
        timeout=300.0,
        max_retries=2,
    )

    response = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {
                "role": "system",
                "content": "你是职业教育岗位与能力图谱分析助手。请严格遵守用户要求的输出格式。",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    content = response.choices[0].message.content or ""
    return content.strip()
