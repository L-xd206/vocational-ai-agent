"""招聘采集结果的标准化、去重与保存服务。"""

import hashlib
import re
import unicodedata
from difflib import SequenceMatcher
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.capabilities.models import CapabilityNode, normalise_node_name
from apps.capabilities.services import (
    normalise_legacy_tree,
    refresh_ability_map_counts,
)
from apps.industry.models import Job
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
REQUIREMENT_DUPLICATE_THRESHOLD = 0.97
POINT_MATCH_THRESHOLD = 0.74
UNIT_MATCH_THRESHOLD = 0.80
ABILITY_MATCH_THRESHOLD = 0.84


def normalise_evidence(value):
    """把大模型可能返回的字符串、列表或空值统一为前端可用的列表。"""
    if value in (None, ""):
        return []
    values = value if isinstance(value, (list, tuple)) else [value]
    result = []
    for item in values:
        if item is None:
            continue
        if isinstance(item, str):
            item = item.strip()
            if not item:
                continue
        if item not in result:
            result.append(item)
    return result


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
    # 来源身份和网址由对应采集器实现决定，配置页面及接口均只允许调整运行参数。
    immutable_source_data = {
        **data,
        "name": source.name,
        "code": source.code,
        "base_url": source.base_url,
    }
    values = _validated_source_values(immutable_source_data, source)
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


def normalise_requirement_text(value):
    """把任职要求变成稳定的比较文本，忽略全半角、大小写、空格和标点差异。"""
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)


def build_content_fingerprint(requirements):
    """只根据任职要求正文生成内容指纹，企业、标题变化不会制造“新信息”。"""
    normalized = normalise_requirement_text(requirements)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


def _requirements_similar(left, right, *, threshold=REQUIREMENT_DUPLICATE_THRESHOLD):
    left_key = normalise_requirement_text(left)
    right_key = normalise_requirement_text(right)
    return _normalised_requirements_similar(left_key, right_key, threshold=threshold)


def _normalised_requirements_similar(left_key, right_key, *, threshold=REQUIREMENT_DUPLICATE_THRESHOLD):
    """比较已规范化的正文；廉价上界检查不会改变最终相似度判断结果。"""
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True
    # 短文本中一两个字的变化可能改变实际含义，只对信息较充分的正文做近似去重。
    if min(len(left_key), len(right_key)) < 20:
        return False
    matcher = SequenceMatcher(None, left_key, right_key)
    # real_quick_ratio/quick_ratio 都是 ratio 的上界。上界尚未达到阈值时，
    # 可以安全跳过最耗时的最长公共子序列计算，不会产生漏判。
    if matcher.real_quick_ratio() < threshold or matcher.quick_ratio() < threshold:
        return False
    return matcher.ratio() >= threshold


def valid_requirement_records(task, *, new_only=False):
    """返回真正新增且互不重复的招聘记录，并保留来源追溯信息。"""
    queryset = JobListing.objects.filter(task=task)
    if new_only:
        # 只有首次创建且仍归属于当前任务的记录才算本批新增。
        queryset = queryset.filter(first_seen_at__gte=task.created_at)
    candidates = list(
        queryset.select_related("crawl_source").order_by("first_seen_at", "id")
    )

    historical = []
    if new_only:
        historical = list(
            JobListing.objects.filter(job=task.job, first_seen_at__lt=task.created_at)
            .exclude(requirements="")
            .values_list("requirements", flat=True)
        )

    accepted = []
    # 旧实现每次两两比较都会重复执行 Unicode 规范化和正则替换；页面为了
    # 还原证据来源会重新走该逻辑，因此数据稍多就会产生数万次重复运算。
    comparison_pool = [normalise_requirement_text(value) for value in historical]
    for listing in candidates:
        requirement = str(listing.requirements or "").strip()
        if len(requirement) <= 10:
            continue
        requirement_key = normalise_requirement_text(requirement)
        if any(
            _normalised_requirements_similar(requirement_key, old_key)
            for old_key in comparison_pool
        ):
            continue
        accepted.append(listing)
        comparison_pool.append(requirement_key)
    return accepted


def valid_requirements(task, *, new_only=False):
    """返回真正新增且互不重复的有效任职要求，供AI分析。"""
    return [
        listing.requirements.strip()
        for listing in valid_requirement_records(task, new_only=new_only)
    ]


