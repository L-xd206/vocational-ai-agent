"""
Step 1: AI生成产业链相关岗位清单
=================================
输入：产业链名称（如"智能制造"）
输出：该产业链上主流岗位名称 + 搜索关键词 + 别名

用法：
  python step1_gen_jobs.py 智能制造
  python step1_gen_jobs.py 新能源
  python step1_gen_jobs.py 新能源汽车
"""
import json
import os
import sys
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_DIR.mkdir(exist_ok=True)


def gen_jobs(chain_name: str) -> dict:
    """调用AI生成产业链岗位清单"""
    from ai.client import call_assistant

    prompt = f"""你是职业教育领域的岗位分析专家，专门为职业院校（中职/高职）做课程开发的岗位需求调研。

请列出"{chain_name}"产业链上的**技能型/操作型/技术型岗位**（不是研发工程师，是职校毕业生能胜任的一线技术岗位）。

## 严格约束（职教领域限定）
- [OK] 操作员、技工、维修工、装配工、调试员、质检员、运维技术员
- [NO] 研发工程师、算法工程师、架构师、系统设计师、博士岗、硕士岗
- 学历要求：中专/大专/高职，不是本科/研究生
- 岗位特征：动手操作为主，有明确的技能点和工具设备，能在实训车间教学

## 要求
1. 列出该产业链 10~20 个一线技术岗位
2. 岗位按产业链上下游排序（零部件加工 → 整机装配 → 设备调试 → 运维服务）
3. 每个岗位给出：标准名称、2~4个别名（招聘网站上的不同叫法）、5~10个搜索关键词

## 输出JSON格式（严格，不要其他文字）
{{{{
  "chain": "{chain_name}",
  "jobs": [
    {{{{
      "name": "标准岗位名",
      "aliases": ["别名1", "别名2"],
      "search_keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"]
    }}}}
  ]
}}}}

请输出"{chain_name}"产业链的职教岗位清单："""

    print(f"\n  正在调用AI生成 [{chain_name}] 产业链岗位清单...")
    try:
        content = call_assistant(prompt, temperature=0.5, max_tokens=4096)

        # 提取JSON（可能被```json包裹）
        import re
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
        if match:
            content = match.group(1)
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            content = content[start:end + 1]

        data = json.loads(content)
        return data
    except Exception as e:
        print(f"  AI调用失败: {e}")
        return {}


if __name__ == "__main__":
    chain = sys.argv[1] if len(sys.argv) > 1 else "智能制造"

    print(f"\n  [Step 1] 产业链岗位生成")
    print(f"  产业链: {chain}")

    data = gen_jobs(chain)
    if not data:
        sys.exit(1)

    jobs = data.get("jobs", [])
    print(f"\n  生成 {len(jobs)} 个岗位:\n")
    for i, job in enumerate(jobs, 1):
        name = job.get("name", "?")
        aliases = job.get("aliases", [])
        keywords = job.get("search_keywords", [])
        print(f"  {i}. {name}")
        print(f"     别名: {', '.join(aliases)}")
        print(f"     搜索词({len(keywords)}): {', '.join(keywords[:6])}...")

    # 保存
    out_file = OUTPUT_DIR / f"{chain}_岗位清单.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n  已保存: {out_file}")
