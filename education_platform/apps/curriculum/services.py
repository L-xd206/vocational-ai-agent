"""课程创建、负责人分配、能力映射和 AI 岗课转化写操作。"""

from django.db import transaction

from apps.resources.models import TextbookNode

from .models import CourseTree, CourseTreeNode


class TeacherWorkProtectedError(ValueError):
    """课程中已有人工成果，禁止 AI 直接覆盖。"""

    def __init__(self, summary):
        self.summary = summary
        super().__init__("课程已包含教师编辑成果，不能直接重新生成，请先创建新版本或清理人工内容。")


def teacher_work_summary(course_tree):
    """汇总会被重新生成覆盖的人工成果，兼容迁移前已存在的数据。"""
    current_state = CourseTree.objects.filter(pk=course_tree.pk).values(
        "has_manual_edits", "is_published"
    ).first() or {
        "has_manual_edits": course_tree.has_manual_edits,
        "is_published": course_tree.is_published,
    }
    nodes = list(
        CourseTreeNode.objects.filter(tree=course_tree)
        .only("id", "is_edited", "resource_links")
    )
    from apps.teaching.models import CourseQuestion

    return {
        "manual_course_edits": bool(current_state["has_manual_edits"]),
        "edited_node_count": sum(1 for node in nodes if node.is_edited),
        "resource_count": sum(
            len(node.resource_links)
            for node in nodes
            if isinstance(node.resource_links, list)
        ),
        "question_count": CourseQuestion.objects.filter(node__tree=course_tree).count(),
        "is_published": bool(current_state["is_published"]),
    }


def ensure_course_tree_can_regenerate(course_tree):
    """在启动 AI 和覆盖节点前都调用，防止并发编辑导致成果丢失。"""
    summary = teacher_work_summary(course_tree)
    if (
        summary["manual_course_edits"]
        or summary["edited_node_count"]
        or summary["resource_count"]
        or summary["question_count"]
        or summary["is_published"]
    ):
        raise TeacherWorkProtectedError(summary)
    return summary


def build_ability_snapshot(ability):
    """将一个岗位能力及其能力单元、知识点固化为下发快照。"""

    units = []
    for unit in ability.children.all():
        points = [
            {
                "id": point.id,
                "name": point.name,
                "node_type": point.node_type,
                "is_enabled": point.is_enabled,
                "sort_order": point.sort_order,
            }
            for point in unit.children.all()
            if point.node_type == "point"
        ]
        if unit.node_type == "unit":
            units.append({
                "id": unit.id,
                "name": unit.name,
                "node_type": unit.node_type,
                "is_enabled": unit.is_enabled,
                "sort_order": unit.sort_order,
                "children": points,
            })
    return {
        "id": ability.id,
        "job_id": ability.job_id,
        "name": ability.name,
        "node_type": ability.node_type,
        "is_enabled": ability.is_enabled,
        "sort_order": ability.sort_order,
        "units": units,
    }


@transaction.atomic
def dispatch_abilities(*, abilities, created_by=None):
    """按能力节点自身所属学院下发课程树；已下发的组合不会重复创建。"""

    results = []
    for ability in abilities:
        organization = ability.organization
        tree, created = CourseTree.objects.get_or_create(
            organization=organization,
            source_ability=ability,
            defaults={
                "name": ability.name,
                "source_snapshot": build_ability_snapshot(ability),
                "created_by": created_by,
            },
        )
        results.append({
            "tree_id": tree.id,
            "ability_id": ability.id,
            "ability_name": ability.name,
            "organization_id": organization.id,
            "organization_name": organization.name,
            "created": created,
        })
    return results


def build_textbook_catalog(textbook):
    """输出紧凑教材目录，只把可匹配的章和知识点发送给 AI。"""
    chapters = []
    for chapter in textbook.nodes.filter(node_type="chapter", parent__isnull=True).order_by("sort_order", "id"):
        chapters.append({
            "id": chapter.id,
            "name": chapter.name,
            "knowledge_points": [
                {
                    "id": point.id,
                    "name": point.name,
                    "content": point.content[:500],
                }
                for point in chapter.children.filter(node_type="knowledge").order_by("sort_order", "id")
            ],
        })
    return {"id": textbook.id, "name": textbook.name, "chapters": chapters}


def build_organization_textbook_index(organization):
    """构建学院教材知识库的轻量索引，供 AI 先自动选择教材。"""
    textbooks = []
    for textbook in organization.textbooks.all().order_by("name", "edition", "id"):
        chapters = []
        for chapter in textbook.nodes.filter(node_type="chapter", parent__isnull=True).order_by("sort_order", "id"):
            chapters.append({
                "id": chapter.id,
                "name": chapter.name,
                "knowledge_points": list(
                    chapter.children.filter(node_type="knowledge")
                    .order_by("sort_order", "id")
                    .values("id", "name")
                ),
            })
        if chapters:
            textbooks.append({
                "id": textbook.id,
                "name": textbook.name,
                "edition": textbook.edition,
                "chapters": chapters,
            })
    return {"textbooks": textbooks}


def _as_text(value):
    return str(value or "").strip()


def _as_text_list(value):
    if not isinstance(value, list):
        return []
    return [_as_text(item) for item in value if _as_text(item)]


