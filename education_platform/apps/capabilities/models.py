import json
import re

from django.db import models


class AbilityMap(models.Model):
    """岗位能力图谱"""
    job = models.OneToOneField("chain.Job", on_delete=models.CASCADE, related_name="ability_map", verbose_name="岗位")
    abilities_json = models.JSONField("能力列表JSON", default=list)
    total_abilities = models.IntegerField("能力项数", default=0)
    total_skills = models.IntegerField("技能点数", default=0)
    raw_text = models.TextField("原始AI输出", blank=True)
    generation_status = models.CharField("生成状态", max_length=20, default="ready")
    generation_error = models.TextField("生成错误", blank=True)
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
        skills = item.get("skills", item.get("children", [])) or []
        children = []
        seen_skills = set()
        for skill in skills:
            if isinstance(skill, dict):
                skill_name = _clean_name(skill.get("name"))
                child = {"name": skill_name, "enabled": True}
                for field in ("evidence", "assessment"):
                    if skill.get(field):
                        child[field] = str(skill[field]).strip()
            else:
                skill_name = _clean_name(skill)
                child = {"name": skill_name, "enabled": True}
            skill_key = skill_name.casefold()
            if not skill_name or skill_key in seen_skills:
                continue
            seen_skills.add(skill_key)
            children.append(child)
        node = {
            "name": name,
            "college": str(item.get("college") or "未分配学院"),
            "enabled": True,
            "children": children,
        }
        if item.get("evidence"):
            node["evidence"] = str(item["evidence"]).strip()
        nodes.append(node)
    return nodes
