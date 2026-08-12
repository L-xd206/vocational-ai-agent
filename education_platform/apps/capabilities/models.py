import json
import re

from django.db import models
from django.db.models import Q


class AbilityMap(models.Model):
    """岗位能力图谱"""
    job = models.OneToOneField("chain.Job", on_delete=models.CASCADE, related_name="ability_map", verbose_name="岗位")
    abilities_json = models.JSONField("能力列表JSON", default=list)
    total_abilities = models.IntegerField("能力项数", default=0)
    total_skills = models.IntegerField("技能点数", default=0)
    raw_text = models.TextField("原始AI输出", blank=True)
    generation_status = models.CharField("生成状态", max_length=20, default="ready")
    generation_error = models.TextField("生成错误", blank=True)
    review_status = models.CharField(
        "审核状态",
        max_length=20,
        choices=[
            ("pending", "待审核"),
            ("confirmed", "已确认"),
            ("rejected", "已退回"),
        ],
        default="pending",
    )
    review_note = models.TextField("审核意见", blank=True)
    reviewed_at = models.DateTimeField("审核时间", null=True, blank=True)
    created_at = models.DateTimeField("生成时间", auto_now_add=True)

    class Meta:
        db_table = "ability_map"
        verbose_name = "能力图谱"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.job.name} 能力图谱 ({self.total_abilities}项/{self.total_skills}技能)"


def parse_abilities_to_tree(raw_text: str) -> list:
    """
    解析新版 JSON 能力图谱，同时兼容旧版“能力名---技能1/技能2”文本。
    """
    if not raw_text:
        return []

    text = raw_text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
    json_candidates = [text]
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        json_candidates.append(text[start:end + 1])
    for candidate in json_candidates:
        try:
            payload = json.loads(candidate)
            items = payload.get("abilities", []) if isinstance(payload, dict) else payload
            if isinstance(items, list):
                return _parse_structured_abilities(items)
        except (json.JSONDecodeError, TypeError, AttributeError):
            continue

    nodes = []
    seen_abilities = set()
    for line in text.split("\n"):
        line = line.strip()
        if "---" not in line or line.startswith("---"):
            continue
        parts = line.split("---", 1)
        ability_name = _clean_name(parts[0])
        ability_key = ability_name.casefold()
        if not ability_name or ability_key in seen_abilities:
            continue
        seen_abilities.add(ability_key)
        skills = _unique_names(parts[1].split("/"))

        nodes.append({
            "name": ability_name,
            "college": "未分配学院",
            "enabled": True,
            "children": [{"name": s ,"enabled": True} for s in skills]
        })
    return nodes


def _clean_name(value):
    value = str(value or "").strip()
    return re.sub(r"^(?:[-*#\d\.、）)]+\s*)", "", value).strip()


def _unique_names(values):
    result = []
    seen = set()
    for value in values:
        name = _clean_name(value)
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            result.append(name)
    return result


def _parse_structured_abilities(items):
    nodes = []
    seen_abilities = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = _clean_name(item.get("name"))
        key = name.casefold()
        if not name or key in seen_abilities:
            continue
        seen_abilities.add(key)
        node = {
            "name": name,
            "college": str(item.get("college") or "未分配学院"),
            "enabled": True,
        }
        units = item.get("units")
        if isinstance(units, list):
            node["units"] = _parse_structured_units(units)
        else:
            # 兼容旧版 AI 的 ability.skills / ability.children 两层结构，
            # 后续由 normalise_legacy_tree 自动补出能力单元。
            node["children"] = _parse_structured_points(
                item.get("skills", item.get("children", [])) or []
            )
        if item.get("evidence"):
            node["evidence"] = str(item["evidence"]).strip()
        nodes.append(node)
    return nodes


def _parse_structured_units(items):
    units = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = _clean_name(item.get("name"))
        key = name.casefold()
        if not name or key in seen:
            continue
        seen.add(key)
        unit = {
            "name": name,
            "enabled": True,
            "children": _parse_structured_points(item.get("children", item.get("skills", [])) or []),
        }
        if item.get("evidence"):
            unit["evidence"] = str(item["evidence"]).strip()
        units.append(unit)
    return units


def _parse_structured_points(items):
    points = []
    seen = set()
    for item in items:
        if isinstance(item, dict):
            name = _clean_name(item.get("name"))
            point = {"name": name, "enabled": True}
            for field in ("evidence", "assessment"):
                if item.get(field):
                    point[field] = str(item[field]).strip()
        else:
            name = _clean_name(item)
            point = {"name": name, "enabled": True}
        key = name.casefold()
        if not name or key in seen:
            continue
        seen.add(key)
        points.append(point)
    return points


def normalise_node_name(value):
    """生成用于同级去重和 AI 匹配的稳定名称。"""
    return re.sub(r"\s+", "", _clean_name(value)).casefold()


class CapabilityNode(models.Model):
    """正式能力图谱节点：岗位能力、能力单元或知识点/技能点。"""

    NODE_TYPES = [
        ("ability", "岗位能力"),
        ("unit", "能力单元"),
        ("point", "知识点/技能点"),
    ]
    ORIGIN_TYPES = [
        ("manual", "人工创建"),
        ("ai", "AI 分析并引用"),
        ("legacy", "历史 JSON 迁移"),
    ]

    job = models.ForeignKey(
        "chain.Job", on_delete=models.CASCADE,
        related_name="capability_nodes", verbose_name="所属岗位",
    )
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, related_name="children",
        null=True, blank=True, verbose_name="父节点",
    )
    node_type = models.CharField("节点类型", max_length=20, choices=NODE_TYPES)
    name = models.CharField("节点名称", max_length=200)
    normalized_name = models.CharField("标准化名称", max_length=200, editable=False)
    college = models.ForeignKey(
        "organizations.College", on_delete=models.SET_NULL,
        related_name="capability_nodes", null=True, blank=True,
        verbose_name="所属学院",
    )
    origin = models.CharField(
        "节点来源", max_length=20, choices=ORIGIN_TYPES, default="manual",
    )
    is_enabled = models.BooleanField("是否启用", default=True)
    sort_order = models.PositiveIntegerField("同级排序", default=0)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "capability_node"
        ordering = ["sort_order", "id"]
        verbose_name = "能力节点"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=["job", "node_type", "normalized_name"],
                condition=Q(parent__isnull=True),
                name="uniq_root_capability_name",
            ),
            models.UniqueConstraint(
                fields=["job", "parent", "node_type", "normalized_name"],
                condition=Q(parent__isnull=False),
                name="uniq_child_capability_name",
            ),
        ]
        indexes = [
            models.Index(fields=["job", "parent"], name="cap_node_job_parent_idx"),
            models.Index(fields=["job", "node_type"], name="cap_node_job_type_idx"),
        ]

    def save(self, *args, **kwargs):
        self.normalized_name = normalise_node_name(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_node_type_display()}：{self.name}"