@transaction.atomic
def save_ai_course_tree(course_tree, payload):
    """校验 AI 结果后，用学习任务树覆盖课程树的可再生成节点。"""
    if not course_tree.source_ability_id or not course_tree.textbook_id:
        raise ValueError("课程树必须同时关联来源岗位能力和教材")
    ensure_course_tree_can_regenerate(course_tree)

    ability = course_tree.source_ability
    units = list(ability.children.filter(node_type="unit").order_by("sort_order", "id"))
    points_by_unit = {
        unit.id: list(unit.children.filter(node_type="point").order_by("sort_order", "id"))
        for unit in units
    }
    expected_unit_ids = {unit.id for unit in units}
    expected_point_ids = {point.id for points in points_by_unit.values() for point in points}
    chapter_items = payload.get("chapters")
    if not isinstance(chapter_items, list):
        raise ValueError("AI 返回缺少学习任务列表")

    received_unit_ids = set()
    received_point_ids = set()
    prepared = []
    textbook_node_ids = set(
        TextbookNode.objects.filter(textbook=course_tree.textbook).values_list("id", flat=True)
    )
    textbook_chapter_ids = set(
        TextbookNode.objects.filter(
            textbook=course_tree.textbook, node_type="chapter"
        ).values_list("id", flat=True)
    )

    for chapter in chapter_items:
        if not isinstance(chapter, dict):
            raise ValueError("学习任务格式无效")
        unit_id = chapter.get("source_unit_id")
        if unit_id not in expected_unit_ids or unit_id in received_unit_ids:
            raise ValueError("AI 返回的能力单元不正确或重复")
        received_unit_ids.add(unit_id)
        textbook_chapter_id = chapter.get("textbook_chapter_id")
        if textbook_chapter_id is not None and textbook_chapter_id not in textbook_chapter_ids:
            raise ValueError("AI 返回的教材章节点不属于当前教材")

        knowledge_items = chapter.get("knowledge_points")
        if not isinstance(knowledge_items, list):
            raise ValueError("学习任务缺少任务卡列表")
        prepared_points = []
        allowed_point_ids = {point.id for point in points_by_unit[unit_id]}
        for point in knowledge_items:
            if not isinstance(point, dict):
                raise ValueError("学习任务卡格式无效")
            point_id = point.get("source_point_id")
            if point_id not in allowed_point_ids or point_id in received_point_ids:
                raise ValueError("AI 返回的知识点不正确、重复或归属错误")
            received_point_ids.add(point_id)
            textbook_node_id = point.get("textbook_node_id")
            if textbook_node_id is not None and textbook_node_id not in textbook_node_ids:
                raise ValueError("AI 返回的教材知识点不属于当前教材")
            prepared_points.append((point_id, textbook_node_id, point))
        prepared.append((unit_id, textbook_chapter_id, chapter, prepared_points))

    if received_unit_ids != expected_unit_ids or received_point_ids != expected_point_ids:
        raise ValueError("AI 返回未完整覆盖正式树的能力单元或知识点")

    unit_by_id = {unit.id: unit for unit in units}
    point_by_id = {point.id: point for points in points_by_unit.values() for point in points}
    textbook_nodes = TextbookNode.objects.in_bulk(textbook_node_ids)
    # 接口启动生成时会先检查一次；此处在真正覆盖前再次检查，避免 AI
    # 执行期间教师刚好编辑任务卡、添加资源或录入试题。
    ensure_course_tree_can_regenerate(course_tree)
    CourseTreeNode.objects.filter(tree=course_tree).delete()
    for chapter_index, (unit_id, textbook_chapter_id, chapter, knowledge_items) in enumerate(prepared):
        task = CourseTreeNode.objects.create(
            tree=course_tree,
            node_type="chapter",
            name=_as_text(chapter.get("name")) or unit_by_id[unit_id].name,
            source_node=unit_by_id[unit_id],
            textbook_node=textbook_nodes.get(textbook_chapter_id),
            task_description=_as_text(chapter.get("task_description")),
            work_scenario=_as_text(chapter.get("work_scenario")),
            operation_steps=_as_text_list(chapter.get("operation_steps")),
            safety_points=_as_text_list(chapter.get("safety_points")),
            resource_links=_as_text_list(chapter.get("resource_links")),
            sort_order=chapter_index,
        )
        for point_index, (point_id, textbook_node_id, point) in enumerate(knowledge_items):
            CourseTreeNode.objects.create(
                tree=course_tree,
                parent=task,
                node_type="knowledge",
                name=_as_text(point.get("name")) or point_by_id[point_id].name,
                source_node=point_by_id[point_id],
                textbook_node=textbook_nodes.get(textbook_node_id),
                task_description=_as_text(point.get("task_description")),
                work_scenario=_as_text(point.get("work_scenario")),
                operation_steps=_as_text_list(point.get("operation_steps")),
                safety_points=_as_text_list(point.get("safety_points")),
                resource_links=_as_text_list(point.get("resource_links")),
                sort_order=point_index,
            )

    course_name = _as_text(payload.get("course_name")) or ability.name
    course_type = payload.get("course_type")
    if course_type not in dict(CourseTree.COURSE_TYPES):
        course_type = "integrated"
    course_tree.name = course_name
    course_tree.course_type = course_type
    course_tree.total_hours = max(0, int(payload.get("total_hours") or 0))
    course_tree.credits = max(0, float(payload.get("credits") or 0))
    course_tree.save(update_fields=["name", "course_type", "total_hours", "credits", "updated_at"])

    ability.course_matches = [{
        "course_name": course_name,
        "matched_content": _as_text(payload.get("matched_content")),
        "source_textbook_id": course_tree.textbook_id,
        "course_tree_id": course_tree.id,
    }]
    ability.save(update_fields=["course_matches", "updated_at"])
    return course_tree
