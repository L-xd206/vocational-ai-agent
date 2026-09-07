"""面向学生个性化学习计划的 DeepSeek 提示词与调用封装。

提供两类能力：
1. 学习计划 AI 推荐：根据学生专业/年级/已学课程，推荐应补强的课程并说明理由。
2. 薄弱项 AI 分析：根据学生测评的错题分布，定位薄弱知识点并给补强建议。

注意：AI 密钥（DEEPSEEK_API_KEY）来自 ai/client.py 读取的 .env；未配置时调用方应降级到规则推荐，而不是让页面报错。
"""
import json
import re


WEAK_PROMPT = """你是职业院校学情诊断助手。请根据学生最近一次测评的答题情况，分析其薄弱知识点并给出补强建议。

## 学生测评错题分布（按知识点聚合）
{stats_json}

## 严格规则
1. 只分析题面给出的知识点；正确率 < 70% 的视为薄弱项，按缺口从大到小排序。
2. 对每个薄弱项给出简短、可执行的补强建议（回看哪些内容、做什么练习）。
3. 若没有正确率 < 70% 的知识点，输出空 recommendations。
4. 只输出 JSON，不要 Markdown、解释或代码块。

## 输出 JSON 格式
{{
  "summary": "整体学情判断一句话",
  "weak_points": [
    {{"node_name": "知识点名", "mastery": 55, "suggestion": "补强建议"}}
  ]
}}
"""


def build_weak_prompt(stats: list) -> str:
    return WEAK_PROMPT.format(stats_json=json.dumps(stats, ensure_ascii=False))


def _parse(text: str, kind: str) -> dict:
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE | re.DOTALL)
    try:
        result = json.loads(clean)
    except json.JSONDecodeError as exc:
        raise ValueError(f"AI 返回的{kind}不是有效 JSON") from exc
    if not isinstance(result, dict):
        raise ValueError(f"AI 返回的{kind}格式无效")
    return result


def analyze_weakness(stats: list) -> dict:
    """AI 分析测评薄弱知识点。未配置密钥时抛 RuntimeError，调用方应降级。"""
    from ai.client import call_assistant

    text = call_assistant(build_weak_prompt(stats), temperature=0.2, max_tokens=1536)
    return _parse(text, "薄弱项分析")


CHAT_MATCH_PROMPT = """你是职业院校学习规划助手。请根据学生与助手的对话，从「课程库」中挑选匹配的学习课程。

## 对话内容
{chat_text}

## 课程库（只能从这里选，course_id 不得改写）
{catalog_json}

## 严格规则
1. 只能从课程库中挑选，最多 3 门，按相关度排序。
2. 结合对话中提到的方向（机器人/PLC/数控/视觉/伺服等）匹配课程。
3. 只输出 JSON，不要 Markdown、解释或代码块。

## 输出 JSON 格式
{{
  "courses": [{{"course_id": 1, "course_name": "课程名"}}]
}}
"""


def match_courses_from_chat(chat_text: str, catalog: list) -> dict:
    """AI 根据对话匹配课程。未配置密钥时抛 RuntimeError，调用方应降级。"""
    from ai.client import call_assistant

    catalog_json = json.dumps(
        [{"course_id": t.id, "course_name": t.name} for t in catalog],
        ensure_ascii=False,
    )
    prompt = CHAT_MATCH_PROMPT.format(chat_text=chat_text or "", catalog_json=catalog_json)
    text = call_assistant(prompt, temperature=0.3, max_tokens=1024)
    result = _parse(text, "课程匹配")
    return {"source": "ai", "courses": result.get("courses", [])}
