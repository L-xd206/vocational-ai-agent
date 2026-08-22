import json
import threading
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.cache import add_never_cache_headers
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.capabilities.models import CapabilityNode
from apps.industry.models import Job
from apps.resources.models import Textbook
from apps.notifications.api import write_system_log
from .models import CourseTree, CourseTreeNode
from .services import (
    TeacherWorkProtectedError,
    build_organization_textbook_index,
    build_textbook_catalog,
    dispatch_abilities,
    ensure_course_tree_can_regenerate,
    save_ai_course_tree,
)


def page_resource_library(request):
    """AI 岗课转化后的课程学习任务树页面。"""
    if not request.user.is_authenticated:
        return render(request, "login.html")
    return render(request, "教育资源库.html")


def page_course_management(request):
    """学院负责人分配课程负责人的管理页。"""
    if not request.user.is_authenticated:
        return render(request, "login.html")
    # 首屏直接渲染，避免 iframe 页面因异步请求或旧缓存长期停在“正在加载”。
    can_manage = _is_college_manager(request)
    courses = _managed_course_data(request) if can_manage else []
    response = render(request, "课程管理.html", {
        "initial_courses": courses,
        "management_error": "仅学院负责人或超级管理员可以管理课程负责人。" if not can_manage else "",
    })
    add_never_cache_headers(response)
    return response


def _is_college_manager(request):
    profile = getattr(request.user, "profile", None)
    return request.user.is_superuser or bool(
        profile and profile.role and profile.role.name == "学院负责人"
    )


def _can_dispatch_abilities(request):
    """岗位能力下发是独立写权限，不能仅凭已登录或页面可见性放行。"""
    if request.user.is_superuser:
        return True
    profile = getattr(request.user, "profile", None)
    return bool(
        profile
        and profile.role
        and profile.role.is_enabled
        and profile.role.permissions.filter(code="capability_dispatch").exists()
    )


def _visible_course_trees(request):
    """学院负责人可见本学院全部课程，课程负责人仅可见自己的课程。"""
    trees = CourseTree.objects.select_related("organization", "textbook", "source_ability", "owner")
    if request.user.is_superuser:
        return trees
    profile = getattr(request.user, "profile", None)
    if profile and profile.organization_id:
        if _is_college_manager(request):
            return trees.filter(organization_id=profile.organization_id)
        return trees.filter(organization_id=profile.organization_id, owner=request.user)
    return trees.none()


def _course_status(tree, node_count=None):
    if tree.is_published:
        return "published", "已发布"
    if tree.has_unpublished_changes:
        return "changed", "有未发布更新"
    if tree.ai_generation_status == "processing":
        return "processing", "AI 生成中"
    if tree.ai_generation_status == "error":
        return "error", "AI 生成失败"
    if not tree.owner_id:
        return "unassigned", "待分配负责人"
    if node_count is not None and node_count == 0:
        return "pending", "待 AI 生成"
    return "editing", "待课程编辑"


def _managed_course_data(request):
    """课程管理列表的共享序列化逻辑。"""
    profile = getattr(request.user, "profile", None)
    trees = CourseTree.objects.select_related("organization", "owner", "textbook").order_by("-updated_at", "-id")
    if not request.user.is_superuser:
        if not profile or not profile.organization_id:
            return []
        trees = trees.filter(organization_id=profile.organization_id)
    courses = []
    for tree in trees:
        status, status_label = _course_status(tree, tree.nodes.count())
        courses.append({
            "id": tree.id, "name": tree.name, "course_type": tree.get_course_type_display(),
            "course_type_code": tree.course_type,
            "total_hours": tree.total_hours, "credits": str(tree.credits),
            "organization": tree.organization.name,
            "owner_id": tree.owner_id,
            "owner_name": getattr(getattr(tree.owner, "profile", None), "real_name", "") or (tree.owner.username if tree.owner_id else "未分配"),
            "textbook": tree.textbook.name if tree.textbook_id else "尚未匹配教材",
            "has_unpublished_changes": tree.has_unpublished_changes,
            "status": status, "status_label": status_label,
        })
    return courses


