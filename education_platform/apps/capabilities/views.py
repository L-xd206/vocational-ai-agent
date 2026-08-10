"""能力图谱 API"""
import json
import threading
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from apps.industry.models import Job, Chain
from apps.collection.models import CrawlTask
from .models import AbilityMap, AnalysisBatch, AnalysisNode, CapabilityNode, parse_abilities_to_tree
from .services import (
    adopt_analysis_node,
    create_analysis_batch,
    create_official_node,
    merge_official_tree,
    normalise_legacy_tree,
    reject_analysis_node,
    resolve_node_by_legacy_path,
    serialize_official_tree,
    serialize_analysis_tree,
    set_job_tree_enabled,
    set_node_enabled,
)

MIN_VALID_LISTINGS = 10


def _valid_requirements(task):
    """只保留包含有效任职要求的招聘记录，作为能力图谱分析依据。"""
    from apps.collection.models import JobListing
    reqs = list(JobListing.objects.filter(task=task).values_list("requirements", flat=True))
    return [str(r).strip() for r in reqs if r and len(str(r).strip()) > 10]


def _data_quality(count: int) -> tuple[str, str]:
    if count == 0:
        return "no_data", "暂无有效招聘数据，暂不生成能力图谱"
    if count < MIN_VALID_LISTINGS:
        return "insufficient", f"有效招聘数据仅 {count} 条，少于 {MIN_VALID_LISTINGS} 条，暂不生成能力图谱"
    if count >= 30:
        return "sufficient", f"有效招聘数据 {count} 条，数据较充分"
    return "ready", f"有效招聘数据 {count} 条，可以生成能力图谱"


def _run_ability_gen(job_id: int):
    """后台生成能力图谱"""
    try:
        job = Job.objects.get(id=job_id)
        task = CrawlTask.objects.filter(job=job, status="completed").order_by("-created_at").first()
        if not task:
            raise RuntimeError("请先完成招聘数据采集")

        # 先筛选有效招聘要求，避免让 AI 基于过少数据生成图谱
        reqs = _valid_requirements(task)
        if len(reqs) < MIN_VALID_LISTINGS:
            quality, message = _data_quality(len(reqs))
            raise RuntimeError(message)

        from ai.services import generate_capability_map
        result = generate_capability_map(job.name, reqs)

        if result and result.get("abilities_text"):
            tree = parse_abilities_to_tree(result["abilities_text"])
            if not tree:
                raise RuntimeError("AI返回内容无法解析为有效能力图谱")
            tree = normalise_legacy_tree(tree)
            merge_official_tree(job, tree, origin="ai")
            AbilityMap.objects.update_or_create(
                job=job,
                defaults={
                    "abilities_json": tree,
                    "total_abilities": len(tree),
                    "total_skills": sum(
                        len(unit.get("children", []))
                        for item in tree
                        for unit in item.get("units", [])
                    ),
                    "raw_text": result["abilities_text"],
                    "generation_status": "ready",
                    "generation_error": "",
                    "review_status": "pending",
                    "review_note": "",
                    "reviewed_at": None,
                }
            )
        else:
            raise RuntimeError(result.get("error") or "AI未返回有效的能力图谱内容")
    except Exception as e:
        print(f"Ability gen error: {e}")
        AbilityMap.objects.filter(job_id=job_id).update(
            generation_status="error", generation_error=str(e)
        )


