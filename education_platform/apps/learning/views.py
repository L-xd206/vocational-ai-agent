import json

from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt

from apps.curriculum.models import CourseTree, CourseTreeNode
from apps.teaching.models import CourseQuestion

from .models import (
    AssessmentAnswer, AssessmentRun, LearningPlan, LearningProgress, LearningRecord,
    PlanCourse, PlanDeleteLog, PlanPoint,
)
from .services import (
    add_course_to_plan,
    analyze_student_weakness,
    build_placement_test,
    chat_reply,
    create_plan_from_courses,
    grade_placement_test,
    list_course_library,
    list_job_options,
    pick_questions,
    plan_live_stats,
    plan_point_ids,
    recommend_from_chat,
    submit_run,
)


def page_learning_plan(request):
    return render(request, "学习计划.html")


def page_learning_profile(request):
    return render(request, "学习档案.html")


def page_learning_plan_content(request):
    return render(request, "计划详情.html")


def page_plan_adjust(request):
    return render(request, "计划调整.html")


def page_plan_create(request):
    return render(request, "新增计划.html")


def _current_student(request):
    return getattr(request.user, "student_profile", None)


def _plan_to_dict(p, live=None):
    live = live or {}
    return {
        "id": p.id,
        "name": p.name,
        "plan_type": p.plan_type,
        "plan_type_display": p.get_plan_type_display(),
        "category": p.category or "",
        "status": p.status,
        "status_display": p.get_status_display(),
        "progress": live.get("progress", p.progress),
        "learned_hours": live.get("learned_hours", p.learned_hours),
        "total_hours": live.get("total_hours", p.total_hours),
        "total_points": live.get("total_points", 0),
        "done_points": live.get("done_points", 0),
        "course_count": live.get("course_count", 0),
        "deadline": p.deadline.strftime("%Y-%m-%d") if p.deadline else "",
        "teacher": p.teacher or "",
        "can_delete": p.plan_type != LearningPlan.PlanType.SEMESTER,
    }


def _compute_overview(lives):
    doing = sum(1 for l in lives if l["status"] == LearningPlan.Status.DOING)
    done = sum(1 for l in lives if l["status"] == LearningPlan.Status.DONE)
    learned = sum(l["learned_hours"] for l in lives)
    remain = sum(max(0, l["total_hours"] - l["learned_hours"]) for l in lives)
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
    queryset = LearningPlan.objects.filter(student=student)
    if status and status != "all":
        queryset = queryset.filter(status=status)
    if keyword:
        queryset = queryset.filter(Q(name__icontains=keyword) | Q(category__icontains=keyword))
    plans = list(queryset)
    items = []
    lives = []
    for p in plans:
        stat = plan_live_stats(student, p)
        live = {**stat, "course_count": p.courses.count(), "status": p.status}
        items.append(_plan_to_dict(p, live))
        lives.append(live)
    return JsonResponse({"ok": True, "plans": items, "overview": _compute_overview(lives)})


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
def api_course_library(request):
    """课程库（新增计划向导用）：所有已发布课程 → 章 → 知识点。"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    return JsonResponse({"ok": True, "library": list_course_library()})


@csrf_exempt
def api_learning_plan_from_courses(request):
    """按课程库勾选批量新建学习计划。body: {name?, plan_type?, category?, selections:[{course_id, node_ids?}]}"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    student = _current_student(request)
    if student is None:
        return JsonResponse({"error": "未关联学生档案"}, status=400)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    selections = data.get("selections") or []
    name = (data.get("name") or "").strip()
    plan_type = (data.get("plan_type") or "self").strip()
    category = (data.get("category") or "自主学习").strip()
    try:
        plan, total_points = create_plan_from_courses(
            student, name, selections, plan_type=plan_type, category=category,
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse({
        "ok": True, "plan_id": plan.id, "total_points": total_points,
        "plan": _plan_to_dict(plan),
    }, status=201)


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
        "assessment_count": AssessmentRun.objects.filter(student=student).count(),
    }
    records_data = [{
        "id": r.id,
        "title": r.title,
        "description": r.description or "",
        "tag": r.tag or "",
        "created_at": r.created_at.strftime("%Y-%m-%d"),
    } for r in records]
    return JsonResponse({"ok": True, "student": student_info, "stats": stats, "records": records_data})


# ===== 学习进度 + 计划详情 =====

