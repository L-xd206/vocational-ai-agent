import json

from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt

from .models import LearningPlan, LearningRecord, PlanDeleteLog


def page_learning_plan(request):
    return render(request, "学习计划.html")


def page_learning_profile(request):
    return render(request, "学习档案.html")


def _current_student(request):
    return getattr(request.user, "student_profile", None)


def _plan_to_dict(p):
    return {
        "id": p.id,
        "name": p.name,
        "course_tree_id": p.course_tree_id,
        "plan_type": p.plan_type,
        "plan_type_display": p.get_plan_type_display(),
        "category": p.category or "",
        "status": p.status,
        "status_display": p.get_status_display(),
        "progress": p.progress,
        "learned_hours": p.learned_hours,
        "total_hours": p.total_hours,
        "deadline": p.deadline.strftime("%Y-%m-%d") if p.deadline else "",
        "teacher": p.teacher or "",
        "can_delete": p.plan_type != LearningPlan.PlanType.SEMESTER,
    }


def _compute_overview(plans):
    doing = sum(1 for p in plans if p.status == LearningPlan.Status.DOING)
    done = sum(1 for p in plans if p.status == LearningPlan.Status.DONE)
    learned = sum(p.learned_hours for p in plans)
    remain = sum(max(0, p.total_hours - p.learned_hours) for p in plans)
    return {
        "current": doing,
        "done": done,
        "learned_hours": learned,
        "remain_hours": remain,
    }


@csrf_exempt
def api_learning_plan_list(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    student = _current_student(request)
    if student is None:
        return JsonResponse({"error": "未关联学生档案"}, status=400)
    if request.method == "POST":
        return api_learning_plan_create(request, student)
    status = request.GET.get("status", "").strip()
    keyword = request.GET.get("keyword", "").strip()
    queryset = LearningPlan.objects.filter(student=student).select_related("course_tree")
    if status and status != "all":
        queryset = queryset.filter(status=status)
    if keyword:
        queryset = queryset.filter(Q(name__icontains=keyword) | Q(category__icontains=keyword))
    plans = list(queryset)
    items = [_plan_to_dict(p) for p in plans]
    return JsonResponse({"ok": True, "plans": items, "overview": _compute_overview(plans)})


@csrf_exempt
def api_learning_plan_create(request, student=None):
    if student is None:
        student = _current_student(request)
        if student is None:
            return JsonResponse({"error": "未关联学生档案"}, status=400)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    name = (data.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "请填写计划名称"}, status=400)
    deadline_str = data.get("deadline") or None
    deadline = parse_date(deadline_str) if deadline_str else None
    plan = LearningPlan.objects.create(
        student=student,
        name=name,
        plan_type=LearningPlan.PlanType.SELF,
        category=(data.get("category") or "").strip() or "自主学习",
        total_hours=int(data.get("total_hours") or 0),
        deadline=deadline,
    )
    return JsonResponse({"ok": True, "plan": _plan_to_dict(plan)}, status=201)


@csrf_exempt
def api_learning_plan_detail(request, plan_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    student = _current_student(request)
    if student is None:
        return JsonResponse({"error": "未关联学生档案"}, status=400)
    plan = LearningPlan.objects.filter(pk=plan_id, student=student).first()
    if plan is None:
        return JsonResponse({"error": "学习计划不存在"}, status=404)
    if request.method == "DELETE":
        if plan.plan_type == LearningPlan.PlanType.SEMESTER:
            return JsonResponse({"error": "学期计划不可删除"}, status=400)
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            data = {}
        reason = (data.get("reason") or "").strip()
        if not reason:
            return JsonResponse({"error": "请填写删除原因"}, status=400)
        PlanDeleteLog.objects.create(
            student=student,
            plan_name=plan.name,
            category=plan.category,
            progress=plan.progress,
            reason=reason,
        )
        plan.delete()
        return JsonResponse({"ok": True})
    return JsonResponse({"error": "不支持的方法"}, status=405)


@csrf_exempt
def api_learning_profile(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    student = _current_student(request)
    if student is None:
        return JsonResponse({"error": "未关联学生档案"}, status=400)
    plans = LearningPlan.objects.filter(student=student)
    records = LearningRecord.objects.filter(student=student).order_by("-created_at")
    student_info = {
        "name": student.name,
        "student_id": student.student_id,
        "major": student.major or "",
        "grade": student.grade or "",
        "class_name": student.class_group.name if student.class_group else "",
    }
    stats = {
        "plan_count": plans.count(),
        "learned_hours": sum(p.learned_hours for p in plans),
        "assessment_count": 0,  # 占位：测评系统未建
    }
    records_data = [{
        "id": r.id,
        "title": r.title,
        "description": r.description or "",
        "tag": r.tag or "",
        "created_at": r.created_at.strftime("%Y-%m-%d"),
    } for r in records]
    return JsonResponse({"ok": True, "student": student_info, "stats": stats, "records": records_data})
