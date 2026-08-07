"""
产业链岗位能力图谱生成流水线
============================
解决核心问题：招聘网站岗位名称不规范 → 多关键词搜索 + 合并去重

流程：
  1. 选定产业链 → 加载预定义岗位清单及搜索关键词
  2. 每个岗位用多个关键词分别搜索（覆盖各种叫法）
  3. 合并去重（同一公司+相似标题视为重复）
  4. AI 提取能力图谱

用法:
  python chain_workflow.py 智能制造          # 生成全部岗位能力图谱
  python chain_workflow.py 智能制造 数控操作工 # 仅生成指定岗位
  python chain_workflow.py --list            # 列出所有产业链
"""
import json
import re
import sys
import time
import urllib.request
import urllib.parse
import ssl
from pathlib import Path
from collections import defaultdict

# === 路径 ===
BASE_DIR = Path(__file__).resolve().parent
CHAINS_FILE = BASE_DIR / "chains.json"
OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR.mkdir(exist_ok=True)

# === mohrss 爬取配置 ===
SEARCH_URL = "http://job.mohrss.gov.cn/cjobs/jobinfolist/listJobinfolist"
CRAWL_PAGES_PER_KEYWORD = 3  # 每个关键词爬几页


def load_chains() -> dict:
    with open(CHAINS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_form(keyword: str, page: int) -> bytes:
    return urllib.parse.urlencode({
        "pageNo": str(page), "pagecount": "50", "textfield": keyword,
        "searchtype": "1", "orderType": "score",
        "ACB241": "", "rowid": "", "AAE397": "",
        "aab019_t": "", "aab019": "", "aab020": "", "aab022": "",
        "acb239_t": "", "acb239": "", "acb228_t": "", "acb228": "",
        "aac011_t": "", "aac011": "",
        "totalpages": "", "totalcount": "",
        "zcType": "", "AREA": "", "AREA_name": "",
        "ACA111": "", "ACA111_name": "",
    }).encode("utf-8")


def _parse_results(html: str) -> list[dict]:
    """从mohrss页面解析岗位数据"""
    match = re.search(r'id="findjoblist"[^>]*value="(.*?)"\s+type=', html, re.DOTALL)
    if not match:
        return []
    raw = match.group(1).replace("&#034;", '"').replace("&amp;", "&")
    raw = raw.replace("&lt;", "<").replace("&gt;", ">")
    last = raw.rfind("}]")
    if last > 0:
        raw = raw[:last + 2]

    results = []
    for j in json.loads(raw):
        results.append({
            "title": j.get("aca112", ""),
            "company": j.get("aab004", ""),
            "city": j.get("area_", j.get("aab302", "")),
            "salary": j.get("acb241", ""),
            "education": j.get("aac011", ""),
            "requirements": j.get("acb22a", ""),
            "headcount": j.get("acb240", ""),
            "date": j.get("s_uptime", j.get("aae397", "")),
            "source": j.get("org_", "中国公共招聘网"),
        })
    return results


def _title_similar(a: str, b: str) -> bool:
    """判断两个岗位标题是否指向同一类岗位"""
    # 去掉括号内容和多余空格
    clean = lambda s: re.sub(r"[（(][^)）]*[)）]", "", s).strip()
    a, b = clean(a), clean(b)
    # 如果核心词相同或包含
    if a == b:
        return True
    if len(a) > 3 and len(b) > 3:
        if a[:4] == b[:4]:
            return True
        if a in b or b in a:
            return True
    return False


def crawl_job_multi_keyword(search_keywords: list[str], pages: int = CRAWL_PAGES_PER_KEYWORD) -> list[dict]:
    """用多个关键词搜索同一个岗位，合并去重"""
    ctx = ssl.create_default_context()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "http://job.mohrss.gov.cn/cjobs/jobinfolist/listJobinfolist",
    }

    all_results = []
    seen = set()  # (company, normalized_title) 去重

    for kw in search_keywords:
        kw_results = []
        for page in range(1, pages + 1):
            try:
                req = urllib.request.Request(SEARCH_URL, data=_build_form(kw, page), headers=headers)
                with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
                    html = resp.read().decode("utf-8", errors="replace")
                page_results = _parse_results(html)
                if not page_results:
                    break
                kw_results.extend(page_results)
            except Exception:
                break
            time.sleep(0.5)

        # 去重
        for r in kw_results:
            key = (r["company"], r["title"][:10])
            if key not in seen:
                # 检查与已有结果是否相似
                is_dup = False
                for existing in all_results:
                    if existing["company"] == r["company"] and _title_similar(existing["title"], r["title"]):
                        is_dup = True
                        # 保留更长的 requirements
                        if len(r.get("requirements", "")) > len(existing.get("requirements", "")):
                            existing.update(r)
                        break
                if not is_dup:
                    seen.add(key)
                    all_results.append(r)

        print(f"    关键词 [{kw}]: {len(kw_results)}条 → 去重后新收录 {len([r for r in kw_results if (r['company'], r['title'][:10]) in seen])} 条")

    return all_results