def _node_to_dict(node, completed):
    return {
        "id": node.id,
        "name": node.name,
        "task_description": node.task_description or "",
        "work_scenario": node.work_scenario or "",
        "operation_steps": node.operation_steps or [],
        "safety_points": node.safety_points or [],
        "resource_links": node.resource_links or [],
        "completed": completed,
    }


@csrf_exempt
def api_learning_plan_content(request, plan_id):
    """计划详情：多课程章节目录 + 学习内容 + 完成状态 + 进度。"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    student = _current_student(request)
    if student is None:
        return JsonResponse({"error": "未关联学生档案"}, status=400)
    plan = LearningPlan.objects.filter(pk=plan_id, student=student).first()
    if plan is None:
        return JsonResponse({"error": "学习计划不存在"}, status=404)
    completed_ids = set(LearningProgress.objects.filter(student=student).values_list("node_id", flat=True))

    courses_out = []
    total_points = 0
    completed_count = 0
    for pc in plan.courses.all().order_by("sort_order", "id"):
        tree = pc.course_tree
        selected_ids = set(pc.points.values_list("node_id", flat=True))
        # 树内章节
        chapters_out = []
        for ch in CourseTreeNode.objects.filter(tree=tree, node_type="chapter").order_by("sort_order", "id"):
            ch_points = [n for n in CourseTreeNode.objects.filter(
                tree=tree, node_type="knowledge", parent_id=ch.id,
            ).order_by("sort_order", "id") if n.id in selected_ids]
            if not ch_points:
                continue
            points_data = [_node_to_dict(p, p.id in completed_ids) for p in ch_points]
            chapters_out.append({"id": ch.id, "name": ch.name, "points": points_data})
            total_points += len(points_data)
            completed_count += sum(1 for p in points_data if p["completed"])
        courses_out.append({
            "course_id": tree.id,
            "course_name": tree.name,
            "plan_course_id": pc.id,
            "chapters": chapters_out,
        })
    progress = round(completed_count / total_points * 100) if total_points else 0
    return JsonResponse({
        "ok": True,
        "plan": {
            "id": plan.id,
            "name": plan.name,
            "plan_type": plan.plan_type,
            "plan_type_display": plan.get_plan_type_display(),
            "status": plan.status,
            "teacher": plan.teacher or "",
            "total_hours": plan.total_hours,
            "learned_hours": plan.learned_hours,
            "progress": progress,
        },
        "courses": courses_out,
        "completed_count": completed_count,
        "total_points": total_points,
    })


@csrf_exempt
def api_learning_plan_progress(request, plan_id):
    """标记/取消知识点完成（无门槛，学生自行标记）。"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    student = _current_student(request)
    if student is None:
        return JsonResponse({"error": "未关联学生档案"}, status=400)
    plan = LearningPlan.objects.filter(pk=plan_id, student=student).first()
    if plan is None:
        return JsonResponse({"error": "学习计划不存在"}, status=404)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    node_id = data.get("node_id")
    completed = data.get("completed", True)
    node = CourseTreeNode.objects.filter(pk=node_id, node_type="knowledge").first()
    if node is None:
        return JsonResponse({"error": "知识点不存在"}, status=404)
    if completed:
        LearningProgress.objects.get_or_create(student=student, node=node)
    else:
        LearningProgress.objects.filter(student=student, node=node).delete()
    return JsonResponse({"ok": True})


# ===== 测评系统 =====

def _question_public(q):
    """抽题展示用（不含正确答案）。"""
    return {
        "id": q.id,
        "question_type": q.question_type,
        "stem": q.stem,
        "options": q.options or [],
        "difficulty": q.difficulty,
    }


def _resolve_scope_ctx(student, plan, scope, node_id):
    """根据 scope + plan 确定测评的展示上下文。返回 (title, node)。"""
    node = CourseTreeNode.objects.filter(pk=node_id).first() if node_id else None
    scope_label = AssessmentRun.Scope(scope).label if scope in AssessmentRun.Scope.values else scope
    if scope == AssessmentRun.Scope.POINT and node:
        title = f"{node.name} · 随堂练习"
    elif scope == AssessmentRun.Scope.CHAPTER and node:
        title = f"{node.name} · 章节测验"
    elif plan:
        title = f"{plan.name} · 课程综合测验"
    else:
        title = f"{scope_label}测评"
    return title, node


