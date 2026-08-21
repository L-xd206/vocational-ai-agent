import json

from django.db.models import Prefetch
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.capabilities.models import CapabilityNode
from apps.industry.models import Job
from .services import dispatch_abilities


@csrf_exempt
@require_http_methods(["POST"])
def api_dispatch_abilities(request):
    """将一个岗位下选中的正式岗位能力下发给目标学院。"""

    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)

    try:
        job_id = int(data.get("job_id"))
        ability_ids = list(dict.fromkeys(int(value) for value in data.get("ability_ids", [])))
    except (TypeError, ValueError):
        return JsonResponse({"error": "岗位或岗位能力参数无效"}, status=400)
    if not ability_ids:
        return JsonResponse({"error": "请至少选择一个岗位能力"}, status=400)

    job = Job.objects.filter(pk=job_id, is_enabled=True).first()
    if job is None:
        return JsonResponse({"error": "岗位不存在或已停用"}, status=404)
    point_queryset = CapabilityNode.objects.filter(node_type="point").order_by("sort_order", "id")
    unit_queryset = CapabilityNode.objects.filter(node_type="unit").order_by("sort_order", "id").prefetch_related(
        Prefetch("children", queryset=point_queryset)
    )
    abilities = list(
        CapabilityNode.objects.filter(
            id__in=ability_ids,
            job=job,
            node_type="ability",
            parent__isnull=True,
        )
        .select_related("organization")
        .prefetch_related(Prefetch("children", queryset=unit_queryset))
        .order_by("sort_order", "id")
    )
    if len(abilities) != len(ability_ids):
        return JsonResponse({"error": "部分岗位能力不存在或不属于当前岗位"}, status=400)
    disabled = [ability.name for ability in abilities if not ability.is_enabled]
    if disabled:
        return JsonResponse({"error": f"以下岗位能力已停用，不能下发：{'、'.join(disabled)}"}, status=400)
    unassigned = [ability.name for ability in abilities if ability.organization_id is None]
    if unassigned:
        return JsonResponse({"error": f"以下岗位能力未分配学院，不能下发：{'、'.join(unassigned)}"}, status=400)
    invalid_organizations = [
        ability.name for ability in abilities
        if ability.organization.org_type != "学院" or not ability.organization.is_enabled
    ]
    if invalid_organizations:
        return JsonResponse({"error": f"以下岗位能力的所属学院无效或已停用：{'、'.join(invalid_organizations)}"}, status=400)

    results = dispatch_abilities(
        abilities=abilities,
        created_by=request.user,
    )
    created_count = sum(1 for item in results if item["created"])
    return JsonResponse({
        "ok": True,
        "created_count": created_count,
        "skipped_count": len(results) - created_count,
        "items": results,
    })