def _run_candidate_analysis(batch_id: int):
    """后台把最新采集数据转换为候选树，不直接修改正式能力图谱。"""
    batch = AnalysisBatch.objects.select_related("job", "crawl_task").get(id=batch_id)
    try:
        task = batch.crawl_task
        if task is None or task.status != "completed":
            raise RuntimeError("请先完成招聘数据采集")
        requirements = _valid_requirements(task)
        if len(requirements) < MIN_VALID_LISTINGS:
            raise RuntimeError(_data_quality(len(requirements))[1])
        from ai.services import generate_capability_map
        result = generate_capability_map(batch.job.name, requirements)
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
def api_ability_generate(request):
    """生成能力图谱"""
    try:
        data = json.loads(request.body)
        job_id = data.get("job_id")
        job = Job.objects.get(id=job_id)

        # 先检查是否已有爬取数据，并筛选有效招聘要求
        task = CrawlTask.objects.filter(job=job, status="completed").order_by("-created_at").first()
        if not task:
            return JsonResponse({"error": "请先爬取招聘数据"}, status=400)
        valid_count = len(_valid_requirements(task))
        quality, message = _data_quality(valid_count)
        if valid_count < MIN_VALID_LISTINGS:
            return JsonResponse({
                "error": message,
                "data_status": quality,
                "data_count": valid_count,
                "required_count": MIN_VALID_LISTINGS,
            }, status=400)

        # 后台生成
        am, _ = AbilityMap.objects.get_or_create(job=job, defaults={"abilities_json": []})
        am.generation_status = "processing"
        am.generation_error = ""
        am.review_status = "pending"
        am.review_note = ""
        am.reviewed_at = None
        am.save(update_fields=["generation_status", "generation_error", "review_status", "review_note", "reviewed_at"])
        t = threading.Thread(target=_run_ability_gen, args=(job_id,), daemon=True)
        t.start()

        return JsonResponse({"status": "processing", "job_id": job_id})

    except Job.DoesNotExist:
        return JsonResponse({"error": "岗位不存在"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def api_ability_tree(request, job_id):
    """获取能力图谱树"""
    try:
        am = AbilityMap.objects.filter(job_id=job_id).first()

        # 同时检查爬取状态
        from apps.collection.models import CrawlTask
        crawl_task = CrawlTask.objects.filter(job_id=job_id, status="completed").order_by("-created_at").first()
        crawl_status = "completed" if crawl_task else "not_started"
        data_count = len(_valid_requirements(crawl_task)) if crawl_task else 0
        data_quality, data_message = _data_quality(data_count)

        has_nodes = CapabilityNode.objects.filter(job_id=job_id).exists()
        if not am and not has_nodes:
            return JsonResponse({"abilities": [], "status": "not_generated", "crawl_status": crawl_status,
                                 "data_count": data_count, "data_status": data_quality, "data_message": data_message,
                                 "required_count": MIN_VALID_LISTINGS})

        if am and am.generation_status == "processing":
            return JsonResponse({"abilities": [], "status": "processing", "error": "能力图谱正在生成", "crawl_status": crawl_status,
                                 "data_count": data_count, "data_status": data_quality, "data_message": data_message,
                                 "required_count": MIN_VALID_LISTINGS})
        if am and am.generation_status == "error":
            return JsonResponse({"abilities": [], "status": "error", "error": am.generation_error or "能力图谱生成失败", "crawl_status": crawl_status,
                                 "data_count": data_count, "data_status": data_quality, "data_message": data_message,
                                 "required_count": MIN_VALID_LISTINGS})

        job = Job.objects.get(id=job_id)
        tree = serialize_official_tree(job)
        total_abilities = sum(1 for item in tree)
        total_skills = sum(
            len(unit.get("children", []))
            for ability in tree
            for unit in ability.get("units", [])
        )
        return JsonResponse({
            "job_name": job.name,
            "total_abilities": total_abilities,
            "total_skills": total_skills,
            "abilities": tree,
            "status": "ready",
            "review_status": am.review_status if am else "pending",
            "review_note": am.review_note if am else "",
            "reviewed_at": am.reviewed_at.isoformat() if am and am.reviewed_at else None,
            "crawl_status": "completed",
            "data_count": data_count,
            "data_status": data_quality,
            "data_message": data_message,
            "required_count": MIN_VALID_LISTINGS,
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def _normalise_tree(tree):
    """旧导入路径兼容入口；新代码统一使用 services.normalise_legacy_tree。"""
    return normalise_legacy_tree(tree)


@csrf_exempt
@require_http_methods(["POST"])
def api_ability_node_toggle(request):
    """切换产业链、岗位或图谱节点状态；禁用父节点时递归禁用所有子节点。"""
    try:
        data = json.loads(request.body)
        node_type = data.get("node_type")
        enabled = bool(data.get("enabled"))

        if node_type == "chain":
            chain = Chain.objects.get(id=data["node_id"])
            chain.is_enabled = enabled
            chain.save(update_fields=["is_enabled"])
            if not enabled:
                for job in chain.jobs.all():
                    job.is_enabled = False
                    job.save(update_fields=["is_enabled"])
                    set_job_tree_enabled(job, False)
            return JsonResponse({"enabled": enabled})

        job = Job.objects.get(id=data["job_id"])
        if node_type == "job":
            job.is_enabled = enabled
            job.save(update_fields=["is_enabled"])
            if not enabled:
                set_job_tree_enabled(job, False)
            return JsonResponse({"enabled": enabled})

        if node_type not in {"ability", "unit", "point"}:
            return JsonResponse({"error": "不支持的节点类型"}, status=400)
        node_id = data.get("node_id")
        if node_id and str(node_id).isdigit():
            node = CapabilityNode.objects.get(id=int(node_id), job=job, node_type=node_type)
        else:
            node = resolve_node_by_legacy_path(
                job,
                node_type,
                data.get("ability_index"),
                data.get("unit_index"),
                data.get("point_index"),
            )
        set_node_enabled(node, enabled)
        tree = serialize_official_tree(job)
        return JsonResponse({"enabled": enabled, "abilities": tree})
    except (Chain.DoesNotExist, Job.DoesNotExist, CapabilityNode.DoesNotExist, IndexError, KeyError, TypeError, ValueError):
        return JsonResponse({"error": "节点不存在或节点路径无效"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def _toggle_job_tree(job, enabled):
    """兼容旧调用；正式数据已经迁移到节点表。"""
    set_job_tree_enabled(job, enabled)


@csrf_exempt
@require_http_methods(["POST"])
def api_ability_node_add(request):
    """向能力或能力单元后新增子节点；技能点本身不允许继续新增。"""
    try:
        data = json.loads(request.body)
        name = str(data.get("name", "")).strip()
        college = str(data.get("college", "")).strip()
        parent_type = data.get("parent_type")
        if not name or parent_type not in {"job", "ability", "unit"}:
            return JsonResponse({"error": "节点名称或父节点类型无效"}, status=400)
        if parent_type == "job" and not college:
            return JsonResponse({"error": "请选择所属学院"}, status=400)
        job = Job.objects.get(id=data["job_id"])
        create_official_node(
            job=job,
            parent_type=parent_type,
            name=name,
            college_name=college,
            ability_index=data.get("ability_index"),
            unit_index=data.get("unit_index"),
        )
        tree = serialize_official_tree(job)
        return JsonResponse({"abilities": tree})
    except Job.DoesNotExist:
        return JsonResponse({"error": "岗位不存在"}, status=404)
    except (IndexError, KeyError, TypeError):
        return JsonResponse({"error": "节点路径无效"}, status=404)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_ability_review(request, job_id):
    """负责人确认或退回能力图谱。"""
    try:
        data = json.loads(request.body or "{}")
        status = data.get("status")
        if status not in {"confirmed", "rejected", "pending"}:
            return JsonResponse({"error": "审核状态无效"}, status=400)
        am = AbilityMap.objects.get(job_id=job_id)
        if am.generation_status != "ready":
            return JsonResponse({"error": "能力图谱尚未生成完成"}, status=400)
        am.review_status = status
        am.review_note = str(data.get("note") or "").strip()
        am.reviewed_at = timezone.now() if status != "pending" else None
        am.save(update_fields=["review_status", "review_note", "reviewed_at"])
        return JsonResponse({
            "job_id": job_id,
            "review_status": am.review_status,
            "review_note": am.review_note,
            "reviewed_at": am.reviewed_at.isoformat() if am.reviewed_at else None,
        })
    except AbilityMap.DoesNotExist:
        return JsonResponse({"error": "能力图谱不存在"}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)


def api_ability_text(request, job_id):
    """获取能力图谱原始文本"""
    try:
        am = AbilityMap.objects.filter(job_id=job_id).first()
        if not am:
            return JsonResponse({"text": "尚未生成"})
        return JsonResponse({"text": am.raw_text})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


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
        valid_count = len(_valid_requirements(task))
        if valid_count < MIN_VALID_LISTINGS:
            quality, message = _data_quality(valid_count)
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
    """获取某次 AI 分析的实体/虚体候选树。"""
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
