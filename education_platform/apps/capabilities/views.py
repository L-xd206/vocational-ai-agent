"""能力图谱 API"""
import json
import threading
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from apps.industry.models import Job, Chain
from apps.collection.models import CrawlTask
from apps.collection.services import MIN_VALID_LISTINGS, data_quality, valid_requirements
from apps.organizations.models import Organization
from .models import AbilityMap, CapabilityNode, parse_abilities_to_tree
from .services import (
    create_official_node,
    merge_official_tree,
    normalise_legacy_tree,
    resolve_node_by_legacy_path,
    serialize_official_tree,
    set_job_tree_enabled,
    set_node_enabled,
)


def _run_ability_gen(job_id: int):
    """后台生成能力图谱"""
    try:
        job = Job.objects.get(id=job_id)
        task = CrawlTask.objects.filter(job=job, status="completed").order_by("-created_at").first()
        if not task:
            raise RuntimeError("请先完成招聘数据采集")

        # 先筛选有效招聘要求，避免让 AI 基于过少数据生成图谱
        reqs = valid_requirements(task)
        if len(reqs) < MIN_VALID_LISTINGS:
            quality, message = data_quality(len(reqs))
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
        valid_count = len(valid_requirements(task))
        quality, message = data_quality(valid_count)
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
        data_count = len(valid_requirements(crawl_task)) if crawl_task else 0
        quality_status, data_message = data_quality(data_count)

        has_nodes = CapabilityNode.objects.filter(job_id=job_id).exists()
        if not am and not has_nodes:
            return JsonResponse({"abilities": [], "status": "not_generated", "crawl_status": crawl_status,
                                 "data_count": data_count, "data_status": quality_status, "data_message": data_message,
                                 "required_count": MIN_VALID_LISTINGS})

        if am and am.generation_status == "processing":
            return JsonResponse({"abilities": [], "status": "processing", "error": "能力图谱正在生成", "crawl_status": crawl_status,
                                 "data_count": data_count, "data_status": quality_status, "data_message": data_message,
                                 "required_count": MIN_VALID_LISTINGS})
        if am and am.generation_status == "error":
            return JsonResponse({"abilities": [], "status": "error", "error": am.generation_error or "能力图谱生成失败", "crawl_status": crawl_status,
                                 "data_count": data_count, "data_status": quality_status, "data_message": data_message,
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
            "data_status": quality_status,
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
            organization_name=college,
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
def api_ability_node_organization(request):
    """修改正式岗位能力节点的所属学院。"""
    try:
        data = json.loads(request.body or "{}")
        node_id = int(data.get("node_id"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "岗位能力参数无效"}, status=400)

    node = CapabilityNode.objects.filter(
        pk=node_id,
        node_type="ability",
        parent__isnull=True,
    ).first()
    if node is None:
        return JsonResponse({"error": "岗位能力节点不存在"}, status=404)

    organization_id = data.get("organization_id") or None
    if organization_id is None:
        node.organization = None
    else:
        organization = Organization.objects.filter(
            pk=organization_id,
            org_type="学院",
            is_enabled=True,
        ).first()
        if organization is None:
            return JsonResponse({"error": "所属学院不存在或已停用"}, status=400)
        node.organization = organization
    node.save(update_fields=["organization", "updated_at"])
    return JsonResponse({
        "ok": True,
        "node_id": node.id,
        "organization_id": node.organization_id,
        "college": node.organization.name if node.organization else "未分配学院",
        "abilities": serialize_official_tree(node.job),
    })


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
