"""学习任务卡试题的查询与维护接口。"""

import json

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.curriculum.models import CourseTreeNode
from apps.curriculum.views import _can_view_course_tree, _require_republish

from .models import CourseQuestion


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
