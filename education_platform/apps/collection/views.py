"""爬虫 API"""
import json
import threading
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from apps.capabilities.models import parse_abilities_to_tree
from apps.capabilities.services import serialize_official_tree
from apps.industry.models import Job
from .models import AnalysisBatch, AnalysisNode, CrawlSource, CrawlTask
from .services import (
    MIN_VALID_LISTINGS,
    adopt_analysis_node,
    create_analysis_batch,
    data_quality,
    reject_analysis_node,
    save_crawl_result,
    serialize_analysis_tree,
    valid_requirements,
)

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


def _run_candidate_analysis(batch_id: int):
    """后台把岗位采集数据转换为候选树，不直接修改正式能力图谱。"""
    batch = AnalysisBatch.objects.select_related("job", "crawl_task").get(id=batch_id)
    try:
        task = batch.crawl_task
        if task is None or task.status != "completed":
            raise RuntimeError("请先完成招聘数据采集")
        requirements = valid_requirements(task)
        if len(requirements) < MIN_VALID_LISTINGS:
            raise RuntimeError(data_quality(len(requirements))[1])

        from ai.services import generate_capability_map

        official_tree = serialize_official_tree(batch.job)
        result = generate_capability_map(
            batch.job.name,
            requirements,
            official_tree=official_tree,
        )
        if not result or not result.get("abilities_text"):
            raise RuntimeError((result or {}).get("error") or "AI未返回有效的能力图谱内容")
        tree = parse_abilities_to_tree(result["abilities_text"])
        if not tree:
            raise RuntimeError("AI返回内容无法解析为有效能力图谱")
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


@csrf_exempt
@require_http_methods(["POST"])
def api_analysis_start(request):
    """基于岗位最新的已完成采集任务启动一批 AI 候选能力分析。"""
    try:
        data = json.loads(request.body or "{}")
        job = Job.objects.get(id=data.get("job_id"))
        task = CrawlTask.objects.filter(job=job, status="completed").order_by("-created_at").first()
        if task is None:
            return JsonResponse({"error": "请先完成招聘数据采集"}, status=400)
        valid_count = len(valid_requirements(task))
        if valid_count < MIN_VALID_LISTINGS:
            quality, message = data_quality(valid_count)
            return JsonResponse({
                "error": message,
                "data_status": quality,
                "data_count": valid_count,
                "required_count": MIN_VALID_LISTINGS,
            }, status=400)
        batch = AnalysisBatch.objects.create(
            job=job,
            crawl_task=task,
            status="processing",
            input_listing_count=valid_count,
            model_name="deepseek-chat",
            started_at=timezone.now(),
        )
        threading.Thread(target=_run_candidate_analysis, args=(batch.id,), daemon=True).start()
        return JsonResponse({"batch_id": batch.id, "status": batch.status})
    except Job.DoesNotExist:
        return JsonResponse({"error": "岗位不存在"}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)


def api_analysis_tree(request, batch_id):
    """获取某次岗位采集 AI 分析的实体/虚体候选树。"""
    try:
        batch = AnalysisBatch.objects.select_related("job").get(id=batch_id)
        return JsonResponse({
            "batch_id": batch.id,
            "job_id": batch.job_id,
            "job_name": batch.job.name,
            "status": batch.status,
            "error": batch.error_message,
            "tree": serialize_analysis_tree(batch) if batch.status == "completed" else [],
        })
    except AnalysisBatch.DoesNotExist:
        return JsonResponse({"error": "分析批次不存在"}, status=404)


@csrf_exempt
@require_http_methods(["POST"])
def api_analysis_node_adopt(request, node_id):
    """引用一个虚体节点；必要时自动补齐其虚体祖先。"""
    try:
        node = AnalysisNode.objects.select_related("batch__job", "parent", "matched_node").get(id=node_id)
        official = adopt_analysis_node(node)
        return JsonResponse({
            "node_id": node.id,
            "matched_node_id": official.id,
            "decision_status": "adopted",
            "abilities": serialize_official_tree(node.batch.job),
        })
    except AnalysisNode.DoesNotExist:
        return JsonResponse({"error": "AI分析节点不存在"}, status=404)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def api_analysis_node_reject(request, node_id):
    """拒纳一个虚体节点及其所有候选子节点。"""
    try:
        node = AnalysisNode.objects.select_related("matched_node").get(id=node_id)
        reject_analysis_node(node)
        return JsonResponse({"node_id": node.id, "decision_status": "rejected"})
    except AnalysisNode.DoesNotExist:
        return JsonResponse({"error": "AI分析节点不存在"}, status=404)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


def api_rejected_analysis_tree(request):
    """获取某岗位最近分析批次中的未采纳节点树。"""
    job_id = request.GET.get("job_id")
    batches = AnalysisBatch.objects.filter(status="completed")
    if job_id:
        batches = batches.filter(job_id=job_id)
    batch = batches.order_by("-created_at").first()
    if batch is None:
        return JsonResponse({"batch_id": None, "tree": []})
    return JsonResponse({
        "batch_id": batch.id,
        "job_id": batch.job_id,
        "tree": serialize_analysis_tree(batch, decision_status="rejected"),
    })