@require_http_methods(["GET"])
def api_course_management_trees(request):
    """学院负责人查看本学院课程并进行负责人分配。"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    if not _is_college_manager(request):
        return JsonResponse({"error": "仅学院负责人可以管理课程负责人"}, status=403)
    return JsonResponse({"courses": _managed_course_data(request)})


@require_http_methods(["GET"])
def api_course_owner_candidates(request):
    """按课程所属学院返回可分配的课程负责人账号。"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    if not _is_college_manager(request):
        return JsonResponse({"error": "仅学院负责人可以分配课程负责人"}, status=403)
    try:
        tree_id = int(request.GET.get("tree_id"))
    except (TypeError, ValueError):
        return JsonResponse({"error": "缺少有效的课程参数"}, status=400)
    tree = CourseTree.objects.select_related("organization").filter(pk=tree_id).first()
    if tree is None:
        return JsonResponse({"error": "课程不存在"}, status=404)
    profile = getattr(request.user, "profile", None)
    if not request.user.is_superuser and (
        not profile or tree.organization_id != profile.organization_id
    ):
        return JsonResponse({"error": "不能管理其他学院的课程"}, status=403)
    from apps.accounts.models import UserProfile
    profiles = UserProfile.objects.select_related("user", "role", "organization").filter(
        organization_id=tree.organization_id,
        role__name="课程负责人",
        role__is_enabled=True,
        user__is_active=True,
    )
    return JsonResponse({"organization_id": tree.organization_id, "users": [
        {"id": item.user_id, "name": item.real_name or item.user.username, "username": item.user.username}
        for item in profiles.order_by("real_name", "user__username")
    ]})


@csrf_exempt
@require_http_methods(["POST"])
def api_assign_course_owner(request, tree_id):
    """学院负责人为课程树分配或更换课程负责人。"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    if not _is_college_manager(request):
        return JsonResponse({"error": "仅学院负责人可以分配课程负责人"}, status=403)
    try:
        data = json.loads(request.body or "{}")
        owner_id = int(data.get("owner_id"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "课程负责人参数无效"}, status=400)
    tree = CourseTree.objects.select_related("organization").filter(pk=tree_id).first()
    if tree is None:
        return JsonResponse({"error": "课程不存在"}, status=404)
    profile = getattr(request.user, "profile", None)
    if not request.user.is_superuser and tree.organization_id != profile.organization_id:
        return JsonResponse({"error": "不能管理其他学院的课程"}, status=403)
    from apps.accounts.models import UserProfile
    owner = UserProfile.objects.select_related("user", "role").filter(
        user_id=owner_id, organization_id=tree.organization_id,
        role__name="课程负责人", user__is_active=True,
    ).first()
    if owner is None:
        return JsonResponse({"error": "该用户不是当前学院有效的课程负责人"}, status=400)
    previous_owner_id = tree.owner_id
    tree.owner = owner.user
    tree.save(update_fields=["owner", "updated_at"])
    write_system_log(
        "operation",
        f"课程负责人交接：{tree.name} → {owner.real_name or owner.user.username}",
        request=request,
        detail={
            "course_tree_id": tree.id,
            "organization_id": tree.organization_id,
            "previous_owner_id": previous_owner_id,
            "new_owner_id": owner.user_id,
        },
    )
    return JsonResponse({"ok": True, "tree_id": tree.id, "owner_id": owner.user_id, "owner_name": owner.real_name or owner.user.username})


@csrf_exempt
@require_http_methods(["PATCH"])
def api_update_course(request, tree_id):
    """学院负责人维护课程基础信息并同步调整课程负责人。"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    if not _is_college_manager(request):
        return JsonResponse({"error": "仅学院负责人可以编辑课程"}, status=403)
    tree = CourseTree.objects.select_related("organization", "owner").filter(pk=tree_id).first()
    if tree is None:
        return JsonResponse({"error": "课程不存在"}, status=404)
    profile = getattr(request.user, "profile", None)
    if not request.user.is_superuser and tree.organization_id != profile.organization_id:
        return JsonResponse({"error": "不能编辑其他学院的课程"}, status=403)
    try:
        data = json.loads(request.body or "{}")
        name = str(data.get("name", tree.name)).strip()
        course_type = str(data.get("course_type", tree.course_type))
        total_hours = int(data.get("total_hours", tree.total_hours))
        credits = Decimal(str(data.get("credits", tree.credits)))
        owner_id = data.get("owner_id", tree.owner_id)
    except (TypeError, ValueError, InvalidOperation, json.JSONDecodeError):
        return JsonResponse({"error": "课程信息格式无效"}, status=400)
    if not name or len(name) > 200:
        return JsonResponse({"error": "课程名称不能为空且不能超过 200 个字符"}, status=400)
    if course_type not in dict(CourseTree.COURSE_TYPES):
        return JsonResponse({"error": "课程类型无效"}, status=400)
    if total_hours < 0 or total_hours > 2000:
        return JsonResponse({"error": "学时必须在 0 到 2000 之间"}, status=400)
    if credits < 0 or credits > 100:
        return JsonResponse({"error": "学分必须在 0 到 100 之间"}, status=400)
    owner = None
    if owner_id not in (None, ""):
        from apps.accounts.models import UserProfile
        owner = UserProfile.objects.select_related("user").filter(
            user_id=owner_id, organization_id=tree.organization_id,
            role__name="课程负责人", user__is_active=True,
        ).first()
        if owner is None:
            return JsonResponse({"error": "课程负责人必须是本学院启用的课程负责人账号"}, status=400)
    previous_owner_id = tree.owner_id
    content_changed = (
        tree.name != name
        or tree.course_type != course_type
        or tree.total_hours != total_hours
        or tree.credits != credits
    )
    tree.name, tree.course_type = name, course_type
    tree.total_hours, tree.credits = total_hours, credits
    tree.owner = owner.user if owner else None
    republish_required = False
    if content_changed:
        republish_required = _require_republish(tree, request)
        tree.has_manual_edits = True
    tree.save()
    if previous_owner_id != tree.owner_id:
        write_system_log(
            "operation", f"课程负责人交接：{tree.name} → {owner.real_name or owner.user.username if owner else '未分配'}",
            request=request,
            detail={"course_tree_id": tree.id, "previous_owner_id": previous_owner_id, "new_owner_id": tree.owner_id},
        )
    return JsonResponse({"ok": True, "course": {
        "id": tree.id, "name": tree.name, "course_type": tree.get_course_type_display(),
        "course_type_code": tree.course_type, "total_hours": tree.total_hours,
        "credits": str(tree.credits), "organization": tree.organization.name,
        "owner_id": tree.owner_id,
        "owner_name": owner.real_name if owner and owner.real_name else (tree.owner.username if tree.owner_id else "未分配"),
        "has_unpublished_changes": tree.has_unpublished_changes,
        "republish_required": republish_required,
    }})


