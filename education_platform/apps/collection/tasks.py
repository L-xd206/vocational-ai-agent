"""
Step 2: 并行爬取产业链多个岗位的招聘信息
=========================================
读取 step1 生成的岗位清单，同时爬取所有岗位的招聘数据。
使用线程池并行爬取，5 个岗位同时进行，大幅提速。

用法:
  python step2_crawl_jobs.py 智能制造    # 爬取智能制造全部岗位
  python step2_crawl_jobs.py 新能源      # 爬取新能源全部岗位
  python step2_crawl_jobs.py 新能源 3    # 每个关键词爬3页（默认3页）
"""
import json
import re
import sys
import time
import ssl
import urllib.request
import urllib.parse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

SEARCH_URL = "http://job.mohrss.gov.cn/cjobs/jobinfolist/listJobinfolist"
MAX_WORKERS = 5  # 并行爬取线程数
PAGES_PER_KW = 3  # 每个关键词默认爬3页


# ============================================================
#  爬取逻辑（复用的，和 crawler.py 一样）
# ============================================================
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
    clean = lambda s: re.sub(r"[（(][^)）]*[)）]", "", s).strip()
    a, b = clean(a), clean(b)
    return a == b or (len(a) > 3 and len(b) > 3 and (a[:4] == b[:4] or a in b or b in a))


def crawl_single_job(job_config: dict, pages: int = PAGES_PER_KW) -> dict:
    """
    爬取单个岗位（用所有搜索关键词并行搜索，合并去重）
    这个函数在独立线程中执行
    """
    job_name = job_config["name"]
    keywords = job_config.get("search_keywords", [job_name])
    ctx = ssl.create_default_context()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "http://job.mohrss.gov.cn/cjobs/jobinfolist/listJobinfolist",
    }

    all_results = []
    seen = set()

    for kw in keywords:
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
            time.sleep(0.3)

        # 去重
        new_count = 0
        for r in kw_results:
            key = (r["company"], r["title"][:10])
            if key in seen:
                continue
            is_dup = False
            for existing in all_results:
                if existing["company"] == r["company"] and _title_similar(existing["title"], r["title"]):
                    is_dup = True
                    if len(r.get("requirements", "")) > len(existing.get("requirements", "")):
                        existing.update(r)
                    break
            if not is_dup:
                seen.add(key)
                all_results.append(r)
                new_count += 1

    return {
        "job_name": job_name,
        "keywords_used": keywords,
        "total_keywords": len(keywords),
        "total_results": len(all_results),
        "results": all_results,
    }


# ============================================================
#  并行爬取主函数
# ============================================================
def crawl_chain(chain_name: str, pages: int = PAGES_PER_KW):
    # 读取 step1 生成的岗位清单
    job_file = DATA_DIR / f"{chain_name}_岗位清单.json"
    if not job_file.exists():
        print(f"  [错误] 未找到 {job_file}")
        print(f"  请先运行: python -m ai.jobs {chain_name}")
        return

    with open(job_file, "r", encoding="utf-8") as f:
        chain_data = json.load(f)

    jobs = chain_data.get("jobs", [])
    print(f"\n{'='*60}")
    print(f"  Step 2: 并行爬取 [{chain_name}] 产业链招聘数据")
    print(f"  岗位数: {len(jobs)} | 并发数: {MAX_WORKERS} | 每关键词: {pages}页")
    print(f"{'='*60}")

    total_all = 0
    results_map = {}  # {岗位名: 爬取结果}

    # 线程池并行爬取
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(crawl_single_job, job, pages): job["name"]
            for job in jobs
        }

        completed = 0
        for future in as_completed(futures):
            job_name = futures[future]
            completed += 1
            try:
                result = future.result()
                results_map[job_name] = result
                n = result["total_results"]
                total_all += n

                bar = "|" + "#" * min(n // 5, 40) + " " * max(0, 40 - n // 5) + "|"
                print(f"  [{completed}/{len(jobs)}] {job_name}: {n}条 {bar}")
            except Exception as e:
                print(f"  [{completed}/{len(jobs)}] {job_name}: 失败 - {e}")

    # 保存
    summary = {
        "chain": chain_name,
        "crawl_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_jobs": len(jobs),
        "total_results": total_all,
        "jobs": {
            name: {
                "total": r["total_results"],
                "keywords_used": r["keywords_used"],
                "results": r["results"],
            }
            for name, r in results_map.items()
        },
    }

    out_file = DATA_DIR / f"{chain_name}_全部岗位_爬取结果.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 汇总
    print(f"\n{'='*60}")
    print(f"  爬取完成")
    print(f"{'='*60}")
    for name, r in results_map.items():
        print(f"  {name}: {r['total_results']}条")
    print(f"\n  共计: {total_all} 条 | 保存: {out_file}")


if __name__ == "__main__":
    chain = sys.argv[1] if len(sys.argv) > 1 else "智能制造"
    pages = int(sys.argv[2]) if len(sys.argv) > 2 else PAGES_PER_KW
    crawl_chain(chain, pages)
