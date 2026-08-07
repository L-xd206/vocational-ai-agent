"""
星辰Agent 助手调用工具
使用 WebSocket 协议连接 星辰Agent 平台
"""
import hashlib
import hmac
import base64
import json
import os
import ssl
import time
from datetime import datetime
from time import mktime
from wsgiref.handlers import format_date_time
from urllib.parse import urlencode
from pathlib import Path

import websocket


def _load_local_env() -> None:
    """读取项目根目录的 .env；已有系统环境变量优先。"""
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

# 星辰Agent 配置
SPARK_HOST = os.getenv("SPARK_HOST", "spark-openapi.cn-huabei-1.xf-yun.com")
SPARK_ASSISTANT_ID = os.getenv("SPARK_ASSISTANT_ID", "")
SPARK_API_KEY = os.getenv("SPARK_API_KEY", "")
SPARK_API_SECRET = os.getenv("SPARK_API_SECRET", "")
SPARK_APP_ID = os.getenv("SPARK_APP_ID", "")


def _validate_settings() -> None:
    """在建立连接前校验敏感配置，避免把凭据写入源码。"""
    missing = [name for name, value in {
        "SPARK_ASSISTANT_ID": SPARK_ASSISTANT_ID,
        "SPARK_API_KEY": SPARK_API_KEY,
        "SPARK_API_SECRET": SPARK_API_SECRET,
        "SPARK_APP_ID": SPARK_APP_ID,
    }.items() if not value]
    if missing:
        raise RuntimeError(f"缺少 AI 环境变量：{', '.join(missing)}")


def _build_ws_url() -> str:
    """生成带 HMAC-SHA256 签名的 WebSocket URL"""
    path = f"/v1/assistants/{SPARK_ASSISTANT_ID}"
    now = datetime.now()
    date = format_date_time(mktime(now.timetuple()))

    sig_origin = f"host: {SPARK_HOST}\ndate: {date}\nGET {path} HTTP/1.1"
    sig_sha = hmac.new(
        SPARK_API_SECRET.encode(),
        sig_origin.encode(),
        digestmod=hashlib.sha256,
    ).digest()
    sig_b64 = base64.b64encode(sig_sha).decode()

    auth_origin = (
        f'api_key="{SPARK_API_KEY}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{sig_b64}"'
    )
    auth = base64.b64encode(auth_origin.encode()).decode()

    params = urlencode({"authorization": auth, "date": date, "host": SPARK_HOST})
    return f"wss://{SPARK_HOST}{path}?{params}"


def call_assistant(prompt: str, temperature: float = 0.5, max_tokens: int = 4096) -> str:
    """
    调用星辰Agent，发送 prompt，返回完整回复文本。

    参数:
        prompt: 用户提示词
        temperature: 温度参数
        max_tokens: 最大 token 数

    返回:
        AI 回复的完整文本，失败返回空字符串
    """
    _validate_settings()
    result = {"content": "", "error": None, "done": False}

    def on_open(ws):
        msg = {
            "header": {"app_id": SPARK_APP_ID, "uid": "django_platform"},
            "parameter": {
                "chat": {
                    "domain": "generalv3.5",
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
            },
            "payload": {
                "message": {"text": [{"role": "user", "content": prompt}]}
            },
        }
        ws.send(json.dumps(msg, ensure_ascii=False))

    def on_message(ws, message):
        try:
            data = json.loads(message)
            header = data.get("header", {})
            if header.get("code") != 0:
                result["error"] = header.get("message", "unknown")
                ws.close()
                return
            payload = data.get("payload", {})
            choices = payload.get("choices", {})
            texts = choices.get("text", [])
            for t in texts:
                result["content"] += t.get("content", "")
            if header.get("status") == 2:
                ws.close()
        except Exception:
            pass

    def on_error(ws, error):
        result["error"] = str(error)

    def on_close(ws, code, msg):
        result["done"] = True

    import threading

    ws_url = _build_ws_url()
    ws = websocket.WebSocketApp(
        ws_url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )

    # 在独立线程中运行 WebSocket（防止后台线程阻塞）
    ws_thread = threading.Thread(target=lambda: ws.run_forever(
        sslopt={"cert_reqs": ssl.CERT_NONE},
        # 长文本生成期间服务端可能暂时不能及时响应心跳，5 秒过于激进。
        ping_interval=30,
        ping_timeout=20,
    ))
    ws_thread.daemon = True
    ws_thread.start()

    # 等待完成或超时（最多 5 分钟）
    timeout = 300
    waited = 0
    while not result["done"] and waited < timeout:
        time.sleep(0.5)
        waited += 0.5

    if not result["done"]:
        ws.close()
        result["error"] = "AI调用超时"
        print(f"[Spark Assistant] Timeout after {timeout}s")

    if result["error"]:
        print(f"[Spark Assistant] Error: {result['error']}")
        return ""

    return result["content"].strip()
