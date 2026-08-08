"""
Step 3: 并行生成全部岗位能力图谱
=================================
读取 step2 爬取的招聘数据，调用AI并行生成每个岗位的能力图谱。

用法:
  python -m ai.capability_generation 新能源    # 生成新能源全部岗位能力图谱
  python -m ai.capability_generation 智能制造  # 生成智能制造全部岗位能力图谱
"""
import json
import os
import re
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

MAX_WORKERS = 3  # AI API 并发数（太大可能限流）

PROMPT = """你是职业院校专业建设负责人，同时有多年{job_name}岗位的一线培训和技能考评经验。
你的任务是把企业招聘要求转换成可以直接用于课程设计、实训任务和考核评价的岗位能力图谱。

## 生成标准
1. 只提取招聘要求中有证据支持的内容；没有依据的设备、软件、标准和证书不要补写。
2. 输出 6~12 个核心能力。每个能力应是一个可独立组织课程或实训项目的工作模块，不要把整份工作流程写成一个能力。
3. 能力名称使用“对象 + 工作任务”，例如“数控机床操作”“工件装夹与找正”“加工质量检测”，不要使用“综合能力”“相关技能”“熟悉设备”等空泛名称。
4. 每个能力输出 3~8 个技能点。每个技能点只能描述一个可观察、可考核的动作，不能用“并且、同时、以及”串联多个动作。
5. 技能点必须尽量包含：操作对象、工具/设备/软件、动作和可验证结果。招聘要求没有给出具体数值时，使用“符合图纸、工艺卡或企业规范”，不要虚构精度数值。
6. 按真实工作顺序组织：安全与准备 → 图纸/工艺 → 操作/装配/调试 → 检测 → 故障处理 → 维护与现场管理。没有证据的环节可以省略。
7. 合并同义能力和重复技能；不同设备或工艺只有在招聘要求体现明显差异时才拆开。
8. 技能点不要包含课程名称、学习目标、解释性前缀、序号或“会/熟悉/了解”等不可考核表达。

## 输出格式（只输出 JSON，不要 Markdown 代码块和其他说明）
{{
  "job_name": "{job_name}",
  "abilities": [
    {{
      "name": "能力名称",
      "evidence": "招聘要求中支持该能力的关键词或事实",
      "skills": [
        {{
          "name": "一个可观察的技能点",
          "evidence": "对应的招聘要求关键词",
          "assessment": "建议的可验证结果"
        }}
      ]
    }}
  ]
}}

## 反例
- 能力：“具备较强综合能力”——不可用于课程设计。
- 技能：“会操作设备并完成调试、检测和维护”——包含多个动作，必须拆成多个技能点。
- 技能：“掌握相关软件”——没有对象和可验证结果。

## 招聘要求原文
{requirements_text}

请生成{job_name}岗位的课程开发级能力图谱。"""


def gen_ability(job_name: str, requirements: list[str]) -> dict:
    """为单个岗位生成能力图谱"""
    # 去重+截断，凑满数据喂给AI
    seen = set()
    unique_reqs = []
    for r in requirements:
        if not r or len(r) < 15:
            continue
        key = r[:40]
        if key not in seen:
            seen.add(key)
            unique_reqs.append(r[:300])

    if not unique_reqs:
        return {"job_name": job_name, "abilities_text": "", "n_abilities": 0, "n_skills": 0}

    combined = "\n\n---\n\n".join(
        f"[{i+1}] {r}" for i, r in enumerate(unique_reqs[:100])
    )[:14000]

    prompt = PROMPT.format(job_name=job_name, requirements_text=combined)

    from ai.client import call_assistant

    try:
        text = call_assistant(prompt, temperature=0.3, max_tokens=8192)

        # 同时兼容新版 JSON 和旧版文本格式统计数量
        n_abilities = 0
        n_skills = 0
        try:
            clean_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE | re.DOTALL)
            payload = json.loads(clean_text)
            items = payload.get("abilities", []) if isinstance(payload, dict) else payload
            if isinstance(items, list):
                n_abilities = len(items)
                n_skills = sum(len(item.get("skills", item.get("children", [])) or [])
                               for item in items if isinstance(item, dict))
        except (json.JSONDecodeError, TypeError, AttributeError):
            lines = [l for l in text.split("\n") if "---" in l and len(l) > 20]
            n_abilities = len(lines)
            n_skills = sum(len(l.split("---")[1].split("/")) for l in lines if "---" in l)

        return {
            "job_name": job_name,
            "abilities_text": text,
            "n_abilities": n_abilities,
            "n_skills": n_skills,
        }
    except Exception as e:
        return {"job_name": job_name, "abilities_text": "", "n_abilities": 0, "n_skills": 0, "error": str(e)}


