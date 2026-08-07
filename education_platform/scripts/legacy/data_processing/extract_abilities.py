"""
AI 岗位能力提取 — 本地调用大模型，从招聘数据生成能力图谱
=========================================================
读取爬取的招聘JSON，通过大模型API提取结构化的岗位能力列表。
支持讯飞星火、豆包(火山引擎)、DeepSeek、ChatGPT等。

用法:
  python extract_abilities.py                           # 自动找最新JSON
  python extract_abilities.py data/电工_爬取结果.json    # 指定文件
  python extract_abilities.py 电工 --stats              # 仅统计，不调AI

依赖:
  pip install openai

配置方式一：讯飞星火（免费，推荐）
  set SPARK_API_KEY=1fdedf8b62e0b4031332ffe418068a55
  set SPARK_API_BASE=https://spark-api-open.xf-yun.com/v1
  set SPARK_MODEL=spark-lite

配置方式二：豆包/火山引擎
  set OPENAI_API_KEY=你的Key
  set SPARK_API_BASE=https://ark.cn-beijing.volces.com/api/v3
  set SPARK_MODEL=doubao-pro-32k

配置方式三：DeepSeek
  set OPENAI_API_KEY=sk-xxx
  set SPARK_API_BASE=https://api.deepseek.com/v1
  set SPARK_MODEL=deepseek-chat

配置方式四：ChatGPT / 通义千问 / 其他OpenAI兼容
  set OPENAI_API_KEY=sk-xxx
  set SPARK_API_BASE=https://api.openai.com/v1
  set SPARK_MODEL=gpt-4o-mini
"""
import json
import os
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# API 配置 — 自动从环境变量读取
API_KEY = os.getenv("SPARK_API_KEY", os.getenv("OPENAI_API_KEY", ""))
API_BASE = os.getenv("SPARK_API_BASE", "https://spark-api-open.xf-yun.com/v1")
MODEL = os.getenv("SPARK_MODEL", "generalv3.5")

# ============================================================
#  提示词模板
# ============================================================
EXTRACT_PROMPT = """你是{job_name}岗位的企业技术培训师，有10年以上一线带徒经验。
请根据下面这些企业真实招聘要求，提取该岗位的核心技能清单。

## 规则
1. 每行一个能力，格式固定为：能力名---技能1/技能2/技能3/...
2. 技能点必须具体到"使用什么工具、完成什么操作、达到什么标准"
3. 从招聘要求原文中提取归纳，不要编造
4. 能力项命名规范：XX系统运维/XX设备维修/XX识读/XX调试/XX作业/XX管理
5. 覆盖全面：从招聘要求中找出该岗位所有细分方向的能力（传统方向+新兴方向都要）
6. 直接输出，不要序号、不要解释、不要分类标签

## 正确示例（技能足够具体）
低压配电系统运维---使用万用表测量三相电压不平衡度/使用钳形电流表测量电机额定电流/使用兆欧表测试电缆相间绝缘电阻不低于0.5MΩ/根据负载功率计算并选择匹配的空气开关额定电流
电气图纸识读---识读GB/T 4728标准电气图形符号/根据二次接线图在端子排上完成控制回路接线/根据电气原理图在电控柜内排查断路故障点/读懂PLC I/O分配表并在触摸屏上核对输入输出信号状态
电机控制电路维修---测量电机三相绕组直流电阻判断匝间短路/用摇表测试电机绕组对地绝缘不低于1MΩ/按星三角降压启动原理图在实训板上完成接线并通电验证/用万用表检测交流接触器线圈电阻和主触头通断

## 错误示例（太笼统，不合格）
电工基础---会使用电工工具/懂电路原理/会看图纸
设备维修---维修设备/排除故障/定期保养

## 招聘要求原文
{requirements_text}

请输出{job_name}岗位的技能清单："""