def analysis_requirement_records(task):
    """复现AI输入的过滤与编号顺序，用于把“招聘要求[n]”追溯到原记录。"""
    seen = set()
    result = []
    for listing in valid_requirement_records(task, new_only=True):
        requirement = str(listing.requirements or "").strip()
        if len(requirement) < 15:
            continue
        key = requirement[:40]
        if key in seen:
            continue
        seen.add(key)
        result.append(listing)
    return result


def serialize_evidence_details(value, task=None, *, requirement_records=None):
    """把证据文字补充为可追溯详情；沿用 JSONField，不需要修改表结构。"""
    evidence = normalise_evidence(value)
    if requirement_records is None:
        requirement_records = analysis_requirement_records(task) if task else []
    result = []
    for item in evidence:
        if isinstance(item, dict):
            result.append(item)
            continue
        text = str(item or "").strip()
        indexes = [int(value) for value in re.findall(r"\[(\d+)\]", text)]
        matched = False
        for index in indexes:
            if not 1 <= index <= len(requirement_records):
                continue
            listing = requirement_records[index - 1]
            source_name = (
                listing.crawl_source.name
                if listing.crawl_source_id else listing.source
            ) or "未知数据源"
            result.append({
                "text": text,
                "source_name": source_name,
                # 中国公共招聘网当前列表接口没有返回每条职位的详情URL；
                # 此时展示采集源主页，仍保证链接来自真实配置而不是虚构地址。
                "source_url": listing.source_url or (
                    listing.crawl_source.base_url if listing.crawl_source_id else ""
                ),
                "captured_at": listing.first_seen_at.isoformat(),
                "job_title": listing.title,
                "company": listing.company,
            })
            matched = True
        if not matched:
            result.append({"text": text})
    return result


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


@transaction.atomic
def save_crawl_result(task, item):
    """保存一条招聘信息；重复记录只刷新内容，不篡改首次发现任务。"""
    # 以岗位作为并发锁。同一岗位即使未来同时启用多个采集源，也必须串行完成
    # “查询是否存在 -> 创建”这段操作，避免两个任务同时插入相同正文。
    Job.objects.select_for_update().only("id").get(id=task.job_id)
    fingerprint = build_listing_fingerprint(item)
    requirements = str(item.get("requirements", "") or "").strip()
    content_fingerprint = build_content_fingerprint(requirements)
    defaults = {
        "title": item.get("title", ""),
        "company": item.get("company", ""),
        "city": item.get("city", ""),
        "salary": item.get("salary", ""),
        "education": item.get("education", ""),
        "requirements": requirements,
        "headcount": item.get("headcount", ""),
        "post_date": item.get("date", item.get("post_date", "")),
        "source": item.get("source", ""),
        "source_url": item.get("source_url", ""),
        "raw_json": item,
    }
    # 指纹本身已经包含来源网址和招聘内容；先跨采集源查询，可识别历史数据中
    # crawl_source 为空、后来补上来源配置后再次采到的同一条招聘信息。
    listing = JobListing.objects.filter(
        job=task.job,
        fingerprint=fingerprint,
    ).order_by("id").first()
    if listing is None and content_fingerprint:
        listing = JobListing.objects.filter(
            job=task.job,
            content_fingerprint=content_fingerprint,
        ).order_by("id").first()
    if listing is None and requirements:
        # 兼容历史迁移前的数据，也拦截只有极小文字改动的重复正文。
        for existing in JobListing.objects.filter(job=task.job).exclude(requirements="").order_by("id"):
            if _requirements_similar(requirements, existing.requirements):
                listing = existing
                break
    created = listing is None
    if created:
        listing = JobListing.objects.create(
            job=task.job,
            crawl_source=task.source,
            fingerprint=fingerprint,
            content_fingerprint=content_fingerprint,
            task=task,
            **defaults,
        )
    if not created:
        # 保留 listing.task，确保历史重复数据不会伪装成本批新增数据。
        # 任职要求是“是否已经分析过”的审计依据；命中内容重复后保留首次正文，
        # 其余展示字段和最近发现时间仍可刷新。
        refresh_defaults = {
            field: value for field, value in defaults.items() if field != "requirements"
        }
        for field, value in refresh_defaults.items():
            setattr(listing, field, value)
        listing.save(update_fields=[*refresh_defaults, "last_seen_at"])
    return listing, created