def run(chain_name: str):
    # 读取 step2 的爬取结果
    crawl_file = DATA_DIR / f"{chain_name}_全部岗位_爬取结果.json"
    if not crawl_file.exists():
        print(f"  [错误] 未找到 {crawl_file}")
        print(f"  请先运行: python step2_crawl_jobs.py {chain_name}")
        return

    with open(crawl_file, "r", encoding="utf-8") as f:
        crawl_data = json.load(f)

    jobs_data = crawl_data.get("jobs", {})
    print(f"\n{'='*60}")
    print(f"  Step 3: AI生成 [{chain_name}] 产业链能力图谱")
    print(f"  岗位数: {len(jobs_data)} | AI并发: {MAX_WORKERS}")
    print(f"{'='*60}")

    # 准备任务列表（只处理有数据的岗位）
    tasks = []
    for job_name, job_info in jobs_data.items():
        reqs = [r.get("requirements", "") for r in job_info.get("results", [])]
        reqs = [r for r in reqs if r and len(r) > 10]
        if reqs:
            tasks.append((job_name, reqs))
        else:
            print(f"  [跳过] {job_name}: 无招聘数据")

    if not tasks:
        print("  没有可处理的岗位")
        return

    print(f"  有效岗位: {len(tasks)} (已过滤无数据岗位)\n")

    # 并行调用AI
    all_abilities = {}
    completed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(gen_ability, name, reqs): name
            for name, reqs in tasks
        }

        for future in as_completed(futures):
            job_name = futures[future]
            completed += 1
            try:
                r = future.result()
                all_abilities[job_name] = r

                bar = "|" + "#" * min(r["n_abilities"], 40) + " " * max(0, 40 - r["n_abilities"]) + "|"
                status = f"{r['n_abilities']}项/{r['n_skills']}技能"
                if r.get("error"):
                    status = f"失败: {r['error'][:40]}"
                print(f"  [{completed}/{len(tasks)}] {job_name}: {status} {bar}")
            except Exception as e:
                all_abilities[job_name] = {"job_name": job_name, "abilities_text": "", "n_abilities": 0, "n_skills": 0, "error": str(e)}
                print(f"  [{completed}/{len(tasks)}] {job_name}: 失败 - {e}")

    # 保存：每个岗位单独文件 + 汇总文件
    total_abilities = 0
    total_skills = 0

    for job_name, r in all_abilities.items():
        if r["n_abilities"] > 0:
            total_abilities += r["n_abilities"]
            total_skills += r["n_skills"]

            out_file = OUTPUT_DIR / f"{chain_name}_{job_name}_能力图谱.txt"
            out_file.write_text(
                f"# {chain_name} — {job_name} 能力图谱\n"
                f"# 共 {r['n_abilities']} 项核心能力 / {r['n_skills']} 个技能点\n\n"
                f"{r['abilities_text']}",
                encoding="utf-8"
            )

    # 汇总文件
    summary_file = OUTPUT_DIR / f"{chain_name}_全部能力图谱汇总.txt"
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(f"# {chain_name} 产业链岗位能力图谱汇总\n")
        f.write(f"# {len(all_abilities)} 个岗位 / {total_abilities} 项能力 / {total_skills} 个技能点\n\n")
        for job_name, r in all_abilities.items():
            if r["n_abilities"] > 0:
                f.write(f"## {job_name} ({r['n_abilities']}项/{r['n_skills']}技能)\n\n{r['abilities_text']}\n\n---\n\n")

    # 汇总打印
    print(f"\n{'='*60}")
    print(f"  能力图谱生成完成")
    print(f"{'='*60}")
    for job_name, r in all_abilities.items():
        if r["n_abilities"] > 0:
            print(f"  {job_name}: {r['n_abilities']}项能力/{r['n_skills']}技能")
        else:
            print(f"  {job_name}: 失败 - {r.get('error', '未知')}")
    print(f"\n  汇总: {summary_file}")


if __name__ == "__main__":
    chain = sys.argv[1] if len(sys.argv) > 1 else "智能制造"
    run(chain)