def api_course_task_trees(request):
    """课程任务树展示数据，供教育资源库三栏图谱读取。"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    question_queryset = CourseTreeNode.questions.rel.related_model.objects.all()
    node_queryset = CourseTreeNode.objects.order_by("sort_order", "id").prefetch_related(
        Prefetch("questions", queryset=question_queryset)
    )
    trees = list(_visible_course_trees(request).prefetch_related(
        Prefetch("nodes", queryset=node_queryset)
    ).order_by("name", "id"))
    courses, chapter_count, knowledge_count, question_count = [], 0, 0, 0
    for tree in trees:
        nodes = list(tree.nodes.all())
        children = {}
        for node in nodes:
            children.setdefault(node.parent_id, []).append(node)
        chapters = []
        for chapter in children.get(None, []):
            if chapter.node_type != "chapter":
                continue
            points = []
            for point in children.get(chapter.id, []):
                if point.node_type != "knowledge":
                    continue
                count = len(point.questions.all())
                question_count += count
                knowledge_count += 1
                points.append({
                    "id": point.id, "name": point.name,
                    "textbook_node": point.textbook_node.name if point.textbook_node_id else "未匹配教材知识点",
                    "is_edited": point.is_edited, "question_count": count,
                    "changed_since_publish": point.changed_since_publish,
                })
            chapter_count += 1
            cards_are_edited = bool(points) and all(point["is_edited"] for point in points)
            chapter_is_edited = chapter.chapter_content_edited and cards_are_edited
            chapters.append({
                "id": chapter.id, "name": chapter.name,
                "textbook_node": chapter.textbook_node.name if chapter.textbook_node_id else "未匹配教材章节",
                "is_edited": chapter_is_edited, "points": points,
                "content_is_edited": chapter.chapter_content_edited,
                "cards_are_edited": cards_are_edited,
                "changed_since_publish": chapter.changed_since_publish or any(
                    point["changed_since_publish"] for point in points
                ),
            })
        courses.append({
            "id": tree.id, "name": tree.name,
            "source_ability": tree.source_ability.name if tree.source_ability_id else "—",
            "textbook": tree.textbook.name if tree.textbook_id else "尚未 AI 匹配教材",
            "is_published": tree.is_published,
            "has_unpublished_changes": tree.has_unpublished_changes,
            "is_generated": bool(chapters),
            "ai_generation_status": tree.ai_generation_status,
            "ai_generation_error": tree.ai_generation_error,
            "chapters": chapters,
        })
    return JsonResponse({
        "courses": courses,
        "stats": {
            "course_count": len(courses), "chapter_count": chapter_count,
            "knowledge_count": knowledge_count, "question_count": question_count,
        },
    })


def _run_ai_learning_task_generation(tree_id):
    """在线程中执行耗时的两次 AI 调用，避免浏览器请求一直挂起。"""
    try:
        course_tree = CourseTree.objects.select_related("source_ability", "organization").get(pk=tree_id)
        ability_snapshot = course_tree.source_snapshot or {
            "id": course_tree.source_ability_id,
            "name": course_tree.source_ability.name,
        }
        textbook_index = build_organization_textbook_index(course_tree.organization)
        if not textbook_index["textbooks"]:
            raise ValueError("当前学院教材库没有已拆分的教材，不能进行 AI 匹配")
        from ai.services import generate_course_task_tree, select_course_textbook
        selection = select_course_textbook(ability_snapshot, textbook_index)
        textbook = Textbook.objects.filter(
            pk=selection.get("textbook_id"), organization=course_tree.organization
        ).first()
        if textbook is None:
            raise ValueError("AI 未在学院教材库中找到可匹配教材")
        course_tree.textbook = textbook
        course_tree.save(update_fields=["textbook", "updated_at"])
        payload = generate_course_task_tree(ability_snapshot, build_textbook_catalog(textbook))
        save_ai_course_tree(course_tree, payload)
        CourseTree.objects.filter(pk=tree_id).update(
            ai_generation_status="ready", ai_generation_error=""
        )
    except TeacherWorkProtectedError as exc:
        # 启动检查后仍可能有教师并发编辑。此时保留原树并恢复为可用状态，
        # 不把一次安全拦截伪装成已经覆盖成功。
        CourseTree.objects.filter(pk=tree_id).update(
            ai_generation_status="ready", ai_generation_error=str(exc)[:1000]
        )
    except Exception as exc:
        CourseTree.objects.filter(pk=tree_id).update(
            ai_generation_status="error", ai_generation_error=str(exc)[:1000]
        )


@csrf_exempt
@require_http_methods(["POST"])
def api_dispatch_abilities(request):
    """将一个岗位下选中的正式岗位能力下发给目标学院。"""

    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    if not _can_dispatch_abilities(request):
        return JsonResponse({
            "error": "仅拥有岗位能力下发权限的负责人或超级管理员可以下发课程树",
            "code": "capability_dispatch_forbidden",
        }, status=403)
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
    # 新下发的课程树立即进入后台 AI 岗课匹配；负责人分配可稍后进行。
    for item in results:
        if not item["created"]:
            continue
        CourseTree.objects.filter(pk=item["tree_id"]).update(
            ai_generation_status="processing", ai_generation_error=""
        )
        threading.Thread(
            target=_run_ai_learning_task_generation,
            args=(item["tree_id"],),
            daemon=True,
        ).start()
    created_count = sum(1 for item in results if item["created"])
    return JsonResponse({
        "ok": True,
        "created_count": created_count,
        "skipped_count": len(results) - created_count,
        "items": results,
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_generate_learning_tasks(request, tree_id):
    """使用 DeepSeek 将一棵下发课程树转化为学习任务树。"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    try:
        json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)

    course_tree = CourseTree.objects.select_related("source_ability", "organization").filter(pk=tree_id).first()
    if course_tree is None:
        return JsonResponse({"error": "课程树不存在"}, status=404)
    profile = getattr(request.user, "profile", None)
    can_trigger = (
        request.user.is_superuser
        or course_tree.owner_id == request.user.id
        or (_is_college_manager(request) and profile and profile.organization_id == course_tree.organization_id)
    )
    if not can_trigger:
        return JsonResponse({"error": "仅本学院负责人或课程负责人可以重新生成课程树"}, status=403)
    if not course_tree.source_ability_id:
        return JsonResponse({"error": "课程树缺少来源岗位能力"}, status=400)

    if course_tree.ai_generation_status == "processing":
        return JsonResponse({"ok": True, "status": "processing", "message": "AI 正在生成学习任务"}, status=202)
    try:
        ensure_course_tree_can_regenerate(course_tree)
    except TeacherWorkProtectedError as exc:
        return JsonResponse({
            "error": str(exc),
            "code": "teacher_work_protected",
            "details": exc.summary,
        }, status=409)
    course_tree.ai_generation_status = "processing"
    course_tree.ai_generation_error = ""
    course_tree.save(update_fields=["ai_generation_status", "ai_generation_error", "updated_at"])
    threading.Thread(target=_run_ai_learning_task_generation, args=(course_tree.id,), daemon=True).start()
    return JsonResponse({
        "ok": True,
        "tree_id": course_tree.id,
        "status": "processing",
        "message": "AI 已开始检索教材并生成学习任务。",
    }, status=202)