def _college_from_name(name):
    name = str(name or "").strip()
    if not name or name == "未分配学院":
        return None
    return College.objects.filter(name=name).first()


def _match_official_node(job, parent, node_type, name):
    candidates = CapabilityNode.objects.filter(
        job=job,
        parent=parent,
        node_type=node_type,
    )
    exact = candidates.filter(normalized_name=normalise_node_name(name)).first()
    if exact:
        return exact
    threshold = {
        "ability": ABILITY_MATCH_THRESHOLD,
        "unit": UNIT_MATCH_THRESHOLD,
        "point": POINT_MATCH_THRESHOLD,
    }.get(node_type, 1.0)
    return _unique_high_confidence_match(candidates, name, threshold=threshold)


def _is_placeholder_unit(name):
    """识别旧版三等分迁移生成的无业务语义能力单元。"""
    return bool(re.fullmatch(r"能力单元\s*\d+", str(name or "").strip()))


def _node_name_similarity(left, right):
    """保守计算节点名称相似度；只用于同一岗位能力内部的旧数据兼容。"""
    left_key = normalise_node_name(left)
    right_key = normalise_node_name(right)
    if not left_key or not right_key:
        return 0.0
    if left_key == right_key:
        return 1.0
    def variants(value):
        # 正式树中经常带“（转速、进给量……）”或精度示例，这些补充说明
        # 不应让同一个技能被误判成新节点。
        raw = str(value or "")
        without_notes = re.sub(r"[（(][^）)]*[）)]", "", raw)
        return {
            normalise_node_name(raw),
            normalise_node_name(without_notes),
        } - {""}

    best = 0.0
    for left_variant in variants(left):
        for right_variant in variants(right):
            containment = 0.0
            if left_variant in right_variant or right_variant in left_variant:
                containment = min(len(left_variant), len(right_variant)) / max(
                    len(left_variant), len(right_variant)
                )
            best = max(
                best,
                containment,
                SequenceMatcher(None, left_variant, right_variant).ratio(),
            )
    return best


def _unique_high_confidence_match(nodes, name, *, threshold=POINT_MATCH_THRESHOLD):
    """返回唯一的高置信度同义节点；并列时拒绝自动匹配。"""
    scored = sorted(
        ((_node_name_similarity(name, node.name), node.id, node) for node in nodes),
        reverse=True,
        key=lambda item: (item[0], -item[1]),
    )
    if not scored or scored[0][0] < threshold:
        return None
    if len(scored) > 1 and abs(scored[0][0] - scored[1][0]) < 0.02:
        return None
    return scored[0][2]


def _match_placeholder_unit_by_points(ability_match, unit_data):
    """用明确同名知识点把AI业务单元映射回旧版占位单元，避免错误强配。"""
    if ability_match is None:
        return None
    candidate_points = {
        normalise_node_name(item.get("name"))
        for item in unit_data.get("children", [])
        if normalise_node_name(item.get("name"))
    }
    if not candidate_points:
        return None

    scored = []
    for unit in ability_match.children.filter(node_type="unit").prefetch_related("children"):
        if not _is_placeholder_unit(unit.name):
            continue
        official_points = {
            child.normalized_name
            for child in unit.children.all()
            if child.node_type == "point"
        }
        exact_score = len(candidate_points & official_points)
        semantic_score = sum(
            1
            for candidate in candidate_points
            if _unique_high_confidence_match(unit.children.filter(node_type="point"), candidate)
        )
        score = max(exact_score, semantic_score)
        if score:
            scored.append((score, unit.id, unit))
    if not scored:
        return None
    scored.sort(reverse=True, key=lambda item: (item[0], -item[1]))
    # 最高分并列意味着归属不明确，宁可保留虚体让人工判断。
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None
    return scored[0][2]


def _match_official_point(parent_official, name):
    """知识点先匹配父单元；父路径变化时，再与岗位整棵正式树保守匹配。"""
    local_nodes = (
        parent_official.children.filter(node_type="point")
        if parent_official is not None else CapabilityNode.objects.none()
    )
    exact = local_nodes.filter(normalized_name=normalise_node_name(name)).first()
    if exact:
        return exact
    local_match = _unique_high_confidence_match(
        local_nodes, name, threshold=POINT_MATCH_THRESHOLD
    )
    if local_match:
        return local_match
    return None


