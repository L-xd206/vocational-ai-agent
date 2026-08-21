"""能力图谱节点、AI 候选树与兼容树结构的业务服务。"""

import copy
import math

from django.db import transaction
from apps.organizations.models import Organization

from .models import (
    AbilityMap,
    CapabilityNode,
    normalise_node_name,
)


def normalise_legacy_tree(tree):
    """把旧版 ability.children 结构转换为 ability.units.children 四层结构。"""
    result = copy.deepcopy(tree or [])
    for ability in result:
        ability.setdefault("enabled", True)
        ability.setdefault("college", "未分配学院")
        if "units" not in ability:
            points = ability.pop("children", []) or []
            size = math.ceil(len(points) / 3) if points else 1
            ability["units"] = [
                {
                    "name": f"能力单元 {index // size + 1}",
                    "enabled": ability["enabled"],
                    "children": [
                        {**point, "enabled": point.get("enabled", True)}
                        for point in points[index:index + size]
                    ],
                }
                for index in range(0, len(points), size)
            ]
        for unit in ability.get("units", []):
            unit.setdefault("enabled", ability["enabled"])
            unit.setdefault("children", [])
            for point in unit["children"]:
                point.setdefault("enabled", unit["enabled"])
    return result


def _organization_from_name(name):
    name = str(name or "").strip()
    if not name or name == "未分配学院":
        return None
    return Organization.objects.filter(name=name, is_enabled=True).first()


def _upsert_node(*, job, parent, node_type, data, origin, sort_order, organization=None):
    normalized_name = normalise_node_name(data.get("name"))
    if not normalized_name:
        return None
    node = CapabilityNode.objects.filter(
        job=job,
        parent=parent,
        node_type=node_type,
        normalized_name=normalized_name,
    ).first()
    if node is None:
        node = CapabilityNode(
            job=job,
            parent=parent,
            node_type=node_type,
            normalized_name=normalized_name,
        )
    node.name = str(data.get("name") or "").strip()
    node.is_enabled = data.get("enabled", True) is not False
    node.sort_order = sort_order
    if node.origin == "manual" and node.pk:
        pass
    else:
        node.origin = origin
    if node_type == "ability":
        node.organization = organization
    node.save()
    return node


@transaction.atomic
def merge_official_tree(job, tree, origin="ai"):
    """将兼容树合并到正式节点表；保留不在本次树中的人工节点。"""
    normalized_tree = normalise_legacy_tree(tree)
    for ability_order, ability_data in enumerate(normalized_tree):
        ability = _upsert_node(
            job=job,
            parent=None,
            node_type="ability",
            data=ability_data,
            origin=origin,
            sort_order=ability_order,
            organization=_organization_from_name(ability_data.get("college")),
        )
        if ability is None:
            continue
        for unit_order, unit_data in enumerate(ability_data.get("units", [])):
            unit = _upsert_node(
                job=job,
                parent=ability,
                node_type="unit",
                data=unit_data,
                origin=origin,
                sort_order=unit_order,
            )
            if unit is None:
                continue
            for point_order, point_data in enumerate(unit_data.get("children", [])):
                _upsert_node(
                    job=job,
                    parent=unit,
                    node_type="point",
                    data=point_data,
                    origin=origin,
                    sort_order=point_order,
                )
    refresh_ability_map_counts(job)
    return serialize_official_tree(job)


def serialize_official_tree(job):
    """用一次查询把正式节点表还原成旧前端仍可读取的 JSON 树。"""
    nodes = list(
        CapabilityNode.objects.filter(job=job)
        .select_related("organization")
        .order_by("sort_order", "id")
    )
    children = {}
    for node in nodes:
        children.setdefault(node.parent_id, []).append(node)

    tree = []
    for ability in children.get(None, []):
        if ability.node_type != "ability":
            continue
        ability_item = {
            "id": ability.id,
            "name": ability.name,
            "college": ability.organization.name if ability.organization else "未分配学院",
            "organization_id": ability.organization_id,
            "enabled": ability.is_enabled,
            "units": [],
        }
        for unit in children.get(ability.id, []):
            if unit.node_type != "unit":
                continue
            unit_item = {
                "id": unit.id,
                "name": unit.name,
                "enabled": unit.is_enabled,
                "children": [],
            }
            for point in children.get(unit.id, []):
                if point.node_type != "point":
                    continue
                unit_item["children"].append({
                    "id": point.id,
                    "name": point.name,
                    "enabled": point.is_enabled,
                })
            ability_item["units"].append(unit_item)
        tree.append(ability_item)
    return tree