def extract_abilities_ai(job_name: str, requirements: list[str]) -> str:
    """调用AI提取能力图谱（复用extract_abilities的逻辑）"""
    import os
    api_key = os.getenv("SPARK_API_KEY", os.getenv("OPENAI_API_KEY", ""))
    if not api_key:
        return ""

    from openai import OpenAI
    client = OpenAI(
        api_key=api_key,
        base_url=os.getenv("SPARK_API_BASE", "https://spark-api-open.xf-yun.com/v1"),
    )

    # 去重
    seen = set()
    unique_reqs = []
    for r in requirements:
        key = r[:30]
        if key not in seen:
            seen.add(key)
            unique_reqs.append(r[:200])

    combined = "\n\n---\n\n".join(
        f"[{i+1}] {r}" for i, r in enumerate(unique_reqs[:80])
    )[:10000]

    prompt = f"""你是{job_name}岗位的企业技术培训师，有10年以上一线带徒经验。
请根据下面这些企业真实招聘要求，提取该岗位的核心技能清单。

## 规则
1. 每行一个能力，格式固定为：能力名---技能1/技能2/技能3/...
2. 技能点必须具体到"使用什么工具、完成什么操作、达到什么标准"
3. 从招聘要求原文中提取归纳，不要编造
4. 覆盖全面：找出该岗位所有细分方向的能力（传统+新兴）
5. 直接输出，不要序号、不要解释、不要分类标签

## 招聘要求原文
{combined}

请输出{job_name}岗位的技能清单："""

    try:
        resp = client.chat.completions.create(
            model=os.getenv("SPARK_MODEL", "generalv3.5"),
            messages=[
                {"role": "system", "content": "你只输出格式化的能力列表，每行格式：能力名---技能1/技能2/...，不输出任何解释。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3, max_tokens=4096,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"      AI调用失败: {e}")
        return ""


# === 主流程 ===
def run_chain(chain_name: str, target_job: str = None):
    chains = load_chains()
    if chain_name not in chains:
        print(f"  未找到产业链: {chain_name}")
        print(f"  可用: {list(chains.keys())}")
        return

    chain = chains[chain_name]
    jobs = chain["jobs"]

    if target_job:
        if target_job not in jobs:
            print(f"  未找到岗位: {target_job}")
            print(f"  可用: {list(jobs.keys())}")
            return
        jobs = {target_job: jobs[target_job]}

    print(f"\n{'='*60}")
    print(f"  产业链: {chain_name} — {chain['description']}")
    print(f"  岗位数: {len(jobs)}")
    print(f"{'='*60}")

    all_abilities = {}  # {岗位名: 能力图谱文本}

    for i, (job_name, job_config) in enumerate(jobs.items(), 1):
        keywords = job_config.get("search_keywords", [job_name])
        aliases = job_config.get("aliases", [])

        print(f"\n[{i}/{len(jobs)}] {job_name}")
        print(f"  别名: {', '.join(aliases[:5])}")
        print(f"  搜索关键词({len(keywords)}个): {', '.join(keywords[:6])}...")

        # 1. 多关键词爬取
        results = crawl_job_multi_keyword(keywords)

        if not results:
            print(f"  [!] 未爬取到数据，跳过")
            continue

        print(f"  合计: {len(results)} 条有效招聘信息")

        # 2. 提取requirements
        reqs = [r.get("requirements", "") for r in results if r.get("requirements", "") and len(r.get("requirements", "")) > 10]
        reqs = reqs[:200]  # 最多200条

        # 3. 保存原始数据
        data_file = DATA_DIR / f"{chain_name}_{job_name}_爬取结果.json"
        with open(data_file, "w", encoding="utf-8") as f:
            json.dump({
                "chain": chain_name,
                "job_name": job_name,
                "aliases": aliases,
                "total": len(results),
                "keywords_used": keywords,
                "results": results,
            }, f, ensure_ascii=False, indent=2)
        print(f"  原始数据: {data_file}")

        # 4. AI 提取
        print(f"  正在调用AI提取能力图谱...")
        abilities_text = extract_abilities_ai(job_name, reqs)

        if abilities_text:
            all_abilities[job_name] = abilities_text

            # 单独保存
            out_file = OUTPUT_DIR / f"{chain_name}_{job_name}_能力图谱.txt"
            lines = [l for l in abilities_text.split("\n") if "---" in l]
            n_skills = sum(len(l.split("---")[1].split("/")) if "---" in l else 0 for l in lines)
            out_file.write_text(
                f"# {chain_name} — {job_name} 能力图谱\n"
                f"# 数据来源: {len(results)} 条招聘信息 → AI深度提取\n"
                f"# 搜索关键词: {', '.join(keywords)}\n"
                f"# 共 {len(lines)} 项核心能力 / {n_skills} 个技能点\n\n"
                f"{abilities_text}",
                encoding="utf-8"
            )
            print(f"   {out_file} ({len(lines)}项/{n_skills}技能)")
        else:
            print(f"  [!] AI提取未返回结果")

        time.sleep(1)  # API速率限制

    # 5. 汇总
    if all_abilities:
        summary = OUTPUT_DIR / f"{chain_name}_全部能力图谱汇总.txt"
        with open(summary, "w", encoding="utf-8") as f:
            f.write(f"# {chain_name} 产业链岗位能力图谱汇总\n")
            f.write(f"# 共 {len(all_abilities)} 个岗位\n\n")
            for job_name, text in all_abilities.items():
                f.write(f"## {job_name}\n\n{text}\n\n---\n\n")
        print(f"\n 汇总文件: {summary}")

    print(f"\n{'='*60}")
    print(f"  完成: {len(all_abilities)}/{len(jobs)} 个岗位")
    print(f"{'='*60}")


if __name__ == "__main__":
    if "--list" in sys.argv:
        chains = load_chains()
        for name, info in chains.items():
            print(f"\n  {name} — {info['description']}")
            for jn, jc in info["jobs"].items():
                print(f"    {jn} ({len(jc['search_keywords'])}个搜索词)")
        sys.exit(0)

    chain = sys.argv[1] if len(sys.argv) > 1 else "智能制造"
    job = sys.argv[2] if len(sys.argv) > 2 else None
    run_chain(chain, job)
