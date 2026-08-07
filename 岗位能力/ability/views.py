"""能力图谱 API"""
import json
import sys
import threading
import copy
import math
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from chain.models import Job
from chain.models import Chain
from crawl.models import CrawlTask
from .models import AbilityMap, parse_abilities_to_tree

BASE_DIR = __file__.split("ability")[0]
sys.path.insert(0, BASE_DIR)


def _run_ability_gen(job_id: int):
    """后台生成能力图谱"""
    try:
        job = Job.objects.get(id=job_id)
        task = CrawlTask.objects.filter(job=job, status="completed").first()
        if not task:
            raise RuntimeError("请先完成招聘数据采集")

        # 收集招聘要求
        from crawl.models import JobListing
        reqs = list(JobListing.objects.filter(task=task).values_list("requirements", flat=True))
        reqs = [r for r in reqs if r and len(r) > 10]

        from step3_gen_abilities import gen_ability
        result = gen_ability(job.name, reqs)

        if result and result.get("abilities_text"):
            tree = parse_abilities_to_tree(result["abilities_text"])
            if not tree:
                raise RuntimeError("AI返回内容无法解析为有效能力图谱")
            AbilityMap.objects.update_or_create(
                job=job,
                defaults={
                    "abilities_json": tree,
                    "total_abilities": len(tree),
                    "total_skills": sum(len(item.get("children", [])) for item in tree),
                    "raw_text": result["abilities_text"],
                    "generation_status": "ready",
                    "generation_error": "",
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

        # 先检查是否已有爬取数据
        task = CrawlTask.objects.filter(job=job, status="completed").first()
        if not task:
            return JsonResponse({"error": "请先爬取招聘数据"}, status=400)

        # 后台生成
        am, _ = AbilityMap.objects.get_or_create(job=job, defaults={"abilities_json": []})
        am.generation_status = "processing"
        am.generation_error = ""
        am.save(update_fields=["generation_status", "generation_error"])
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
        from crawl.models import CrawlTask
        crawl_task = CrawlTask.objects.filter(job_id=job_id, status="completed").first()
        crawl_status = "completed" if crawl_task else "not_started"

        if not am:
            return JsonResponse({"abilities": [], "status": "not_generated", "crawl_status": crawl_status})

        if am.generation_status == "processing":
            return JsonResponse({"abilities": [], "status": "processing", "error": "能力图谱正在生成", "crawl_status": crawl_status})
        if am.generation_status == "error":
            return JsonResponse({"abilities": [], "status": "error", "error": am.generation_error or "能力图谱生成失败", "crawl_status": crawl_status})

        tree = _normalise_tree(am.abilities_json)
        return JsonResponse({
            "job_name": am.job.name,
            "total_abilities": am.total_abilities,
            "total_skills": am.total_skills,
            "abilities": tree,
            "status": "ready",
            "crawl_status": "completed",
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def _normalise_tree(tree):
    """兼容旧版仅有 children 的图谱，同时给每一级补齐启用状态。"""
    result = copy.deepcopy(tree or [])
    for ability in result:
        ability.setdefault("enabled", True)
        ability.setdefault("college", "未分配学院")
        if "units" not in ability:
            points = ability.pop("children", []) or []
            size = math.ceil(len(points) / 3) if points else 1
            ability["units"] = [
                {"name": f"能力单元 {index // size + 1}", "enabled": True,
                 "children": [{**point, "enabled": point.get("enabled", True)} for point in points[index:index + size]]}
                for index in range(0, len(points), size)
            ]
        for unit in ability["units"]:
            unit.setdefault("enabled", True)
            unit.setdefault("children", [])
            for point in unit["children"]:
                point.setdefault("enabled", True)
    return result


def _set_descendants_enabled(node, enabled):
    node["enabled"] = enabled
    for unit in node.get("units", []):
        _set_descendants_enabled(unit, enabled)
    for point in node.get("children", []):
        point["enabled"] = enabled


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
                    _toggle_job_tree(job, False)
            return JsonResponse({"enabled": enabled})

        job = Job.objects.get(id=data["job_id"])
        if node_type == "job":
            job.is_enabled = enabled
            job.save(update_fields=["is_enabled"])
            if not enabled:
                _toggle_job_tree(job, False)
            return JsonResponse({"enabled": enabled})

        am = AbilityMap.objects.get(job=job)
        tree = _normalise_tree(am.abilities_json)
        ai = int(data["ability_index"])
        if node_type == "ability":
            _set_descendants_enabled(tree[ai], enabled)
        elif node_type == "unit":
            unit = tree[ai]["units"][int(data["unit_index"])]
            _set_descendants_enabled(unit, enabled)
        elif node_type == "point":
            tree[ai]["units"][int(data["unit_index"])]["children"][int(data["point_index"])] ["enabled"] = enabled
        else:
            return JsonResponse({"error": "不支持的节点类型"}, status=400)
        am.abilities_json = tree
        am.save(update_fields=["abilities_json"])
        return JsonResponse({"enabled": enabled, "abilities": tree})
    except (Chain.DoesNotExist, Job.DoesNotExist, AbilityMap.DoesNotExist, IndexError, KeyError, ValueError):
        return JsonResponse({"error": "节点不存在或节点路径无效"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def _toggle_job_tree(job, enabled):
    am = AbilityMap.objects.filter(job=job).first()
    if not am:
        return
    tree = _normalise_tree(am.abilities_json)
    for ability in tree:
        _set_descendants_enabled(ability, enabled)
    am.abilities_json = tree
    am.save(update_fields=["abilities_json"])


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
            return JsonResponse({"error": "新增岗位能力时必须选择所属学院"}, status=400)
        job = Job.objects.get(id=data["job_id"])
        am, _ = AbilityMap.objects.get_or_create(job=job, defaults={"abilities_json": []})
        tree = _normalise_tree(am.abilities_json)
        if parent_type == "job":
            if any(str(item.get("name", "")).strip().casefold() == name.casefold() for item in tree):
                return JsonResponse({"error": "该岗位下已存在同名岗位能力"}, status=400)
            tree.append({"name": name, "college": college, "enabled": job.is_enabled, "units": []})
        else:
            ability = tree[int(data["ability_index"])]
            if parent_type == "ability":
                if any(str(item.get("name", "")).strip().casefold() == name.casefold() for item in ability["units"]):
                    return JsonResponse({"error": "该岗位能力下已存在同名能力单元"}, status=400)
                ability["units"].append({"name": name, "enabled": ability["enabled"], "children": []})
            else:
                unit = ability["units"][int(data["unit_index"])]
                if any(str(item.get("name", "")).strip().casefold() == name.casefold() for item in unit["children"]):
                    return JsonResponse({"error": "该能力单元下已存在同名知识点/技能点"}, status=400)
                unit["children"].append({"name": name, "enabled": unit["enabled"]})
        am.abilities_json = tree
        am.total_abilities = len(tree)
        am.total_skills = sum(len(u.get("children", [])) for a in tree for u in a.get("units", []))
        am.save(update_fields=["abilities_json", "total_abilities", "total_skills"])
        return JsonResponse({"abilities": tree})
    except (Job.DoesNotExist, IndexError, KeyError, ValueError):
        return JsonResponse({"error": "节点路径无效"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def api_ability_text(request, job_id):
    """获取能力图谱原始文本"""
    try:
        am = AbilityMap.objects.filter(job_id=job_id).first()
        if not am:
            return JsonResponse({"text": "尚未生成"})
        return JsonResponse({"text": am.raw_text})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
