"""
岗位招聘信息爬虫 — 中国公共招聘网 (job.mohrss.gov.cn)
=====================================================
全国数据，覆盖各省市，无需登录，直接爬取。

用法:
  python crawler.py 电工              # 爬全部页（默认）
  python crawler.py 电工 50           # 爬50页
  python crawler.py 数控操作工 100    # 爬100页
  python crawler.py 电工 --stats      # 仅看统计，不爬
"""
import json
import re
import sys
import time
import urllib.request
import urllib.parse
import ssl
from collections import Counter
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_DIR.mkdir(exist_ok=True)

SEARCH_URL = "http://job.mohrss.gov.cn/cjobs/jobinfolist/listJobinfolist"


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


def _parse_page(html: str) -> list[dict] | None:
    """从HTML中提取岗位JSON数据"""
    match = re.search(
        r'id="findjoblist"[^>]*value="(.*?)"\s+type=',
        html, re.DOTALL
    )
    if not match:
        match = re.search(r'id="findjoblist"[^>]*value="(.*?)"', html, re.DOTALL)
    if not match:
        return None

    raw = match.group(1)
    decoded = raw.replace("&#034;", '"')
    decoded = decoded.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    last = decoded.rfind("}]")
    if last > 0:
        decoded = decoded[:last + 2]

    jobs = json.loads(decoded)
    return [
        {
            "title": j.get("aca112", ""),
            "company": j.get("aab004", ""),
            "city": j.get("area_", j.get("aab302", "")),
            "salary": j.get("acb241", ""),
            "education": _edu(j.get("aac011", "")),
            "experience": j.get("aac014", ""),
            "requirements": j.get("acb22a", ""),
            "headcount": j.get("acb240", ""),
            "date": j.get("s_uptime", j.get("aae397", "")),
            "source": j.get("org_", "中国公共招聘网"),
            "job_id": j.get("acb200", ""),
            "contact": j.get("aae004", ""),
            "phone": j.get("aae005", ""),
            "address": j.get("aae006", ""),
        }
        for j in jobs
    ]


def _edu(code: str) -> str:
    m = {"00": "不限", "10": "初中", "20": "高中", "30": "中技",
         "40": "中专", "50": "大专", "60": "本科", "70": "硕士", "80": "博士"}
    return m.get(code, code)


def _get_page_info(html: str) -> tuple:
    """返回 (total_pages, total_count)"""
    tp = re.search(r'id="totalpages"[^>]*value="(\d+)"', html)
    tc = re.search(r'id="totalcount"[^>]*value="(\d+)"', html)
    return (int(tp.group(1)) if tp else 0, int(tc.group(1)) if tc else 0)


def crawl(keyword: str, max_pages: int = 0) -> list[dict]:
    """
    Args:
        keyword: 搜索关键词
        max_pages: 最大页数，0=全部
    """
    ctx = ssl.create_default_context()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "http://job.mohrss.gov.cn/cjobs/jobinfolist/listJobinfolist",
    }

    all_jobs = []
    page = 1
    total_pages = 0
    total_count = 0

    while True:
        if max_pages > 0 and page > max_pages:
            break
        if total_pages > 0 and page > total_pages:
            break

        # 进度显示
        if page == 1:
            print(f"  第 1 页...", end=" ", flush=True)
        elif page % 10 == 0:
            eta = (total_pages - page) * 0.7 if total_pages else 0
            print(f"\n  [{page}/{total_pages}] {len(all_jobs)}条 | 剩余约{eta:.0f}s", end=" ", flush=True)

        try:
            req = urllib.request.Request(SEARCH_URL, data=_build_form(keyword, page), headers=headers)
            with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            print(f"\n  请求失败(p{page}): {e}")
            time.sleep(3)
            continue

        if page == 1:
            total_pages, total_count = _get_page_info(html)
            print(f"共 {total_count} 条 / {total_pages} 页")
            if max_pages == 0:
                print(f"  将爬取全部 {total_pages} 页，预计 {total_pages * 0.6:.0f}s")

        jobs = _parse_page(html)
        if jobs is None:
            print(f"\n  p{page}无数据")
            break

        all_jobs.extend(jobs)
        page += 1
        time.sleep(0.6)  # 页间延迟

    print(f"\n  完成: {len(all_jobs)} 条 / {page-1} 页")
    return all_jobs


def stats(keyword: str):
    """仅查看统计信息，不爬取"""
    ctx = ssl.create_default_context()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "http://job.mohrss.gov.cn/cjobs/jobinfolist/listJobinfolist",
    }
    req = urllib.request.Request(SEARCH_URL, data=_build_form(keyword, 1), headers=headers)
    with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    tp, tc = _get_page_info(html)
    jobs = _parse_page(html)
    print(f"\n  关键词: {keyword}")
    print(f"  总计: {tc} 条 / {tp} 页")

    if jobs:
        cities = Counter(j.get("city", "") for j in jobs)
        sources = Counter(j.get("source", "") for j in jobs)
        print(f"\n  地区分布 (首页):")
        for c, n in cities.most_common(10):
            print(f"    {c}: {n}")
        print(f"\n  发布机构 (首页):")
        for s, n in sources.most_common(5):
            print(f"    {s}: {n}")


def save(jobs: list[dict], keyword: str):
    filepath = OUTPUT_DIR / f"{keyword}_爬取结果.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({
            "search_keyword": keyword,
            "total": len(jobs),
            "source": "中国公共招聘网 (job.mohrss.gov.cn)",
            "crawl_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "results": jobs,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n  保存: {filepath}")

    if jobs:
        cities = Counter(j.get("city", "") for j in jobs)
        print(f"  地区覆盖: {len(cities)} 个")
        print(f"  预览 (前3条):")
        for i, j in enumerate(jobs[:3], 1):
            print(f"  {i}. [{j['company'][:12]}] {j['title']} | {j['city'][:8]} | {j['salary']} | {j['date']}")


if __name__ == "__main__":
    if "--stats" in sys.argv:
        keyword = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "电工"
        stats(keyword)
        sys.exit(0)

    keyword = sys.argv[1] if len(sys.argv) > 1 else "电工"
    pages = int(sys.argv[2]) if len(sys.argv) > 2 else 0

    mode = f"{pages} 页" if pages > 0 else "全部"
    print(f"\n  [中国公共招聘网] {keyword} | {mode}\n")

    jobs = crawl(keyword, pages)
    if not jobs:
        print("\n  无数据")
        sys.exit(1)

    save(jobs, keyword)
