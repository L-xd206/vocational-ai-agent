"""将正式岗位能力转化为课程学习任务的 DeepSeek 提示词与调用封装。"""

import json
import re


PROMPT = """你是职业院校课程开发负责人。请把一项正式岗位能力转化为可直接用于课堂实训的学习型任务树，并严格根据提供的教材目录匹配知识点。

## 转化目标
将“岗位能力 → 能力单元 → 知识点/技能点”转化为“课程 → 学习任务（章）→ 学习任务卡（知识点）”。
每个任务卡必须包含任务名称、任务描述、工作情境、分步操作指导、安全要点，以及对应的教材知识点。

## 岗位正式树（必须完整覆盖，节点 ID 不得改写）
{ability_json}

## 可用教材知识库（只能从这里选择教材节点 ID）
{textbook_json}

## 严格规则
1. 输出必须覆盖正式树中的每个能力单元和每个知识点/技能点，且每个 source_unit_id、source_point_id 只能出现一次。
2. 每个能力单元生成一个学习任务；每个知识点/技能点生成一个学习任务卡。
3. textbook_chapter_id 和 textbook_node_id 必须来自给定教材；找不到准确对应内容时填 null，不得杜撰 ID 或教材名称。
4. task_description 说明学生要完成什么；work_scenario 使用真实、合理的企业工作情境；operation_steps 每一步是可执行的动作；safety_points 只写确有必要的安全要求。
5. 课程名应为教学课程名称，不要直接复制岗位能力名称；course_type 只能为 theory、practice、integrated。
6. 不得虚构设备型号、精度数值、标准号或教学资源链接。resource_links 没有可靠信息时输出空数组。
7. 只输出 JSON，不要 Markdown、解释或代码块。

## 输出 JSON 格式
{{
  "course_name": "课程名称",
  "course_type": "integrated",
  "total_hours": 0,
  "credits": 0,
  "matched_content": "本课程与该岗位能力的对应说明",
  "chapters": [
    {{
      "source_unit_id": 1,
      "textbook_chapter_id": 1,
      "name": "学习任务名称",
      "task_description": "任务描述",
      "work_scenario": "工作情境",
      "operation_steps": ["步骤一"],
      "safety_points": ["安全要点"],
      "resource_links": [],
      "knowledge_points": [
        {{
          "source_point_id": 1,
          "textbook_node_id": 1,
          "name": "学习任务卡名称",
          "task_description": "任务描述",
          "work_scenario": "工作情境",
          "operation_steps": ["步骤一"],
          "safety_points": ["安全要点"],
          "resource_links": []
        }}
      ]
    }}
  ]
}}
"""


TEXTBOOK_SELECTION_PROMPT = """你是职业教育教材知识库检索助手。请根据岗位正式能力，从学院教材知识库中选出最适合作为课程转化依据的一本教材。

## 岗位正式能力
{ability_json}

## 学院教材知识库索引
{textbook_index_json}

## 规则
1. 只可返回索引中存在的 textbook_id；无法找到相关教材时返回 null。
2. 以能力单元、知识点/技能点与教材章节/知识点的语义覆盖度为依据，不得仅按课程名称字面相似度选择。
3. 一本教材无法覆盖全部内容时，优先选择覆盖核心操作任务最多的一本；不要返回多个教材。
4. 只输出 JSON，不要解释性文字或 Markdown。

{{"textbook_id": 1, "reason": "简短说明匹配依据"}}
"""


def build_prompt(ability_snapshot: dict, textbook_catalog: dict) -> str:
    return PROMPT.format(
        ability_json=json.dumps(ability_snapshot, ensure_ascii=False, separators=(",", ":")),
        textbook_json=json.dumps(textbook_catalog, ensure_ascii=False, separators=(",", ":")),
    )


def build_textbook_selection_prompt(ability_snapshot: dict, textbook_index: dict) -> str:
    return TEXTBOOK_SELECTION_PROMPT.format(
        ability_json=json.dumps(ability_snapshot, ensure_ascii=False, separators=(",", ":")),
        textbook_index_json=json.dumps(textbook_index, ensure_ascii=False, separators=(",", ":")),
    )


def select_textbook_for_ability(ability_snapshot: dict, textbook_index: dict) -> dict:
    """由 AI 从学院教材知识库中选择最匹配的一本教材。"""
    from ai.client import call_assistant

    text = call_assistant(
        build_textbook_selection_prompt(ability_snapshot, textbook_index),
        temperature=0.1,
        max_tokens=1024,
    )
    clean_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE | re.DOTALL)
    try:
        result = json.loads(clean_text)
    except json.JSONDecodeError as exc:
        raise ValueError("AI 返回的教材匹配结果不是有效 JSON") from exc
    if not isinstance(result, dict):
        raise ValueError("AI 返回的教材匹配结果格式无效")
    return result


def generate_learning_task_tree(ability_snapshot: dict, textbook_catalog: dict) -> dict:
    """调用 AI 并解析其返回的学习任务树。"""
    from ai.client import call_assistant

    text = call_assistant(build_prompt(ability_snapshot, textbook_catalog), temperature=0.2, max_tokens=8192)
    clean_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE | re.DOTALL)
    try:
        result = json.loads(clean_text)
    except json.JSONDecodeError as exc:
        raise ValueError("AI 返回的学习任务不是有效 JSON") from exc
    if not isinstance(result, dict) or not isinstance(result.get("chapters"), list):
        raise ValueError("AI 返回缺少 chapters 学习任务列表")
    return result