@csrf_exempt
def api_assessment_start(request):
    """按范围抽题并返回（不建 run，提交时才落库）。"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    student = _current_student(request)
    if student is None:
        return JsonResponse({"error": "未关联学生档案"}, status=400)
    scope = request.GET.get("scope", "").strip()
    plan_id = request.GET.get("plan_id", "").strip()
    node_id = request.GET.get("node_id", "").strip()
    if scope not in AssessmentRun.Scope.values:
        return JsonResponse({"error": "测评范围无效"}, status=400)
    plan = LearningPlan.objects.filter(pk=plan_id, student=student).first() if plan_id else None
    if plan is None and scope in (AssessmentRun.Scope.CHAPTER, AssessmentRun.Scope.COURSE):
        return JsonResponse({"error": "学习计划不存在"}, status=404)
    title, node = _resolve_scope_ctx(student, plan, scope, node_id)
    if node is None and scope in (AssessmentRun.Scope.POINT, AssessmentRun.Scope.CHAPTER):
        return JsonResponse({"error": "缺少测评节点"}, status=400)
    questions = pick_questions(
        scope, plan=plan,
        node_id=node.id if node else None,
    )
    if not questions:
        return JsonResponse({"error": "该范围暂无可用题目"}, status=400)
    return JsonResponse({
        "ok": True,
        "run_key": {"plan_id": plan.id if plan else None, "scope": scope, "node_id": node.id if node else None},
        "title": title,
        "scope_label": AssessmentRun.Scope(scope).label,
        "questions": [_question_public(q) for q in questions],
        "total": len(questions),
    })


@csrf_exempt
def api_assessment_submit(request):
    """提交作答：按题重新抽对应范围题目，用快照判分并落库。"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    student = _current_student(request)
    if student is None:
        return JsonResponse({"error": "未关联学生档案"}, status=400)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    scope = (data.get("scope") or "").strip()
    plan_id = data.get("plan_id")
    node_id = data.get("node_id")
    answers = data.get("answers") or []
    if scope not in AssessmentRun.Scope.values:
        return JsonResponse({"error": "测评范围无效"}, status=400)
    plan = LearningPlan.objects.filter(pk=plan_id, student=student).first() if plan_id else None
    title, node = _resolve_scope_ctx(student, plan, scope, node_id)
    if not isinstance(answers, list) or not answers:
        return JsonResponse({"error": "请完成全部题目再提交"}, status=400)
    # 用学生作答的题目 id 取题判分（与展示题一致，避免重抽随机题错位）
    submitted_ids = [a.get("question_id") for a in answers]
    questions = list(CourseQuestion.objects.filter(id__in=submitted_ids))
    if not questions:
        return JsonResponse({"error": "未找到对应题目"}, status=400)
    run, results = submit_run(
        student=student, plan=plan, scope=scope, node=node,
        title=title, answers=answers, questions=questions,
    )
    return JsonResponse({"ok": True, "run": {
        "id": run.id, "title": run.title, "score": run.score,
        "total": run.total, "correct_count": run.correct_count,
        "wrong_count": run.wrong_count,
    }})


@csrf_exempt
def api_assessment_history(request):
    """当前学生的测评历史（学习档案用）。"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    student = _current_student(request)
    if student is None:
        return JsonResponse({"error": "未关联学生档案"}, status=400)
    runs = AssessmentRun.objects.filter(student=student).select_related("plan", "node")
    return JsonResponse({"ok": True, "runs": [{
        "id": r.id,
        "title": r.title,
        "scope": r.scope,
        "score": r.score,
        "total": r.total,
        "correct_count": r.correct_count,
        "wrong_count": r.wrong_count,
        "submitted_at": r.submitted_at.strftime("%Y-%m-%d %H:%M"),
    } for r in runs]})


@csrf_exempt
def api_assessment_detail(request, run_id):
    """测评详情：逐题 + 学生答案 + 对错（学习档案试题详情/回看用）。"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    student = _current_student(request)
    if student is None:
        return JsonResponse({"error": "未关联学生档案"}, status=400)
    run = AssessmentRun.objects.filter(pk=run_id, student=student).prefetch_related(
        "answers__question", "answers__node",
    ).first()
    if run is None:
        return JsonResponse({"error": "测评不存在"}, status=404)
    # 从答案明细取题目（连同正确信息）
    items = []
    for ans in run.answers.select_related("question", "node").all():
        q = ans.question
        items.append({
            "question_id": q.id,
            "stem": q.stem,
            "options": q.options or [],
            "question_type": q.question_type,
            "chosen": ans.chosen or [],
            "correct_answer": q.correct_answer,
            "is_correct": ans.is_correct,
            "node_name": ans.node.name if ans.node else "",
        })
    return JsonResponse({
        "ok": True,
        "run": {
            "id": run.id, "title": run.title, "scope": run.scope,
            "score": run.score, "total": run.total,
            "correct_count": run.correct_count, "wrong_count": run.wrong_count,
            "submitted_at": run.submitted_at.strftime("%Y-%m-%d %H:%M"),
        },
        "items": items,
    })


