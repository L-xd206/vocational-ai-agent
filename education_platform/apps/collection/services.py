"""招聘采集结果的标准化、去重与保存服务。"""

import hashlib
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.capabilities.models import CapabilityNode, normalise_node_name
from apps.capabilities.services import (
    normalise_legacy_tree,
    refresh_ability_map_counts,
)
from apps.organizations.models import College

from .crawlers.registry import validate_crawler_code
from .models import (
    AnalysisBatch,
    AnalysisNode,
    CrawlSource,
    CrawlTask,
    JobListing,
)


MIN_VALID_LISTINGS = 10


def serialize_crawl_source(source):
    config = source.config_json or {}
    return {
        "id": source.id,
        "name": source.name,
        "code": source.code,
        "base_url": source.base_url,
        "interval_minutes": source.interval_minutes,
        "pages": int(config.get("pages", 3)),
        "is_enabled": source.is_enabled,
        "last_run_at": source.last_run_at.isoformat() if source.last_run_at else None,
        "next_run_at": source.next_run_at.isoformat() if source.next_run_at else None,
        "created_at": source.created_at.isoformat(),
        "updated_at": source.updated_at.isoformat(),
    }


def _validated_source_values(data, source=None):
    name = str(data.get("name", source.name if source else "")).strip()
    code = str(data.get("code", source.code if source else "")).strip()
    base_url = str(data.get("base_url", source.base_url if source else "")).strip()
    if not name or not code or not base_url:
        raise ValueError("请填写来源名称、来源编码和来源地址")
    validate_crawler_code(code)

    try:
        interval_minutes = int(data.get(
            "interval_minutes", source.interval_minutes if source else 1440
        ))
        pages = int(data.get(
            "pages", (source.config_json or {}).get("pages", 3) if source else 3
        ))
    except (TypeError, ValueError):
        raise ValueError("采集间隔和采集页数必须是整数")
    if not 5 <= interval_minutes <= 43200:
        raise ValueError("采集间隔必须在5分钟到30天之间")
    if not 1 <= pages <= 10:
        raise ValueError("每个关键词采集页数必须在1到10之间")

    return {
        "name": name,
        "code": code,
        "base_url": base_url,
        "interval_minutes": interval_minutes,
        "pages": pages,
        "is_enabled": bool(data.get("is_enabled", source.is_enabled if source else True)),
    }


@transaction.atomic
def create_crawl_source(data):
    values = _validated_source_values(data)
    now = timezone.now()
    return CrawlSource.objects.create(
        name=values["name"],
        code=values["code"],
        base_url=values["base_url"],
        interval_minutes=values["interval_minutes"],
        is_enabled=values["is_enabled"],
        config_json={"pages": values["pages"]},
        next_run_at=(
            now + timedelta(minutes=values["interval_minutes"])
            if values["is_enabled"] else None
        ),
    )


@transaction.atomic
def update_crawl_source(source, data):
    values = _validated_source_values(data, source)
    source.name = values["name"]
    source.code = values["code"]
    source.base_url = values["base_url"]
    source.interval_minutes = values["interval_minutes"]
    source.is_enabled = values["is_enabled"]
    source.config_json = {**(source.config_json or {}), "pages": values["pages"]}
    source.next_run_at = (
        timezone.now() + timedelta(minutes=values["interval_minutes"])
        if source.is_enabled else None
    )
    source.save()
    return source


@transaction.atomic
def create_crawl_task(*, job, source, trigger_type):
    existing = CrawlTask.objects.filter(
        job=job,
        source=source,
        status__in=["pending", "running"],
    ).order_by("-created_at").first()
    if existing:
        return existing, False

    try:
        # 使用内部保存点：并发插入触发唯一约束时，只回滚本次 INSERT，
        # 外层事务仍可继续查询已经由另一请求创建的任务。
        with transaction.atomic():
            task = CrawlTask.objects.create(
                job=job,
                source=source,
                trigger_type=trigger_type,
                status="pending",
                scheduled_at=timezone.now(),
                total_keywords=len(job.search_keywords or [job.name]),
            )
        return task, True
    except IntegrityError:
        task = CrawlTask.objects.get(
            job=job,
            source=source,
            status__in=["pending", "running"],
        )
        return task, False


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
    # 记录关联的采集任务，并把 AI 分析结果保存为 AnalysisBatch 和 AnalysisNode。
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


def serialize_rejected_tree(batch):
    """返回拒纳节点，并保留未被拒纳的祖先作为只读路径上下文。"""
    nodes = list(
        batch.nodes.select_related("matched_node", "college")
        .order_by("sort_order", "id")
    )
    node_map = {node.id: node for node in nodes}
    included_ids = set()

    for node in nodes:
        if node.decision_status != "rejected":
            continue
        current = node
        while current:
            included_ids.add(current.id)
            current = node_map.get(current.parent_id)

    children = {}
    for node in nodes:
        if node.id not in included_ids:
            continue
        parent_id = node.parent_id if node.parent_id in included_ids else None
        children.setdefault(parent_id, []).append(node)

    def item(node):
        return {
            "id": node.id,
            "name": node.name,
            "node_type": node.node_type,
            "decision_status": node.decision_status,
            "context_only": node.decision_status != "rejected",
            "is_virtual": node.matched_node_id is None,
            "evidence": node.evidence_json,
            "decided_at": node.decided_at.isoformat() if node.decided_at else None,
            "children": [item(child) for child in children.get(node.id, [])],
        }

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
