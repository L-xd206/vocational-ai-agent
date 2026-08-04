"""能力图谱 API"""
import json
import sys
import threading
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from chain.models import Job
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
            return

        # 收集招聘要求
        from crawl.models import JobListing
        reqs = list(JobListing.objects.filter(task=task).values_list("requirements", flat=True))
        reqs = [r for r in reqs if r and len(r) > 10]

        from step3_gen_abilities import gen_ability
        result = gen_ability(job.name, reqs)

        if result and result.get("abilities_text"):
            tree = parse_abilities_to_tree(result["abilities_text"])
            AbilityMap.objects.update_or_create(
                job=job,
                defaults={
                    "abilities_json": tree,
                    "total_abilities": result.get("n_abilities", len(tree)),
                    "total_skills": result.get("n_skills", 0),
                    "raw_text": result["abilities_text"],
                }
            )
    except Exception as e:
        print(f"Ability gen error: {e}")


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

        return JsonResponse({
            "job_name": am.job.name,
            "total_abilities": am.total_abilities,
            "total_skills": am.total_skills,
            "abilities": [{
                "name": a["name"],
                "children": a["children"],
            } for a in am.abilities_json],
            "status": "ready",
            "crawl_status": "completed",
        })

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
