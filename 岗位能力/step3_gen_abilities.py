"""
Step 3: 并行生成全部岗位能力图谱
=================================
读取 step2 爬取的招聘数据，调用AI并行生成每个岗位的能力图谱。

用法:
  python step3_gen_abilities.py 新能源    # 生成新能源全部岗位能力图谱
  python step3_gen_abilities.py 智能制造  # 生成智能制造全部岗位能力图谱
"""
import json
import os
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

API_KEY = os.getenv("SPARK_API_KEY") or os.getenv("OPENAI_API_KEY") or "1fdedf8b62e0b4031332ffe418068a55:NmEzYmI5NDRkMzYxMGZmYTMyODMwOWNk"
API_BASE = os.getenv("SPARK_API_BASE", "https://spark-api-open.xf-yun.com/v1")
MODEL = os.getenv("SPARK_MODEL", "generalv3.5")

MAX_WORKERS = 3  # AI API 并发数（太大可能限流）

PROMPT = """你是{job_name}岗位的企业技术培训师，有15年一线带徒和技能考评经验。
请根据下面这些企业真实招聘要求，深度提取该岗位的核心技能清单，用于职业院校课程开发。

## 规则
1. 每行一个能力，格式固定为：能力名---技能1/技能2/技能3/...
2. 每个能力拆解为 5~10 个技能点，技能点越多越好
3. 技能点必须具体到"使用XX工具/设备/软件，完成XX操作，达到XX标准/精度/指标"
4. 从招聘要求原文中提取归纳，不要编造不存在的技能
5. 能力项命名规范：XX操作/XX维修/XX调试/XX识读/XX检测/XX装配/XX运维/XX管理
6. 覆盖该岗位所有细分方向（不同行业/不同设备/不同场景的差异化技能都要体现）
7. 直接输出，不要序号、不要解释、不要分类标签

## 技能点细化标准（每个技能点必须包含三个要素）
- [工具]：使用什么工具/设备/软件
- [操作]：完成什么具体操作
- [标准]：达到什么精度/指标/规范要求

## 正确示例
低压配电系统运维---使用万用表测量三相四线制线路的相电压与线电压偏差不超过±5%/使用钳形电流表在设备满载时测量各相电流不平衡度不超过15%/使用2500V兆欧表测试低压电缆相间及对地绝缘电阻不低于1MΩ/根据回路计算电流选择匹配额定电流1.2~1.5倍的空气开关并完成整定/使用红外热像仪扫描配电柜母排及断路器接线端子温升不超过40K

## 错误示例（太笼统，不合格）
低压配电运维---会测电压/会测电流/会选开关

## 招聘要求原文
{requirements_text}

请输出{job_name}岗位的完整技能清单（15~30项能力，越详细越好）："""


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

    from spark_assistant import call_assistant

    try:
        text = call_assistant(prompt, temperature=0.3, max_tokens=8192)

        # 统计
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