# ===== 薄弱分析 =====

@csrf_exempt
def api_ai_weakness(request, plan_id):
    """AI 薄弱项分析：某学习计划下学生的薄弱知识点。"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    student = _current_student(request)
    if student is None:
        return JsonResponse({"error": "未关联学生档案"}, status=400)
    plan = LearningPlan.objects.filter(pk=plan_id, student=student).first()
    if plan is None:
        return JsonResponse({"error": "学习计划不存在"}, status=404)
    result = analyze_student_weakness(student, plan)
    return JsonResponse({"ok": True, **result})


# ===== 计划调整（多课程 + 知识点）=====

def _plan_course_out(pc, completed_ids):
    """单个 PlanCourse 的结构化输出（课程 → 章 → 已选知识点）。"""
    selected_ids = set(pc.points.values_list("node_id", flat=True))
    chapters = []
    nodes = list(CourseTreeNode.objects.filter(tree=pc.course_tree).order_by("sort_order", "id"))
    for ch in [n for n in nodes if n.node_type == "chapter"]:
        pts = [n for n in nodes if n.node_type == "knowledge" and n.parent_id == ch.id and n.id in selected_ids]
        if not pts:
            continue
        chapters.append({
            "chapter_id": ch.id, "chapter_name": ch.name,
            "points": [_node_to_dict(p, p.id in completed_ids) for p in pts],
        })
    return {
        "plan_course_id": pc.id,
        "course_id": pc.course_tree_id,
        "course_name": pc.course_tree.name,
        "chapters": chapters,
    }


@csrf_exempt
def api_plan_adjust(request, plan_id):
    """计划调整页数据：当前计划课程 + 薄弱项 + 课程库候选（含 in_plan 标记）。"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    student = _current_student(request)
    if student is None:
        return JsonResponse({"error": "未关联学生档案"}, status=400)
    plan = LearningPlan.objects.filter(pk=plan_id, student=student).prefetch_related("courses__course_tree").first()
    if plan is None:
        return JsonResponse({"error": "学习计划不存在"}, status=404)
    if request.method == "POST":
        return api_plan_adjust_save(request, student, plan)

    completed_ids = set(LearningProgress.objects.filter(student=student).values_list("node_id", flat=True))
    plan_point_set = set(plan_point_ids(plan))
    plan_courses = [_plan_course_out(pc, completed_ids) for pc in plan.courses.all().order_by("sort_order", "id")]

    # 薄弱项建议
    weak_points = analyze_student_weakness(student, plan).get("weak_points", [])

    # 课程库候选（所有已发布课程知识点，标记是否已在计划）
    library = []
    for tree in CourseTree.objects.filter(is_published=True).order_by("name", "id"):
        chapters = []
        nodes = list(CourseTreeNode.objects.filter(tree=tree).order_by("sort_order", "id"))
        for ch in [n for n in nodes if n.node_type == "chapter"]:
            points = [n for n in nodes if n.node_type == "knowledge" and n.parent_id == ch.id]
            if not points:
                continue
            chapters.append({
                "chapter_id": ch.id, "chapter_name": ch.name,
                "points": [{
                    "id": p.id, "name": p.name,
                    "in_plan": p.id in plan_point_set,
                } for p in points],
            })
        library.append({"course_id": tree.id, "course_name": tree.name, "chapters": chapters})

    return JsonResponse({
        "ok": True,
        "plan": {"id": plan.id, "name": plan.name, "plan_type": plan.plan_type},
        "plan_courses": plan_courses,
        "weak_points": weak_points,
        "library": library,
    })


