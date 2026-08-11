"""招聘采集结果的标准化、去重与保存服务。"""

import hashlib

from django.db import transaction
from django.utils import timezone

from apps.capabilities.models import CapabilityNode, normalise_node_name
from apps.capabilities.services import (
    normalise_legacy_tree,
    refresh_ability_map_counts,
)
from apps.organizations.models import College

from .models import AnalysisBatch, AnalysisNode, JobListing


MIN_VALID_LISTINGS = 10


def valid_requirements(task):
    """返回一次采集任务中可供 AI 分析的有效任职要求。"""
    requirements = JobListing.objects.filter(task=task).values_list("requirements", flat=True)
    return [
        str(requirement).strip()
        for requirement in requirements
        if requirement and len(str(requirement).strip()) > 10
    ]


def data_quality(count):
    """根据有效招聘数据数量返回质量状态和用户提示。"""
    if count == 0:
        return "no_data", "暂无有效招聘数据，暂不生成能力图谱"
    if count < MIN_VALID_LISTINGS:
        return "insufficient", f"有效招聘数据仅 {count} 条，少于 {MIN_VALID_LISTINGS} 条，暂不生成能力图谱"
    if count >= 30:
        return "sufficient", f"有效招聘数据 {count} 条，数据较充分"
    return "ready", f"有效招聘数据 {count} 条，可以生成能力图谱"