def _can_manage_course_tree(request, tree):
    return request.user.is_superuser or tree.owner_id == request.user.id


def _can_view_course_tree(request, tree):
    """限制课程内容读取范围，避免通过枚举节点 ID 跨学院读取。"""
    if request.user.is_superuser or tree.owner_id == request.user.id:
        return True
    profile = getattr(request.user, "profile", None)
    return bool(
        _is_college_manager(request)
        and profile
        and profile.organization_id == tree.organization_id
    )


def _require_republish(tree, request):
    """发布后的内容一旦修改，自动撤回发布，确保学生只看到重新确认后的版本。"""
    is_post_publish_change = tree.is_published or tree.has_unpublished_changes
    if not is_post_publish_change:
        return False
    was_published = tree.is_published
    tree.is_published = False
    tree.published_at = None
    tree.has_unpublished_changes = True
    tree.save(update_fields=[
        "is_published", "published_at", "has_unpublished_changes", "updated_at"
    ])
    if was_published:
        write_system_log(
            "operation", f"课程已撤回待重新发布：{tree.name}", request=request,
            detail={"course_tree_id": tree.id, "reason": "课程内容修改"},
        )
    return True


def _sync_task_edited_state(task):
    """任务卡编辑状态变化后，自动汇总直属学习任务的完成状态。"""
    if task is None or task.node_type != "chapter":
        return
    cards = task.children.filter(node_type="knowledge")
    is_edited = (
        task.chapter_content_edited
        and cards.exists()
        and not cards.filter(is_edited=False).exists()
    )
    if task.is_edited != is_edited:
        task.is_edited = is_edited
        task.save(update_fields=["is_edited", "updated_at"])


