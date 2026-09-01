"""学习任务卡试题的查询与维护接口。"""

import json

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.curriculum.api import get_teachable_course_trees, get_visible_course_trees
from apps.curriculum.models import CourseTreeNode
from apps.curriculum.views import _can_view_course_tree, _require_republish
from apps.organizations.api import get_classes_by_college

from .models import CourseQuestion, TeachingArrangement


def _can_manage(request, node):
    return request.user.is_superuser or node.tree.owner_id == request.user.id


def _serialize(question):
    return {
        "id": question.id,
        "question_type": question.question_type,
        "stem": question.stem,
        "options": question.options,
        "correct_answer": question.correct_answer,
        "analysis": question.analysis,
        "difficulty": question.difficulty,
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_node_questions(request, node_id):
    """获取或整体保存一张任务卡下的试题。"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    node = CourseTreeNode.objects.select_related("tree").filter(
        pk=node_id, node_type="knowledge"
    ).first()
    if node is None:
        return JsonResponse({"error": "学习任务卡不存在"}, status=404)
    if not _can_view_course_tree(request, node.tree):
        return JsonResponse({"error": "无权查看该课程试题"}, status=403)
    if request.method == "GET":
        return JsonResponse({"node_id": node.id, "node_name": node.name, "questions": [
            _serialize(question) for question in node.questions.all()
        ]})
    if not _can_manage(request, node):
        return JsonResponse({"error": "仅课程负责人可以编辑试题"}, status=403)
    try:
        payload = json.loads(request.body or "{}")
        items = payload.get("questions")
        if not isinstance(items, list):
            raise ValueError("questions 必须是数组")
    except (json.JSONDecodeError, ValueError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    allowed_types = {item[0] for item in CourseQuestion.QUESTION_TYPES}
    allowed_difficulties = {item[0] for item in CourseQuestion.DIFFICULTIES}
    if len(items) > 50:
        return JsonResponse({"error": "单张学习任务卡最多保存 50 道试题"}, status=400)
    try:
        with transaction.atomic():
            is_post_publish_change = node.tree.is_published or node.tree.has_unpublished_changes
            republish_required = _require_republish(node.tree, request)
            node.tree.has_manual_edits = True
            node.tree.save(update_fields=["has_manual_edits", "updated_at"])
            if is_post_publish_change and not node.changed_since_publish:
                node.changed_since_publish = True
                node.save(update_fields=["changed_since_publish", "updated_at"])
            node.questions.all().delete()
            created = []
            stems = set()
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    raise ValueError("试题格式无效")
                question_type = item.get("question_type")
                if question_type not in allowed_types:
                    raise ValueError("题型无效")
                stem = str(item.get("stem") or "").strip()
                if not stem:
                    raise ValueError("题目内容不能为空")
                stem_key = " ".join(stem.casefold().split())
                if stem_key in stems:
                    raise ValueError("同一任务卡内不能保存重复题目")
                stems.add(stem_key)
                options = item.get("options") or []
                answer = item.get("correct_answer") or []
                if not isinstance(options, list) or not isinstance(answer, list):
                    raise ValueError("选项和答案必须是数组")
                if any(len(str(value).strip()) > 500 for value in options):
                    raise ValueError("单个选项不能超过 500 字")
                if any(len(str(value).strip()) > 1000 for value in answer):
                    raise ValueError("单个参考答案不能超过 1000 字")
                question = CourseQuestion(
                    node=node,
                    question_type=question_type,
                    stem=stem,
                    options=[str(value).strip() for value in options if str(value).strip()],
                    correct_answer=[str(value).strip() for value in answer if str(value).strip()],
                    analysis=str(item.get("analysis") or "").strip(),
                    difficulty=item.get("difficulty") if item.get("difficulty") in allowed_difficulties else "medium",
                    sort_order=index,
                    created_by=request.user,
                )
                question.full_clean()
                question.save()
                created.append(_serialize(question))
    except (ValidationError, ValueError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse({"ok": True, "questions": created, "republish_required": republish_required})


# ===== 教学安排 =====

def page_teaching_arrangement(request):
    return render(request, "教学安排.html")


def _arrangement_to_dict(arr):
    classes = list(arr.classes.all())
    return {
        "id": arr.id,
        "course_tree_id": arr.course_tree_id,
        "course_name": arr.course_tree.name,
        "course_type": arr.course_tree.get_course_type_display(),
        "hours": arr.course_tree.total_hours,
        "credits": float(arr.course_tree.credits),
        "semester": arr.semester,
        "class_ids": [c.id for c in classes],
        "class_names": [c.name for c in classes],
        "student_count": sum(len(c.students.all()) for c in classes),
        "created_at": arr.created_at.strftime("%Y-%m-%d"),
    }


def _compute_stats(arrangements):
    class_ids = set()
    students = 0
    for arr in arrangements:
        for c in arr.classes.all():
            class_ids.add(c.id)
            students += len(c.students.all())
    return {
        "course_count": len(arrangements),
        "class_count": len(class_ids),
        "student_count": students,
    }


@csrf_exempt
def api_teaching_course_options(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    trees = get_teachable_course_trees(request.user)
    items = [{
        "id": t.id,
        "name": t.name,
        "hours": t.total_hours,
        "credits": float(t.credits),
        "course_type": t.course_type,
        "course_type_display": t.get_course_type_display(),
    } for t in trees]
    return JsonResponse({"ok": True, "courses": items})


@csrf_exempt
def api_teaching_class_options(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    profile = getattr(request.user, "profile", None)
    if not profile or not profile.organization_id:
        return JsonResponse({"ok": True, "classes": []})
    classes = get_classes_by_college(profile.organization_id).prefetch_related("students")
    items = [{
        "id": c.id,
        "name": c.name,
        "grade": c.grade,
        "student_count": len(c.students.all()),
    } for c in classes]
    return JsonResponse({"ok": True, "classes": items})


@csrf_exempt
def api_teaching_arrangement_list(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    if request.method == "POST":
        return api_teaching_arrangement_create(request)
    semester = request.GET.get("semester", "").strip()
    keyword = request.GET.get("keyword", "").strip()
    queryset = TeachingArrangement.objects.filter(teacher=request.user).select_related("course_tree")
    if semester and semester != "all":
        queryset = queryset.filter(semester=semester)
    if keyword:
        queryset = queryset.filter(
            Q(course_tree__name__icontains=keyword) | Q(classes__name__icontains=keyword)
        ).distinct()
    arrangements = list(queryset.prefetch_related("classes__students"))
    items = [_arrangement_to_dict(arr) for arr in arrangements]
    stats = _compute_stats(arrangements)
    return JsonResponse({"ok": True, "arrangements": items, "stats": stats})


@csrf_exempt
def api_teaching_arrangement_create(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    course_tree_id = data.get("course_tree_id")
    semester = (data.get("semester") or "").strip()
    class_ids = data.get("class_ids") or []
    if not course_tree_id or not semester or not class_ids:
        return JsonResponse({"error": "请选择课程、学期和班级"}, status=400)
    course_tree = get_teachable_course_trees(request.user).filter(pk=course_tree_id).first()
    if course_tree is None:
        return JsonResponse({"error": "课程不可用或不存在"}, status=400)
    profile = getattr(request.user, "profile", None)
    if not profile or not profile.organization_id:
        return JsonResponse({"error": "未关联学院，无法安排教学"}, status=400)
    classes = get_classes_by_college(profile.organization_id).filter(pk__in=class_ids)
    if classes.count() != len(set(class_ids)):
        return JsonResponse({"error": "包含无效班级"}, status=400)
    arr, created = TeachingArrangement.objects.get_or_create(
        teacher=request.user,
        course_tree=course_tree,
        semester=semester,
    )
    arr.classes.add(*classes)
    return JsonResponse({"ok": True, "arrangement": _arrangement_to_dict(arr), "created": created}, status=201 if created else 200)


@csrf_exempt
def api_teaching_arrangement_detail(request, arrangement_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    arr = TeachingArrangement.objects.filter(pk=arrangement_id, teacher=request.user).first()
    if arr is None:
        return JsonResponse({"error": "教学安排不存在"}, status=404)
    if request.method == "PATCH":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "无效的 JSON"}, status=400)
        class_ids = data.get("class_ids") or []
        if not class_ids:
            return JsonResponse({"error": "请至少保留一个班级"}, status=400)
        profile = getattr(request.user, "profile", None)
        if not profile or not profile.organization_id:
            return JsonResponse({"error": "未关联学院"}, status=400)
        classes = get_classes_by_college(profile.organization_id).filter(pk__in=class_ids)
        if classes.count() != len(set(class_ids)):
            return JsonResponse({"error": "包含无效班级"}, status=400)
        arr.classes.set(classes)
        return JsonResponse({"ok": True, "arrangement": _arrangement_to_dict(arr)})
    return JsonResponse({"error": "不支持的方法"}, status=405)


@csrf_exempt
def api_teaching_arrangement_members(request, arrangement_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    arr = TeachingArrangement.objects.filter(
        pk=arrangement_id, teacher=request.user,
    ).prefetch_related("classes__students").first()
    if arr is None:
        return JsonResponse({"error": "教学安排不存在"}, status=404)
    members = []
    for cls in arr.classes.all():
        members.append({
            "class_id": cls.id,
            "class_name": cls.name,
            "grade": cls.grade,
            "students": [{"name": s.name, "student_id": s.student_id} for s in cls.students.all()],
        })
    return JsonResponse({"ok": True, "members": members})


# ===== 课程试题检索 =====

def page_question_bank(request):
    return render(request, "试题库.html")


def _question_to_dict(q):
    chapter = q.node.parent
    course = q.node.tree
    path_parts = [course.name, chapter.name if chapter else "", q.node.name]
    return {
        "id": q.id,
        "question_type": q.question_type,
        "question_type_display": q.get_question_type_display(),
        "stem": q.stem,
        "options": q.options,
        "correct_answer": q.correct_answer,
        "analysis": q.analysis,
        "difficulty": q.difficulty,
        "node_id": q.node_id,
        "node_name": q.node.name,
        "chapter_name": chapter.name if chapter else "",
        "course_id": course.id,
        "course_name": course.name,
        "path": " / ".join([p for p in path_parts if p]),
        "updated_at": q.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
    }


@csrf_exempt
def api_question_course_options(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    trees = get_visible_course_trees(request.user)
    items = [{"id": t.id, "name": t.name} for t in trees]
    return JsonResponse({"ok": True, "courses": items})


@csrf_exempt
def api_question_list(request):
    """课程试题列表（跨课程/章节/知识点检索）。"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    keyword = request.GET.get("keyword", "").strip()
    question_type = request.GET.get("question_type", "").strip()
    course_tree_id = request.GET.get("course_tree_id", "").strip()
    trees = get_visible_course_trees(request.user)
    queryset = CourseQuestion.objects.filter(node__tree__in=trees).select_related(
        "node", "node__parent", "node__tree",
    )
    if keyword:
        queryset = queryset.filter(
            Q(stem__icontains=keyword)
            | Q(node__name__icontains=keyword)
            | Q(node__parent__name__icontains=keyword)
            | Q(node__tree__name__icontains=keyword)
        )
    if question_type:
        queryset = queryset.filter(question_type=question_type)
    if course_tree_id:
        queryset = queryset.filter(node__tree_id=course_tree_id)
    total = queryset.count()
    page = int(request.GET.get("page", 1) or 1)
    page_size = int(request.GET.get("page_size", 10) or 10)
    offset = (page - 1) * page_size
    items = [_question_to_dict(q) for q in queryset[offset:offset + page_size]]
    return JsonResponse({"ok": True, "questions": items, "total": total})