def build_listing_fingerprint(item):
    """根据稳定字段生成 SHA-256 指纹，用于跨批次去重。"""
    parts = [
        item.get("title", ""),
        item.get("company", ""),
        item.get("city", ""),
        item.get("source_url", ""),
        str(item.get("requirements", ""))[:200],
    ]
    raw = "|".join(str(value or "").strip().casefold() for value in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def save_crawl_result(task, item):
    """保存或更新一条招聘信息，返回 (记录, 是否首次创建)。"""
    fingerprint = build_listing_fingerprint(item)
    defaults = {
        "task": task,
        "title": item.get("title", ""),
        "company": item.get("company", ""),
        "city": item.get("city", ""),
        "salary": item.get("salary", ""),
        "education": item.get("education", ""),
        "requirements": item.get("requirements", ""),
        "headcount": item.get("headcount", ""),
        "post_date": item.get("date", item.get("post_date", "")),
        "source": item.get("source", ""),
        "source_url": item.get("source_url", ""),
        "raw_json": item,
    }
    listing, created = JobListing.objects.update_or_create(
        job=task.job,
        crawl_source=task.source,
        fingerprint=fingerprint,
        defaults=defaults,
    )
    return listing, created


def _college_from_name(name):
    name = str(name or "").strip()
    if not name or name == "未分配学院":
        return None
    return College.objects.filter(name=name).first()


def _match_official_node(job, parent, node_type, name):
    return CapabilityNode.objects.filter(
        job=job,
        parent=parent,
        node_type=node_type,
        normalized_name=normalise_node_name(name),
    ).first()


@transaction.atomic
def create_analysis_batch(job, tree, *, crawl_task=None, raw_ai_output="", model_name="", batch=None):
    """保存一棵岗位采集 AI 候选树，并逐级匹配正式能力节点。"""
    normalized_tree = normalise_legacy_tree(tree)
    if batch is None:
        batch = AnalysisBatch(job=job, crawl_task=crawl_task)
    else:
        batch.nodes.all().delete()
    batch.status = "completed"
    batch.input_listing_count = crawl_task.listings.count() if crawl_task else 0
    batch.model_name = model_name
    batch.raw_ai_output = raw_ai_output
    batch.error_message = ""
    batch.started_at = batch.started_at or timezone.now()
    batch.finished_at = timezone.now()
    batch.save()

    def add_candidate(data, node_type, parent_candidate, parent_official, order, college=None):
        matched = _match_official_node(job, parent_official, node_type, data.get("name"))
        candidate = AnalysisNode.objects.create(
            batch=batch,
            parent=parent_candidate,
            node_type=node_type,
            name=str(data.get("name") or "").strip(),
            normalized_name=normalise_node_name(data.get("name")),
            matched_node=matched,
            college=college,
            decision_status="not_required" if matched else "pending",
            evidence_json=data.get("evidence", []),
            sort_order=order,
        )
        return candidate, matched

    for ability_order, ability_data in enumerate(normalized_tree):
        college = _college_from_name(ability_data.get("college"))
        ability_candidate, ability_match = add_candidate(
            ability_data, "ability", None, None, ability_order, college
        )
        for unit_order, unit_data in enumerate(ability_data.get("units", [])):
            unit_candidate, unit_match = add_candidate(
                unit_data, "unit", ability_candidate, ability_match, unit_order
            )
            for point_order, point_data in enumerate(unit_data.get("children", [])):
                add_candidate(
                    point_data,
                    "point",
                    unit_candidate,
                    unit_match,
                    point_order,
                )
    return batch


def serialize_analysis_tree(batch, *, decision_status=None):
    """将 AI 候选节点序列化成岗位能力、能力单元、知识点三层树。"""
    queryset = batch.nodes.select_related("matched_node", "college").order_by("sort_order", "id")
    if decision_status:
        queryset = queryset.filter(decision_status=decision_status)
    nodes = list(queryset)
    included_ids = {node.id for node in nodes}
    children = {}
    for node in nodes:
        parent_id = node.parent_id if node.parent_id in included_ids else None
        children.setdefault(parent_id, []).append(node)

    def item(node):
        payload = {
            "id": node.id,
            "name": node.name,
            "node_type": node.node_type,
            "matched_node_id": node.matched_node_id,
            "is_virtual": node.matched_node_id is None,
            "decision_status": node.decision_status,
            "evidence": node.evidence_json,
            "children": [item(child) for child in children.get(node.id, [])],
        }
        if node.node_type == "ability":
            payload["college"] = node.college.name if node.college else "未分配学院"
        return payload

    return [item(node) for node in children.get(None, [])]


@transaction.atomic
def adopt_analysis_node(node):
    """引用候选节点；若其虚体祖先尚未引用，则先自动补齐祖先路径。"""
    if node.decision_status == "rejected":
        raise ValueError("已拒纳节点需先恢复，不能直接引用")
    if node.matched_node_id:
        if node.decision_status == "pending":
            node.decision_status = "adopted"
            node.decided_at = timezone.now()
            node.save(update_fields=["decision_status", "decided_at", "updated_at"])
        return node.matched_node

    parent = adopt_analysis_node(node.parent) if node.parent_id else None
    matched = _match_official_node(node.batch.job, parent, node.node_type, node.name)
    if matched is None:
        matched = CapabilityNode.objects.create(
            job=node.batch.job,
            parent=parent,
            node_type=node.node_type,
            name=node.name,
            normalized_name=node.normalized_name,
            college=node.college if node.node_type == "ability" else None,
            origin="ai",
            is_enabled=parent.is_enabled if parent else node.batch.job.is_enabled,
            sort_order=CapabilityNode.objects.filter(job=node.batch.job, parent=parent).count(),
        )
    node.matched_node = matched
    node.decision_status = "adopted"
    node.decided_at = timezone.now()
    node.save(update_fields=["matched_node", "decision_status", "decided_at", "updated_at"])
    refresh_ability_map_counts(node.batch.job, reset_review=True)
    return matched


def _reject_candidate_subtree(node):
    node.decision_status = "rejected"
    node.decided_at = timezone.now()
    node.save(update_fields=["decision_status", "decided_at", "updated_at"])
    for child in node.children.all():
        _reject_candidate_subtree(child)


@transaction.atomic
def reject_analysis_node(node):
    """拒纳虚体节点及其所有候选子节点。"""
    if node.matched_node_id:
        raise ValueError("正式已存在节点不能拒纳")
    _reject_candidate_subtree(node)