def _match_official_point_anywhere(job, parent_official, name):
    """同父级未命中时，避免因AI重新分组而重复新增已有知识点。"""
    matched = _match_official_point(parent_official, name)
    if matched:
        return matched
    all_points = CapabilityNode.objects.filter(job=job, node_type="point")
    exact = all_points.filter(normalized_name=normalise_node_name(name)).order_by("id").first()
    if exact:
        return exact
    return _unique_high_confidence_match(
        all_points, name, threshold=POINT_MATCH_THRESHOLD
    )


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
    batch.input_listing_count = len(valid_requirements(crawl_task, new_only=True)) if crawl_task else 0
    batch.model_name = model_name
    batch.raw_ai_output = raw_ai_output
    batch.error_message = ""
    batch.started_at = batch.started_at or timezone.now()
    batch.finished_at = timezone.now()
    batch.save()

    def add_candidate(
        data,
        node_type,
        parent_candidate,
        parent_official,
        order,
        college=None,
        matched_override=None,
    ):
        matched = matched_override or _match_official_node(
            job, parent_official, node_type, data.get("name")
        )
        candidate = AnalysisNode.objects.create(
            batch=batch,
            parent=parent_candidate,
            node_type=node_type,
            name=str(data.get("name") or "").strip(),
            normalized_name=normalise_node_name(data.get("name")),
            matched_node=matched,
            college=college,
            decision_status="not_required" if matched else "pending",
            evidence_json=normalise_evidence(data.get("evidence")),
            sort_order=order,
        )
        return candidate, matched

    for ability_order, ability_data in enumerate(normalized_tree):
        college = _college_from_name(ability_data.get("college"))
        ability_candidate, ability_match = add_candidate(
            ability_data, "ability", None, None, ability_order, college
        )
        for unit_order, unit_data in enumerate(ability_data.get("units", [])):
            unit_match = _match_official_node(
                job, ability_match, "unit", unit_data.get("name")
            )
            if unit_match is None:
                unit_match = _match_placeholder_unit_by_points(ability_match, unit_data)
            unit_candidate, unit_match = add_candidate(
                unit_data,
                "unit",
                ability_candidate,
                ability_match,
                unit_order,
                matched_override=unit_match,
            )
            matched_point_parents = set()
            for point_order, point_data in enumerate(unit_data.get("children", [])):
                point_match = _match_official_point_anywhere(
                    job, unit_match, point_data.get("name")
                )
                if point_match and point_match.parent_id:
                    matched_point_parents.add(point_match.parent_id)
                add_candidate(
                    point_data,
                    "point",
                    unit_candidate,
                    unit_match,
                    point_order,
                    matched_override=point_match,
                )
            # AI经常把正式知识点重新分组并为单元起业务名称。若所有已匹配
            # 知识点明确指向同一个正式单元，就把这个候选单元视为同一节点。
            if unit_match is None and len(matched_point_parents) == 1:
                inferred_unit = CapabilityNode.objects.filter(
                    id=next(iter(matched_point_parents)),
                    job=job,
                    node_type="unit",
                    parent=ability_match,
                ).first()
                if inferred_unit:
                    unit_candidate.matched_node = inferred_unit
                    unit_candidate.decision_status = "not_required"
                    unit_candidate.save(update_fields=[
                        "matched_node", "decision_status", "updated_at",
                    ])
    return batch


def serialize_analysis_tree(batch, *, decision_status=None):
    """将 AI 候选节点序列化成岗位能力、能力单元、知识点三层树。"""
    requirement_records = (
        analysis_requirement_records(batch.crawl_task)
        if batch.crawl_task_id else []
    )
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
        child_items = []
        for child in children.get(node.id, []):
            child_payload = item(child)
            if child_payload is not None:
                child_items.append(child_payload)

        # The candidate page is an incremental tree, rather than a copy of the
        # official capability tree.  A matched node is returned only when it is
        # an ancestor needed to show where a pending AI node will be attached.
        is_pending_virtual_leaf = (
            node.matched_node_id is None
            and node.decision_status == "pending"
            and node.node_type == "point"
        )
        if decision_status is None and not is_pending_virtual_leaf and not child_items:
            return None

        payload = {
            "id": node.id,
            "name": node.name,
            "node_type": node.node_type,
            "matched_node_id": node.matched_node_id,
            "is_virtual": node.matched_node_id is None,
            "decision_status": node.decision_status,
            "evidence": serialize_evidence_details(
                node.evidence_json,
                requirement_records=requirement_records,
            ),
            "children": child_items,
        }
        if node.node_type == "ability":
            payload["college"] = node.college.name if node.college else "未分配学院"
        return payload

    result = []
    for node in children.get(None, []):
        payload = item(node)
        if payload is not None:
            result.append(payload)
    return result