@csrf_exempt
def api_plan_adjust_save(request, student, plan):
    """计划调整写操作：add/remove 课程或知识点、course 排序。"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    action = (data.get("action") or "").strip()

    if action == "add_course":
        tree = CourseTree.objects.filter(pk=data.get("course_id"), is_published=True).first()
        if tree is None:
            return JsonResponse({"error": "课程不存在"}, status=400)
        plan_course, added = add_course_to_plan(plan, tree)
        return JsonResponse({"ok": True, "plan_course_id": plan_course.id, "added": added})

    if action == "remove_course":
        PlanCourse.objects.filter(plan=plan, course_tree_id=data.get("course_id")).delete()
        return JsonResponse({"ok": True})

    if action in ("add_point", "remove_point"):
        node_id = data.get("node_id")
        node = CourseTreeNode.objects.filter(pk=node_id, node_type="knowledge").first()
        if node is None:
            return JsonResponse({"error": "知识点不存在"}, status=404)
        if action == "add_point":
            # 加入某知识点：确保其课程在计划内，再把该点挂上去
            plan_course, _ = PlanCourse.objects.get_or_create(
                plan=plan, course_tree_id=node.tree_id,
                defaults={"sort_order": plan.courses.count()},
            )
            PlanPoint.objects.get_or_create(
                plan_course=plan_course, node=node,
                defaults={"sort_order": plan_course.points.count()},
            )
        else:
            PlanPoint.objects.filter(plan_course__plan=plan, node_id=node_id).delete()
        return JsonResponse({"ok": True})

    if action == "move_course":
        course_id = data.get("course_id")
        direction = data.get("direction")  # up / down
        ordered = list(plan.courses.order_by("sort_order", "id"))
        idx = next((i for i, pc in enumerate(ordered) if pc.course_tree_id == course_id), None)
        if idx is None:
            return JsonResponse({"error": "课程不在计划中"}, status=400)
        target = idx - 1 if direction == "up" else idx + 1
        if target < 0 or target >= len(ordered):
            return JsonResponse({"ok": True})  # 已在边界
        ordered[idx], ordered[target] = ordered[target], ordered[idx]
        for i, pc in enumerate(ordered):
            PlanCourse.objects.filter(pk=pc.pk).update(sort_order=i)
        return JsonResponse({"ok": True})

    return JsonResponse({"error": "无效的操作"}, status=400)


# ===== 新增计划向导（按岗位 / 按课程 / AI 目标推荐 / 摸底）=====

@csrf_exempt
def api_job_options(request):
    """按岗位创建：返回有课程关联的岗位列表。"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    return JsonResponse({"ok": True, "jobs": list_job_options()})


@csrf_exempt
def api_ai_chat(request):
    """AI 目标推荐的多轮对话回话。body: {message, history:[{role,text}]}"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    message = (data.get("message") or "").strip()
    history = data.get("history") or []
    if not message:
        return JsonResponse({"error": "请先输入内容"}, status=400)
    return JsonResponse({"ok": True, "reply": chat_reply(message, history)})


@csrf_exempt
def api_ai_plan_from_chat(request):
    """根据聊天历史匹配课程。body: {history:[{role,text}]}"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    history = data.get("history") or []
    if not any(m.get("role") == "user" for m in history):
        return JsonResponse({"error": "请先和 AI 聊聊学习目标"}, status=400)
    result = recommend_from_chat(history)
    return JsonResponse({"ok": True, **result})


@csrf_exempt
def api_placement_test(request):
    """摸底自测：按课程抽单选真题。body: {course_ids:[..]}"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    course_ids = data.get("course_ids") or []
    questions = build_placement_test(course_ids)
    if not questions:
        return JsonResponse({"error": "所选课程暂无可用题目，请改用 0 基础学习"}, status=400)
    return JsonResponse({"ok": True, "questions": questions, "total": len(questions)})


@csrf_exempt
def api_placement_submit(request):
    """提交摸底作答，返回精简+排序后的推荐课程。body: {course_ids, answered:[{question_id, chosen_index}]}"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    course_ids = data.get("course_ids") or []
    answered = data.get("answered") or []
    if not answered:
        return JsonResponse({"error": "请完成全部题目再提交"}, status=400)
    result = grade_placement_test(course_ids, answered)
    return JsonResponse({"ok": True, **result})
