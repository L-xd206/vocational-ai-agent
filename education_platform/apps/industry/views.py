"""产业链 + 岗位 API"""
import json
import os
from django.shortcuts import render
from django.http import JsonResponse
from django.db.models import Prefetch
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from .models import Chain, Job
from .services import normalize_keywords, validate_job_name


# 🔧 确保可以 import 同目录下的 step1 脚本
def page_chain_list(request):
    """产业链管理页面"""
    return render(request, "能力图谱库.html")


# ========== API ==========

@csrf_exempt
def api_chain_list(request):
    """获取当前可用于业务流程的产业链和岗位。"""
    active_jobs = Job.objects.filter(is_enabled=True)
    chains = (
        Chain.objects.filter(is_enabled=True)
        .prefetch_related(Prefetch("jobs", queryset=active_jobs))
        .order_by("id")
    )
    return JsonResponse({
        "chains": [{
            "id": c.id, "name": c.name, "description": c.description,
            "enabled": c.is_enabled,
            "job_count": c.jobs.count(),
            "created_at": c.created_at.strftime("%Y-%m-%d %H:%M"),
        } for c in chains]
    })


@csrf_exempt
def api_chain_detail(request, chain_id):
    """获取已启用产业链详情（仅含可用岗位）。"""
    try:
        chain = (
            Chain.objects.filter(is_enabled=True)
            .prefetch_related(Prefetch("jobs", queryset=Job.objects.filter(is_enabled=True)))
            .get(id=chain_id)
        )
    except Chain.DoesNotExist:
        return JsonResponse({"error": "产业链不存在"}, status=404)

    return JsonResponse({
        "id": chain.id,
        "name": chain.name,
        "description": chain.description,
        "enabled": chain.is_enabled,
        "jobs": [{
            "id": j.id, "name": j.name, "aliases": j.aliases,
            "search_keywords": j.search_keywords, "is_confirmed": j.is_confirmed,
            "enabled": j.is_enabled,
        } for j in chain.jobs.all()],
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_chain_create(request):
    """新增产业链 + AI 生成岗位"""
    chain = None
    try:
        data = json.loads(request.body)
        chain_name = data.get("name", "").strip()
        if not chain_name:
            return JsonResponse({"error": "请输入产业链名称"}, status=400)

        # 1. 创建产业链
        chain, created = Chain.objects.get_or_create(name=chain_name)

        if not created:
            return JsonResponse({"error": f"产业链 [{chain_name}] 已存在"}, status=400)

        # 2. 调用 AI 生成岗位
        from ai.services import generate_jobs
        ai_result = generate_jobs(chain_name)

        if not ai_result or not ai_result.get("jobs"):
            failed_chain_id = chain.id
            chain.delete()
            return JsonResponse({"error": "AI生成失败", "chain_id": failed_chain_id}, status=500)

        # 3. 保存岗位
        saved_jobs = []
        seen_names = set()
        for job_data in ai_result.get("jobs", []):
            try:
                job_name = validate_job_name(job_data.get("name"))
                keywords = normalize_keywords(job_data.get("search_keywords", []))
            except ValueError:
                continue
            if job_name.casefold() in seen_names:
                continue
            seen_names.add(job_name.casefold())
            job = Job.objects.create(
                chain=chain,
                name=job_name,
                aliases=job_data.get("aliases", []),
                search_keywords=keywords,
                is_confirmed=False,
            )
            saved_jobs.append({"id": job.id, "name": job.name, "search_keywords": job.search_keywords})

        if not saved_jobs:
            chain.delete()
            return JsonResponse({"error": "AI未生成有效岗位或搜索关键词"}, status=500)

        return JsonResponse({
            "chain_id": chain.id,
            "name": chain.name,
            "jobs": saved_jobs,
        })

    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的JSON"}, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        if chain is not None and chain.pk:
            chain.delete()
        return JsonResponse({"error": str(e), "traceback": traceback.format_exc()}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_job_update(request, job_id):
    """更新岗位（手动调整别名、关键词、确认状态）"""
    try:
        job = Job.objects.get(id=job_id)
        data = json.loads(request.body)

        if "name" in data:
            data["name"] = validate_job_name(data["name"])
        if "search_keywords" in data:
            data["search_keywords"] = normalize_keywords(data["search_keywords"])
        elif not job.search_keywords:
            raise ValueError("请至少填写3个不同的搜索关键词")
        if "aliases" in data:
            job.aliases = data["aliases"]
        if "search_keywords" in data:
            job.search_keywords = data["search_keywords"]
        if "is_confirmed" in data:
            job.is_confirmed = data["is_confirmed"]
        if "name" in data:
            job.name = data["name"]

        job.save()
        return JsonResponse({"id": job.id, "name": job.name, "is_confirmed": job.is_confirmed})

    except Job.DoesNotExist:
        return JsonResponse({"error": "岗位不存在"}, status=404)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
def api_chain_delete(request, chain_id):
    """删除产业链"""
    try:
        chain = Chain.objects.get(id=chain_id)
        chain.delete()
        return JsonResponse({"deleted": True})
    except Chain.DoesNotExist:
        return JsonResponse({"error": "产业链不存在"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_job_create(request):
    """手动新增岗位（不调用AI）"""
    try:
        data = json.loads(request.body)
        chain_id = data.get("chain_id")
        job_name = validate_job_name(data.get("name"))
        keywords = normalize_keywords(data.get("search_keywords", []))

        chain = Chain.objects.get(id=chain_id)
        if Job.objects.filter(chain=chain, name__iexact=job_name).exists():
            return JsonResponse({"error": "该产业链下已存在同名岗位"}, status=400)
        job = Job.objects.create(chain=chain, name=job_name, search_keywords=keywords, is_confirmed=False)
        return JsonResponse({"id": job.id, "name": job.name, "search_keywords": job.search_keywords})
    except (Chain.DoesNotExist, ValueError) as e:
        if isinstance(e, ValueError):
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"error": "产业链不存在"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
def api_job_delete(request, job_id):
    """删除岗位"""
    try:
        job = Job.objects.get(id=job_id)
        job.delete()
        return JsonResponse({"deleted": True})
    except Job.DoesNotExist:
        return JsonResponse({"error": "岗位不存在"}, status=404)