def serialize_pending_analysis_batches(batches):
    """合并一个岗位的历史完成批次，只返回当前仍需人工处理的候选路径。

    同一路径以最新批次中的状态为准：新批次已经引用或拒纳后，旧批次的
    同名候选不会再次出现；新批次没有覆盖到的旧候选则会继续保留。
    """
    batches = list(batches)
    latest_by_path = {}
    records_by_batch = {
        batch.id: (
            analysis_requirement_records(batch.crawl_task)
            if batch.crawl_task_id else []
        )
        for batch in batches
    }

    for batch in batches:
        nodes = list(batch.nodes.all())
        node_map = {node.id: node for node in nodes}
        path_cache = {}

        def path_for(node):
            if node.id in path_cache:
                return path_cache[node.id]
            segment = (node.node_type, node.normalized_name)
            parent = node_map.get(node.parent_id)
            path = (*path_for(parent), segment) if parent else (segment,)
            path_cache[node.id] = path
            return path

        for node in nodes:
            # batches 必须按新到旧传入，setdefault 才能保留最新一次状态。
            latest_by_path.setdefault(path_for(node), node)

    pending_paths = []
    for path, node in latest_by_path.items():
        if (
            node.node_type != "point"
            or node.matched_node_id
            or node.decision_status != "pending"
        ):
            continue
        # 如果最新的祖先路径已经被拒纳或被历史恢复操作关闭，则它下面的
        # 旧候选不能脱离父路径单独重新出现。
        blocked = any(
            latest_by_path[prefix].decision_status in {"rejected", "restored"}
            and not latest_by_path[prefix].matched_node_id
            for size in range(1, len(path))
            for prefix in (path[:size],)
        )
        if not blocked:
            pending_paths.append(path)

    included_paths = {
        path[:size]
        for path in pending_paths
        for size in range(1, len(path) + 1)
    }
    children = {}
    for path in included_paths:
        children.setdefault(path[:-1], []).append(path)
    for paths in children.values():
        paths.sort(key=lambda path: (
            latest_by_path[path].sort_order,
            latest_by_path[path].id,
        ))

    def item(path):
        node = latest_by_path[path]
        payload = {
            "id": node.id,
            "name": node.name,
            "node_type": node.node_type,
            "matched_node_id": node.matched_node_id,
            "is_virtual": node.matched_node_id is None,
            "decision_status": node.decision_status,
            "evidence": serialize_evidence_details(
                node.evidence_json,
                requirement_records=records_by_batch.get(node.batch_id, []),
            ),
            "children": [item(child) for child in children.get(path, [])],
        }
        if node.node_type == "ability":
            payload["college"] = node.college.name if node.college else "未分配学院"
        return payload

    return [item(path) for path in children.get((), [])]


def serialize_rejected_tree(batch):
    """返回拒纳节点，并保留未被拒纳的祖先作为只读路径上下文。"""
    requirement_records = (
        analysis_requirement_records(batch.crawl_task)
        if batch.crawl_task_id else []
    )
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
            "evidence": serialize_evidence_details(
                node.evidence_json,
                requirement_records=requirement_records,
            ),
            "decided_at": node.decided_at.isoformat() if node.decided_at else None,
            "children": [item(child) for child in children.get(node.id, [])],
        }

    return [item(node) for node in children.get(None, [])]


