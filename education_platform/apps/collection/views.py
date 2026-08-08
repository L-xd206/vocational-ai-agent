"""爬虫 API"""
import json
import threading
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from apps.industry.models import Job
from .models import CrawlTask, JobListing

def _run_crawl(task_id: int):
    """后台执行爬取"""
    try:
        task = CrawlTask.objects.get(id=task_id)
        task.status = "running"
        task.save()

        from .tasks import crawl_single_job
        keywords = task.job.search_keywords or [task.job.name]
        result = crawl_single_job({"name": task.job.name, "search_keywords": keywords}, pages=3)

        task.total_results = result.get("total_results", 0)

        # 保存招聘详情
        for item in result.get("results", []):
            JobListing.objects.create(
                task=task,
                title=item.get("title", ""),
                company=item.get("company", ""),
                city=item.get("city", ""),
                salary=item.get("salary", ""),
                education=item.get("education", ""),
                requirements=item.get("requirements", ""),
                headcount=item.get("headcount", ""),
                post_date=item.get("date", ""),
                source=item.get("source", ""),
            )
        # 明细全部落库后再标记完成，避免前端提前开始能力图谱分析。
        task.status = "completed"
        task.save()
    except Exception as e:
        task = CrawlTask.objects.get(id=task_id)
        task.status = "failed"
        task.save()


@csrf_exempt
@require_http_methods(["POST"])
def api_crawl_start(request):
    """启动爬取"""
    try:
        data = json.loads(request.body)
        job_id = data.get("job_id")
        job = Job.objects.get(id=job_id)

        # 创建任务
        task = CrawlTask.objects.create(
            job=job,
            status="pending",
            total_keywords=len(job.search_keywords or [job.name]),
        )

        # 线程后台执行
        t = threading.Thread(target=_run_crawl, args=(task.id,), daemon=True)
        t.start()

        return JsonResponse({"task_id": task.id, "status": "pending"})

    except Job.DoesNotExist:
        return JsonResponse({"error": "岗位不存在"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def api_crawl_status(request, task_id):
    """查询爬取进度"""
    try:
        task = CrawlTask.objects.get(id=task_id)
        return JsonResponse({
            "task_id": task.id,
            "status": task.status,
            "total_results": task.total_results,
        })
    except CrawlTask.DoesNotExist:
        return JsonResponse({"error": "任务不存在"}, status=404)
