"""岗位招聘数据采集与 AI 候选能力分析 API。"""

import json
import threading

from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db.models import Prefetch
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.capabilities.services import serialize_official_tree
from apps.industry.models import Job

from .models import AnalysisBatch, AnalysisNode, CrawlSource, CrawlTask
from .services import (
    MIN_VALID_LISTINGS,
    adopt_analysis_node,
    create_crawl_source,
    create_crawl_task,
    data_quality,
    reject_analysis_node,
    serialize_analysis_tree,
    serialize_crawl_source,
    serialize_rejected_tree,
    update_crawl_source,
    valid_requirements,
)
from .tasks import execute_analysis_batch, execute_crawl_task


# 保留旧名称，兼容已有测试或内部调用；新代码统一调用 tasks 中的函数。
_run_crawl = execute_crawl_task
_run_candidate_analysis = execute_analysis_batch


def _json_body(request):
    try:
        return json.loads(request.body or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("无效的 JSON") from exc


@login_required
@require_http_methods(["GET", "POST"])
@csrf_exempt
def api_crawl_sources(request):
    """查询采集来源；POST 用于未来新增已实现采集器对应的来源。"""
    if request.method == "GET":
        return JsonResponse({
            "sources": [
                serialize_crawl_source(source)
                for source in CrawlSource.objects.order_by("id")
            ],
        })
    try:
        source = create_crawl_source(_json_body(request))
        return JsonResponse({"source": serialize_crawl_source(source)}, status=201)
    except (ValueError, IntegrityError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@login_required
@require_http_methods(["PATCH"])
@csrf_exempt
def api_crawl_source_detail(request, source_id):
    """编辑某个采集来源的通用配置。"""
    try:
        source = CrawlSource.objects.get(id=source_id)
        source = update_crawl_source(source, _json_body(request))
        return JsonResponse({"source": serialize_crawl_source(source)})
    except CrawlSource.DoesNotExist:
        return JsonResponse({"error": "采集来源不存在"}, status=404)
    except (ValueError, IntegrityError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def api_crawl_start(request):
    """手动启动一个岗位的采集；同来源同岗位禁止重复执行。"""
    try:
        data = _json_body(request)
        job = Job.objects.get(
            id=data.get("job_id"),
            is_enabled=True,
            chain__is_enabled=True,
        )
        source_id = data.get("source_id")
        source_query = CrawlSource.objects.filter(is_enabled=True)
        source = (
            source_query.get(id=source_id)
            if source_id
            else source_query.order_by("id").first()
        )
        if source is None:
            return JsonResponse({"error": "暂无已启用的采集来源"}, status=400)

        task, created = create_crawl_task(
            job=job,
            source=source,
            trigger_type="manual",
        )
        if not created:
            return JsonResponse({
                "error": "该岗位在此来源已有采集任务正在执行",
                "task_id": task.id,
                "status": task.status,
            }, status=409)

        threading.Thread(
            target=execute_crawl_task,
            args=(task.id,),
            kwargs={"auto_analyze": True},
            daemon=True,
        ).start()
        return JsonResponse({"task_id": task.id, "status": task.status}, status=202)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Job.DoesNotExist:
        return JsonResponse({"error": "岗位不存在或已禁用"}, status=404)
    except CrawlSource.DoesNotExist:
        return JsonResponse({"error": "采集来源不存在或已禁用"}, status=404)


@login_required
@require_http_methods(["GET"])
def api_crawl_status(request, task_id):
    try:
        task = CrawlTask.objects.get(id=task_id)
        analysis = task.analysis_batches.order_by("-created_at").first()
        return JsonResponse({
            "task_id": task.id,
            "status": task.status,
            "total_results": task.total_results,
            "new_results": task.new_results,
            "error_message": task.error_message,
            "analysis": ({
                "id": analysis.id,
                "status": analysis.status,
                "error_message": analysis.error_message,
            } if analysis else None),
        })
    except CrawlTask.DoesNotExist:
        return JsonResponse({"error": "采集任务不存在"}, status=404)


@login_required
@require_http_methods(["GET"])
def api_crawl_tasks(request):
    queryset = CrawlTask.objects.select_related("job", "source").order_by("-created_at")
    if request.GET.get("job_id"):
        queryset = queryset.filter(job_id=request.GET["job_id"])
    if request.GET.get("status"):
        queryset = queryset.filter(status=request.GET["status"])

    items = []
    for task in queryset[:100]:
        analysis = task.analysis_batches.order_by("-created_at").first()
        items.append({
            "id": task.id,
            "job": {"id": task.job_id, "name": task.job.name},
            "source": ({"id": task.source_id, "name": task.source.name} if task.source else None),
            "trigger_type": task.trigger_type,
            "status": task.status,
            "total_results": task.total_results,
            "new_results": task.new_results,
            "error_message": task.error_message,
            "created_at": task.created_at.isoformat(),
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "finished_at": task.finished_at.isoformat() if task.finished_at else None,
            "analysis": ({
                "id": analysis.id,
                "status": analysis.status,
                "error_message": analysis.error_message,
            } if analysis else None),
        })
    return JsonResponse({"tasks": items})


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def api_analysis_start(request):
    """手动补触发最新已完成任务的候选分析。"""
    try:
        data = _json_body(request)
        job = Job.objects.get(id=data.get("job_id"))
        task = CrawlTask.objects.filter(job=job, status="completed").order_by("-created_at").first()
        if task is None:
            return JsonResponse({"error": "请先完成招聘数据采集"}, status=400)
        existing = AnalysisBatch.objects.filter(crawl_task=task).first()
        if existing:
            return JsonResponse({"batch_id": existing.id, "status": existing.status})

        requirements = valid_requirements(task)
        valid_count = len(requirements)
        if valid_count < MIN_VALID_LISTINGS:
            _, message = data_quality(valid_count)
            batch = AnalysisBatch.objects.create(
                job=job,
                crawl_task=task,
                status="skipped",
                input_listing_count=valid_count,
                error_message=message,
                started_at=timezone.now(),
                finished_at=timezone.now(),
            )
            return JsonResponse({"batch_id": batch.id, "status": batch.status})

        batch = AnalysisBatch.objects.create(
            job=job,
            crawl_task=task,
            status="processing",
            input_listing_count=valid_count,
            model_name="deepseek-chat",
            started_at=timezone.now(),
        )
        threading.Thread(target=execute_analysis_batch, args=(batch.id,), daemon=True).start()
        return JsonResponse({"batch_id": batch.id, "status": batch.status}, status=202)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Job.DoesNotExist:
        return JsonResponse({"error": "岗位不存在"}, status=404)


@login_required
@require_http_methods(["GET"])
def api_analysis_tree(request, batch_id):
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


@login_required
@require_http_methods(["GET"])
def api_latest_analysis_trees(request):
    """一次返回各岗位的最新分析结果，供岗位采集四列树首屏使用。"""
    latest_batches = AnalysisBatch.objects.select_related("crawl_task").order_by("-created_at")
    jobs = (
        Job.objects.filter(is_enabled=True, chain__is_enabled=True)
        .select_related("chain")
        .prefetch_related(Prefetch(
            "analysis_batches",
            queryset=latest_batches,
            to_attr="collection_batches",
        ))
        .order_by("chain__name", "name", "id")
    )

    results = []
    for job in jobs:
        batch = job.collection_batches[0] if job.collection_batches else None
        results.append({
            "job": {
                "id": job.id,
                "name": job.name,
                "chain_id": job.chain_id,
                "chain_name": job.chain.name,
            },
            "batch": ({
                "id": batch.id,
                "status": batch.status,
                "crawl_task_id": batch.crawl_task_id,
                "input_listing_count": batch.input_listing_count,
                "error_message": batch.error_message,
                "created_at": batch.created_at.isoformat(),
            } if batch else None),
            "tree": (
                serialize_analysis_tree(batch)
                if batch and batch.status == "completed" else []
            ),
        })
    return JsonResponse({"results": results})


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def api_analysis_node_adopt(request, node_id):
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


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def api_analysis_node_reject(request, node_id):
    try:
        node = AnalysisNode.objects.select_related("matched_node").get(id=node_id)
        reject_analysis_node(node)
        return JsonResponse({"node_id": node.id, "decision_status": "rejected"})
    except AnalysisNode.DoesNotExist:
        return JsonResponse({"error": "AI分析节点不存在"}, status=404)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@login_required
@require_http_methods(["GET"])
def api_rejected_analysis_tree(request):
    """返回全部未采纳历史，并为叶子拒纳数据保留完整祖先路径。"""
    batches = AnalysisBatch.objects.filter(
        nodes__decision_status="rejected",
    ).select_related("job", "crawl_task").distinct().order_by("-created_at")
    if request.GET.get("job_id"):
        batches = batches.filter(job_id=request.GET["job_id"])
    return JsonResponse({
        "results": [{
            "batch_id": batch.id,
            "job": {"id": batch.job_id, "name": batch.job.name},
            "crawl_task_id": batch.crawl_task_id,
            "created_at": batch.created_at.isoformat(),
            "tree": serialize_rejected_tree(batch),
        } for batch in batches],
    })
