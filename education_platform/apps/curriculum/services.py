"""课程创建、负责人分配、能力映射等写操作。"""

from django.db import transaction

from .models import CourseTree


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
