"""爬虫 API"""
import json
import threading
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from apps.industry.models import Job
from .models import CrawlSource, CrawlTask
from .services import save_crawl_result

def _run_crawl(task_id: int):
    """后台执行爬取"""
    try:
        task = CrawlTask.objects.get(id=task_id)
        task.status = "running"
        task.started_at = timezone.now()
        task.error_message = ""
        task.save(update_fields=["status", "started_at", "error_message"])

        from .tasks import crawl_single_job
        keywords = task.job.search_keywords or [task.job.name]
        result = crawl_single_job({"name": task.job.name, "search_keywords": keywords}, pages=3)

        task.total_results = result.get("total_results", 0)
        task.results_json = result.get("results", [])

        # 保存招聘详情
        new_count = 0
        for item in result.get("results", []):
            _, created = save_crawl_result(task, item)
            new_count += int(created)
        # 明细全部落库后再标记完成，避免前端提前开始能力图谱分析。
        task.new_results = new_count
        task.status = "completed"
        task.finished_at = timezone.now()
        task.save(update_fields=[
            "total_results", "new_results", "results_json", "status", "finished_at"
        ])
    except Exception as e:
        task = CrawlTask.objects.get(id=task_id)
        task.status = "failed"
        task.error_message = str(e)
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "error_message", "finished_at"])


@csrf_exempt
@require_http_methods(["POST"])
def api_crawl_start(request):
    """启动爬取"""
    try:
        data = json.loads(request.body)
        job_id = data.get("job_id")
        job = Job.objects.get(id=job_id)
        source_id = data.get("source_id")
        source = None
        if source_id:
            source = CrawlSource.objects.get(id=source_id, is_enabled=True)
        else:
            source = CrawlSource.objects.filter(is_enabled=True).order_by("id").first()

        # 创建任务
        task = CrawlTask.objects.create(
            job=job,
            source=source,
            status="pending",
            trigger_type=data.get("trigger_type", "manual"),
            total_keywords=len(job.search_keywords or [job.name]),
        )

        # 线程后台执行
        t = threading.Thread(target=_run_crawl, args=(task.id,), daemon=True)
        t.start()

        return JsonResponse({"task_id": task.id, "status": "pending"})

    except Job.DoesNotExist:
        return JsonResponse({"error": "岗位不存在"}, status=404)
    except CrawlSource.DoesNotExist:
        return JsonResponse({"error": "采集来源不存在或已禁用"}, status=404)
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
            "new_results": task.new_results,
            "error_message": task.error_message,
        })
    except CrawlTask.DoesNotExist:
        return JsonResponse({"error": "任务不存在"}, status=404)