# ============================================================
#  数据加载
# ============================================================
def load_job_data(filepath: str = None) -> tuple[str, list[str]]:
    """加载招聘JSON，返回 (岗位名, requirements列表)"""
    if filepath:
        fp = Path(filepath)
    else:
        # 自动找最新的爬取结果
        json_files = sorted(DATA_DIR.glob("*_爬取结果.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        fp = json_files[0] if json_files else None

    if not fp or not fp.exists():
        print("  未找到数据文件。用法: python extract_abilities.py data/电工_爬取结果.json")
        return "", []

    with open(fp, "r", encoding="utf-8") as f:
        data = json.load(f)

    keyword = data.get("search_keyword", "")
    results = data.get("results", [])

    # 提取所有 requirements 文本
    reqs = []
    for r in results:
        req = r.get("requirements", "")
        if req and len(req) > 10:
            reqs.append(req)

    print(f"  数据文件: {fp.name}")
    print(f"  岗位关键词: {keyword}")
    print(f"  有效招聘条数: {len(reqs)} (共{len(results)}条)")

    return keyword, reqs


# ============================================================
#  AI 提取
# ============================================================
def extract_via_ai(job_name: str, requirements: list[str]) -> str:
    """通过大模型提取能力列表"""
    if not API_KEY or API_KEY == "your-spark-api-key-here":
        print("\n  [警告] 未配置 API Key，使用本地统计模式代替")
        print("  设置方式: set SPARK_API_KEY=your-key")
        return extract_via_stats(job_name, requirements)

    from openai import OpenAI

    client = OpenAI(api_key=API_KEY, base_url=API_BASE)

    # 合并招聘信息（去重后取前100条，每条截200字，凑满约12000字给AI）
    seen = set()
    unique_reqs = []
    for r in requirements:
        key = r[:30]  # 用前30字去重
        if key not in seen:
            seen.add(key)
            unique_reqs.append(r[:200])  # 每条截断到200字

    combined = "\n\n---\n\n".join(
        f"[{i+1}] {r}" for i, r in enumerate(unique_reqs[:100])
    )[:12000]

    prompt = EXTRACT_PROMPT.format(
        job_name=job_name,
        requirements_text=combined,
    )

    print(f"\n  去重后: {len(unique_reqs[:100])} 条招聘信息")
    print(f"  发送字数: {len(prompt)} 字")
    print(f"  模型: {MODEL}")
    print(f"  正在调用AI...")

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "你是一个精确的职业教育课程设计专家。你只输出格式化的能力列表，每行格式为：岗位能力---技能点1/技能点2/...，不输出任何解释、序号、或其他内容。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=4096,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"  AI调用失败: {e}")
        print("  回退到本地统计模式...")
        return extract_via_stats(job_name, requirements)


# ============================================================
#  本地统计模式（不依赖 AI，基于词频 + 规则）
# ============================================================
SKILL_PATTERNS = {
    "配电系统运维": ["配电", "电路", "线路", "照明", "布线", "接线", "走线", "配电柜", "电箱", "开关"],
    "设备电气维修": ["维修", "故障", "检修", "排除", "保养", "调试", "机修", "修理", "抢修"],
    "电工安全规范": ["安全", "规范", "规程", "操作票", "6S", "防护", "接地", "漏电", "绝缘"],
    "仪表与测量": ["万用表", "钳形表", "兆欧表", "测量", "检测", "测试", "摇表", "仪表", "仪器"],
    "电机与控制": ["电机", "电动机", "变频", "PLC", "控制柜", "启动", "正反转", "星三角"],
    "电气图纸识读": ["图纸", "电路图", "接线图", "CAD", "识图", "看图", "电气图"],
    "高低压操作": ["高压", "低压", "变压器", "变电站", "高压柜", "停送电", "倒闸"],
    "智能楼宇弱电": ["弱电", "监控", "门禁", "消防", "报警", "楼宇", "安防", "综合布线", "网络"],
    "空调制冷": ["空调", "制冷", "暖通", "中央空调", "冷柜", "压缩机", "冷凝"],
    "工具与仪表使用": ["电钻", "电锤", "压线钳", "剥线钳", "电烙铁", "热风枪", "角磨机"],
}

def extract_via_stats(job_name: str, requirements: list[str]) -> str:
    """基于关键词匹配的本地提取（不依赖AI）"""
    all_text = " ".join(requirements)

    lines = []
    for ability, keywords in SKILL_PATTERNS.items():
        matched_skills = set()
        for kw in keywords:
            if kw in all_text:
                matched_skills.add(kw)

        if len(matched_skills) >= 2:  # 至少匹配2个关键词才算有效能力
            lines.append(f"{ability}---{'/'.join(sorted(matched_skills))}")

    # 按匹配数排序，多的在前
    lines.sort(key=lambda x: -len(x.split("---")[1].split("/")))

    return "\n".join(lines) if lines else "  未匹配到能力项，请配置API Key使用AI模式"


# ============================================================
#  统计模式
# ============================================================
def show_stats(job_name: str, requirements: list[str]):
    """展示招聘数据中的高频关键词统计"""
    all_text = " ".join(requirements)

    print(f"\n  [{job_name}] 招聘要求高频词:")
    all_keywords = []
    for ability, keywords in SKILL_PATTERNS.items():
        count = sum(all_text.count(kw) for kw in keywords)
        if count > 0:
            all_keywords.append((ability, count))

    for ability, count in sorted(all_keywords, key=lambda x: -x[1]):
        bar = "█" * (count // 5)
        print(f"    {ability}: {count}次 {bar}")

    # 薪资分布
    print(f"\n  薪资分布 (基于招聘信息文字):")
    salary_keywords = ["低压", "高压", "PLC", "变频", "空调", "维修", "安装", "值班"]
    for kw in salary_keywords:
        cnt = all_text.count(kw)
        if cnt > 0:
            print(f'    含[{kw}]: {cnt}条')


# ============================================================
#  入口
# ============================================================
if __name__ == "__main__":
    filepath = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else None
    show_stats_only = "--stats" in sys.argv

    print(f"\n  [AI岗位能力提取]\n")

    job_name, requirements = load_job_data(filepath)

    if not requirements:
        sys.exit(1)

    if show_stats_only:
        show_stats(job_name, requirements)
        sys.exit(0)

    # AI 提取
    result = extract_via_ai(job_name, requirements)

    # 保存结果
    out_file = OUTPUT_DIR / f"{job_name}_能力图谱.txt"

    # 统计能力项和技能点
    lines = [l.strip() for l in result.split("\n") if "---" in l and l.strip()]
    total_abilities = len(lines)
    total_skills = sum(len(l.split("---")[1].split("/")) if "---" in l else 0 for l in lines)

    output = f"# {job_name}岗位能力图谱\n"
    output += f"# 数据来源：中国公共招聘网 → AI深度提取\n"
    output += f"# 共 {total_abilities} 项核心能力 / {total_skills} 个技能点\n\n"
    output += result

    with open(out_file, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"\n{'='*60}")
    print(f"  提取完成: {total_abilities} 项能力 / {total_skills} 个技能点")
    print(f"{'='*60}")
    for line in lines[:5]:
        name = line.split("---")[0] if "---" in line else line[:30]
        skills = line.split("---")[1] if "---" in line else ""
        count = len(skills.split("/")) if skills else 0
        bar = "█" * min(count, 20)
        print(f"  {name} ({count}技能) {bar}")
    if len(lines) > 5:
        print(f"  ... 共 {total_abilities} 项")
    print(f"\n  已保存: {out_file}")