def refresh_ability_map_counts(job, reset_review=False):
    """节点变化后同步图谱元信息中的统计值。"""
    ability_map, _ = AbilityMap.objects.get_or_create(job=job, defaults={"abilities_json": []})
    ability_map.total_abilities = CapabilityNode.objects.filter(
        job=job, node_type="ability"
    ).count()
    ability_map.total_skills = CapabilityNode.objects.filter(
        job=job, node_type="point"
    ).count()
    update_fields = ["total_abilities", "total_skills"]
    if reset_review:
        ability_map.review_status = "pending"
        ability_map.review_note = ""
        ability_map.reviewed_at = None
        update_fields += ["review_status", "review_note", "reviewed_at"]
    ability_map.save(update_fields=update_fields)
    return ability_map


def resolve_node_by_legacy_path(job, node_type, ability_index=None, unit_index=None, point_index=None):
    """兼容旧前端传来的数组下标，解析到稳定的 CapabilityNode。"""
    abilities = list(CapabilityNode.objects.filter(
        job=job, parent__isnull=True, node_type="ability"
    ).order_by("sort_order", "id"))
    ability = abilities[int(ability_index)]
    if node_type == "ability":
        return ability
    units = list(ability.children.filter(node_type="unit").order_by("sort_order", "id"))
    unit = units[int(unit_index)]
    if node_type == "unit":
        return unit
    points = list(unit.children.filter(node_type="point").order_by("sort_order", "id"))
    return points[int(point_index)]


@transaction.atomic
def create_official_node(*, job, parent_type, name, organization_name="", ability_index=None, unit_index=None):
    """按旧前端参数新增正式节点，并执行同级去重。"""
    name = str(name or "").strip()
    if not name:
        raise ValueError("请输入节点名称")
    normalized_name = normalise_node_name(name)
    if parent_type == "job":
        parent = None
        node_type = "ability"
        organization = Organization.objects.filter(
            name=organization_name,
            is_enabled=True,
        ).first()
        if organization is None:
            raise ValueError("所选组织不存在或已禁用")
    elif parent_type == "ability":
        parent = resolve_node_by_legacy_path(job, "ability", ability_index)
        node_type = "unit"
        organization = None
    elif parent_type == "unit":
        parent = resolve_node_by_legacy_path(job, "unit", ability_index, unit_index)
        node_type = "point"
        organization = None
    else:
        raise ValueError("父节点类型无效")

    if CapabilityNode.objects.filter(
        job=job, parent=parent, node_type=node_type, normalized_name=normalized_name
    ).exists():
        raise ValueError("同一父节点下已存在同名节点")
    sort_order = CapabilityNode.objects.filter(job=job, parent=parent).count()
    node = CapabilityNode.objects.create(
        job=job,
        parent=parent,
        node_type=node_type,
        name=name,
        normalized_name=normalized_name,
        organization=organization,
        origin="manual",
        is_enabled=parent.is_enabled if parent else job.is_enabled,
        sort_order=sort_order,
    )
    refresh_ability_map_counts(job, reset_review=True)
    return node


def _set_descendants_enabled(node, enabled):
    node.is_enabled = enabled
    node.save(update_fields=["is_enabled", "updated_at"])
    for child in node.children.all():
        _set_descendants_enabled(child, enabled)


@transaction.atomic
def set_node_enabled(node, enabled):
    """切换正式节点状态；禁用父节点时级联禁用所有后代。"""
    if enabled:
        node.is_enabled = True
        node.save(update_fields=["is_enabled", "updated_at"])
    else:
        _set_descendants_enabled(node, False)
    refresh_ability_map_counts(node.job, reset_review=True)


@transaction.atomic
def set_job_tree_enabled(job, enabled):
    for root in CapabilityNode.objects.filter(job=job, parent__isnull=True):
        _set_descendants_enabled(root, enabled)
    refresh_ability_map_counts(job, reset_review=True)