def merge_rejected_trees(batches):
    """把同一岗位多个分析批次的拒纳树按完整节点路径合并。

    分析批次仍保留在数据库中用于审计；这里只解决页面按批次重复绘制
    同一个岗位的问题。相同父路径下的同名节点合并，子节点与证据取并集。
    """
    merged_roots = []

    def merge_level(target, incoming):
        for node in incoming:
            key = (node.get("node_type"), normalise_node_name(node.get("name")))
            existing = next(
                (
                    item for item in target
                    if (item.get("node_type"), normalise_node_name(item.get("name"))) == key
                ),
                None,
            )
            if existing is None:
                existing = {
                    **node,
                    "children": [],
                    "source_node_ids": [node["id"]],
                    "restore_node_id": (
                        node["id"] if not node.get("context_only", False) else None
                    ),
                }
                target.append(existing)
            else:
                if node["id"] not in existing["source_node_ids"]:
                    existing["source_node_ids"].append(node["id"])
                # 只要任一批次真正拒纳过该节点，它就不只是路径上下文。
                existing["context_only"] = (
                    existing.get("context_only", True) and node.get("context_only", True)
                )
                if not node.get("context_only", False):
                    existing["restore_node_id"] = node["id"]
                existing["decision_status"] = (
                    "rejected" if not existing["context_only"] else existing["decision_status"]
                )
                evidence = normalise_evidence(existing.get("evidence"))
                incoming_evidence = normalise_evidence(node.get("evidence"))
                for value in incoming_evidence:
                    if value not in evidence:
                        evidence.append(value)
                existing["evidence"] = evidence
                if node.get("decided_at") and (
                    not existing.get("decided_at")
                    or node["decided_at"] > existing["decided_at"]
                ):
                    existing["decided_at"] = node["decided_at"]
            merge_level(existing["children"], node.get("children") or [])

    for batch in batches:
        merge_level(merged_roots, serialize_rejected_tree(batch))
    return merged_roots


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


def _latest_completed_batch(job):
    return AnalysisBatch.objects.filter(
        job=job,
        status="completed",
    ).order_by("-created_at", "-id").first()


def _find_or_copy_candidate_node(source, target_batch, parent):
    """把历史批次节点路径合并到当前候选批次，避免同名路径重复。"""
    existing = AnalysisNode.objects.filter(
        batch=target_batch,
        parent=parent,
        node_type=source.node_type,
        normalized_name=source.normalized_name,
    ).order_by("id").first()
    if existing:
        return existing
    return AnalysisNode.objects.create(
        batch=target_batch,
        parent=parent,
        node_type=source.node_type,
        name=source.name,
        matched_node=source.matched_node,
        college=source.college,
        decision_status=("not_required" if source.matched_node_id else "pending"),
        evidence_json=source.evidence_json,
        sort_order=AnalysisNode.objects.filter(batch=target_batch, parent=parent).count(),
    )


@transaction.atomic
def restore_rejected_node(node):
    """撤销拒纳，让节点重新回到当前岗位候选树，尚不写入正式图谱。"""
    if node.decision_status != "rejected":
        raise ValueError("只有已拒纳节点可以恢复")

    target_batch = _latest_completed_batch(node.batch.job) or node.batch

    # 先构造从岗位能力到选中节点的完整路径。
    path = []
    current = node
    while current:
        path.append(current)
        current = current.parent
    path.reverse()

    target_parent = None
    target_node = None
    target_path = []
    for source in path:
        if source.batch_id == target_batch.id:
            target_node = source
        else:
            target_node = _find_or_copy_candidate_node(source, target_batch, target_parent)
        target_path.append(target_node)
        target_parent = target_node

    def restore_target(target):
        target.decision_status = "not_required" if target.matched_node_id else "pending"
        target.decision_note = ""
        target.decided_at = None
        target.save(update_fields=[
            "decision_status", "decision_note", "decided_at", "updated_at",
        ])

    # 叶子节点想返回候选页，父路径也必须退出 rejected 状态，否则前端会在
    # 过滤父节点时连同刚恢复的叶子一起隐藏。
    for target in target_path:
        restore_target(target)

    def restore_source_subtree(source, target):
        restore_target(target)

        for source_child in source.children.filter(decision_status="rejected").order_by("sort_order", "id"):
            if source.batch_id == target_batch.id:
                target_child = source_child
            else:
                target_child = _find_or_copy_candidate_node(source_child, target_batch, target)
            restore_source_subtree(source_child, target_child)

    restore_source_subtree(node, target_node)

    # 历史批次保留审计节点，但退出“未采纳”集合。
    if node.batch_id != target_batch.id:
        def mark_restored(source):
            source.decision_status = "restored"
            source.decision_note = "已恢复到当前岗位候选树，尚未引用到正式图谱"
            source.decided_at = timezone.now()
            source.save(update_fields=[
                "decision_status", "decision_note", "decided_at", "updated_at",
            ])
            for child in source.children.filter(decision_status="rejected"):
                mark_restored(child)
        mark_restored(node)

    return target_node, target_batch