RESOURCE_TYPES = {"micro_course", "simulation", "video", "courseware", "document", "link"}


def _normalise_resource_links(value):
    """兼容旧版字符串资源，统一保存为名称、类型、链接组成的对象。"""
    if not isinstance(value, list):
        raise ValueError("教学资源必须是列表")
    resources = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if text:
                resources.append({"name": text, "resource_type": "link", "url": text})
            continue
        if not isinstance(item, dict):
            raise ValueError("教学资源格式无效")
        name = str(item.get("name") or "").strip()
        url = str(item.get("url") or "").strip()
        resource_type = str(item.get("resource_type") or "link")
        if not name or not url:
            raise ValueError("教学资源必须填写名称和链接")
        if resource_type not in RESOURCE_TYPES:
            raise ValueError("教学资源类型无效")
        if len(name) > 100 or len(url) > 500:
            raise ValueError("教学资源名称或链接过长")
        if urlparse(url).scheme not in {"http", "https"}:
            raise ValueError("教学资源链接必须以 http:// 或 https:// 开头")
        resources.append({"name": name, "resource_type": resource_type, "url": url})
    if len(resources) > 20:
        raise ValueError("单张任务卡最多关联 20 个教学资源")
    return resources


@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_task_card_detail(request, node_id):
    """查看或编辑学习任务（章）或学习任务卡（知识点）。"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    node = CourseTreeNode.objects.select_related("tree", "textbook_node", "tree__organization").filter(
        pk=node_id, node_type__in=["chapter", "knowledge"]
    ).first()
    if node is None:
        return JsonResponse({"error": "课程树节点不存在"}, status=404)
    if not _can_view_course_tree(request, node.tree):
        return JsonResponse({"error": "无权查看该课程内容"}, status=403)
    if request.method == "POST" and not _can_manage_course_tree(request, node.tree):
        return JsonResponse({"error": "仅课程负责人可以编辑学习任务和任务卡"}, status=403)
    if request.method == "POST":
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "无效的 JSON"}, status=400)
        for field in ("name", "task_description", "work_scenario"):
            if field in data:
                setattr(node, field, str(data[field] or "").strip())
        for field in ("operation_steps", "safety_points"):
            if field in data:
                value = data[field]
                if not isinstance(value, list):
                    return JsonResponse({"error": f"{field} 必须是列表"}, status=400)
                setattr(node, field, [str(item).strip() for item in value if str(item).strip()])
        if "resource_links" in data:
            try:
                node.resource_links = _normalise_resource_links(data["resource_links"])
            except ValueError as exc:
                return JsonResponse({"error": str(exc)}, status=400)
        is_post_publish_change = node.tree.is_published or node.tree.has_unpublished_changes
        republish_required = _require_republish(node.tree, request)
        node.tree.has_manual_edits = True
        node.tree.save(update_fields=["has_manual_edits", "updated_at"])
        if node.node_type == "chapter":
            node.chapter_content_edited = bool(data.get("is_edited", True))
        else:
            node.is_edited = bool(data.get("is_edited", True))
        if is_post_publish_change:
            node.changed_since_publish = True
        node.save()
        _sync_task_edited_state(node if node.node_type == "chapter" else node.parent)
    payload = {
        "id": node.id, "tree_id": node.tree_id, "node_type": node.node_type, "name": node.name,
        "task_description": node.task_description, "work_scenario": node.work_scenario,
        "operation_steps": node.operation_steps, "safety_points": node.safety_points,
        "resource_links": _normalise_resource_links(node.resource_links),
        "is_edited": node.chapter_content_edited if node.node_type == "chapter" else node.is_edited,
        "changed_since_publish": node.changed_since_publish,
        "textbook_node": node.textbook_node.name if node.textbook_node_id else "未匹配教材知识点",
    }
    if request.method == "POST":
        payload["republish_required"] = republish_required
    return JsonResponse(payload)


@csrf_exempt
@require_http_methods(["POST"])
def api_publish_course_tree(request, tree_id):
    """课程负责人确认任务卡后直接发布课程。"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    tree = CourseTree.objects.filter(pk=tree_id).first()
    if tree is None:
        return JsonResponse({"error": "课程树不存在"}, status=404)
    if not _can_manage_course_tree(request, tree):
        return JsonResponse({"error": "仅课程负责人可以发布课程"}, status=403)
    issues = []
    if tree.ai_generation_status != "ready":
        issues.append("课程尚未完成 AI 岗课转化")
    if not tree.name.strip():
        issues.append("课程名称不能为空")
    if tree.total_hours <= 0:
        issues.append("课程学时必须大于 0")
    if tree.credits <= 0:
        issues.append("课程学分必须大于 0")
    if not tree.textbook_id:
        issues.append("课程尚未匹配教材")

    chapters = list(tree.nodes.filter(node_type="chapter", parent__isnull=True))
    if not chapters:
        issues.append("课程至少需要一个学习任务")
    unedited_chapter_count = sum(1 for chapter in chapters if not chapter.chapter_content_edited)
    if unedited_chapter_count:
        issues.append(f"还有 {unedited_chapter_count} 个学习任务未编辑确认")

    empty_chapter_count = 0
    unedited_card_count = 0
    for chapter in chapters:
        cards = tree.nodes.filter(parent=chapter, node_type="knowledge")
        if not cards.exists():
            empty_chapter_count += 1
        unedited_card_count += cards.filter(is_edited=False).count()
    if empty_chapter_count:
        issues.append(f"还有 {empty_chapter_count} 个学习任务没有任务卡")
    if unedited_card_count:
        issues.append(f"还有 {unedited_card_count} 张学习任务卡未编辑完成")
    if issues:
        return JsonResponse({
            "error": "发布前检查未通过",
            "code": "publish_check_failed",
            "issues": issues,
        }, status=400)
    tree.is_published = True
    tree.published_at = timezone.now()
    tree.has_unpublished_changes = False
    tree.save(update_fields=[
        "is_published", "published_at", "has_unpublished_changes", "updated_at"
    ])
    tree.nodes.filter(changed_since_publish=True).update(changed_since_publish=False)
    return JsonResponse({"ok": True, "tree_id": tree.id, "published_at": tree.published_at.isoformat()})
