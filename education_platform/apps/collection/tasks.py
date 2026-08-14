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

from django.db import IntegrityError, transaction
from django.utils import timezone

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


def crawl_single_job(
    job_config: dict,
    pages: int = PAGES_PER_KW,
    *,
    search_url: str = SEARCH_URL,
    timeout: int = 20,
) -> dict:
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
                req = urllib.request.Request(search_url, data=_build_form(kw, page), headers=headers)
                with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
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


def execute_crawl_task(task_id: int, *, auto_analyze: bool = True):
    """执行一次采集任务；手动采集和定时采集共用这一入口。"""
    from .crawlers.registry import get_crawler
    from .models import CrawlTask
    from .services import save_crawl_result

    # 原子领取任务，避免两个执行器同时开始同一个任务。
    with transaction.atomic():
        task = (
            CrawlTask.objects.select_for_update()
            .select_related("job", "source")
            .get(id=task_id)
        )
        if task.status not in {"pending", "failed"}:
            return task
        task.status = "running"
        task.started_at = timezone.now()
        task.finished_at = None
        task.error_message = ""
        task.save(update_fields=["status", "started_at", "finished_at", "error_message"])

    try:
        if task.source is None:
            raise RuntimeError("采集任务没有配置采集来源")
        if not task.source.is_enabled:
            raise RuntimeError(f"采集来源“{task.source.name}”已停用")

        crawler = get_crawler(task.source)
        results = crawler.crawl(job=task.job, source=task.source)

        new_count = 0
        for item in results:
            _, created = save_crawl_result(task, item)
            new_count += int(created)

        task.total_results = len(results)
        task.new_results = new_count
        task.results_json = results
        task.status = "completed"
        task.finished_at = timezone.now()
        task.save(update_fields=[
            "total_results", "new_results", "results_json", "status", "finished_at",
        ])
    except Exception as exc:
        task.status = "failed"
        task.error_message = str(exc)
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "error_message", "finished_at"])
        return task

    if auto_analyze and task.new_results > 0:
        start_analysis_for_task(task.id)
    return task


def start_analysis_for_task(task_id: int):
    """为一次已完成采集创建唯一的候选能力分析批次。"""
    from .models import AnalysisBatch, CrawlTask
    from .services import (
        MIN_VALID_LISTINGS,
        data_quality,
        valid_requirements,
    )

    task = CrawlTask.objects.select_related("job").get(id=task_id)
    requirements = valid_requirements(task, new_only=True)
    valid_count = len(requirements)
    skipped = valid_count < MIN_VALID_LISTINGS
    _, message = data_quality(valid_count)
    try:
        with transaction.atomic():
            batch = AnalysisBatch.objects.create(
                job=task.job,
                crawl_task=task,
                status="skipped" if skipped else "processing",
                input_listing_count=valid_count,
                model_name="" if skipped else "deepseek-chat",
                error_message=message if skipped else "",
                started_at=timezone.now(),
                finished_at=timezone.now() if skipped else None,
            )
    except IntegrityError:
        return AnalysisBatch.objects.get(crawl_task=task)
    if skipped:
        return batch
    return execute_analysis_batch(batch.id)


def execute_analysis_batch(batch_id: int):
    """执行一个已经创建的候选能力分析批次。"""
    from apps.capabilities.models import parse_abilities_to_tree
    from apps.capabilities.services import serialize_official_tree

    from .models import AnalysisBatch
    from .services import (
        MIN_VALID_LISTINGS,
        create_analysis_batch,
        data_quality,
        valid_requirements,
    )

    batch = AnalysisBatch.objects.select_related("job", "crawl_task").get(id=batch_id)
    try:
        task = batch.crawl_task
        if task is None or task.status != "completed":
            raise RuntimeError("请先完成招聘数据采集")
        requirements = valid_requirements(task, new_only=True)
        valid_count = len(requirements)
        if valid_count < MIN_VALID_LISTINGS:
            _, message = data_quality(valid_count)
            batch.status = "skipped"
            batch.input_listing_count = valid_count
            batch.error_message = message
            batch.finished_at = timezone.now()
            batch.save(update_fields=[
                "status", "input_listing_count", "error_message", "finished_at",
            ])
            return batch

        from ai.services import generate_capability_map

        result = generate_capability_map(
            batch.job.name,
            requirements,
            official_tree=serialize_official_tree(batch.job),
        )
        if not result or not result.get("abilities_text"):
            raise RuntimeError((result or {}).get("error") or "AI未返回有效的能力图谱内容")
        raw_output = result["abilities_text"]
        tree = parse_abilities_to_tree(raw_output)
        clean_output = re.sub(
            r"^```(?:json)?\s*|\s*```$",
            "",
            raw_output.strip(),
            flags=re.IGNORECASE | re.DOTALL,
        )
        try:
            payload = json.loads(clean_output)
            items = payload.get("abilities") if isinstance(payload, dict) else payload
            explicitly_empty = isinstance(items, list) and not items
        except (json.JSONDecodeError, TypeError, AttributeError):
            explicitly_empty = False
        if not tree and not explicitly_empty:
            raise RuntimeError("AI返回内容无法解析为有效候选能力树")
        create_analysis_batch(
            batch.job,
            tree,
            crawl_task=task,
            raw_ai_output=result["abilities_text"],
            model_name="deepseek-chat",
            batch=batch,
        )
    except Exception as exc:
        batch.status = "failed"
        batch.error_message = str(exc)
        batch.finished_at = timezone.now()
        batch.save(update_fields=["status", "error_message", "finished_at"])
    return batch


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
