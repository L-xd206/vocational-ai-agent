from django.db import models


class AbilityMap(models.Model):
    """岗位能力图谱"""
    job = models.OneToOneField("chain.Job", on_delete=models.CASCADE, related_name="ability_map", verbose_name="岗位")
    abilities_json = models.JSONField("能力列表JSON", default=list)
    total_abilities = models.IntegerField("能力项数", default=0)
    total_skills = models.IntegerField("技能点数", default=0)
    raw_text = models.TextField("原始AI输出", blank=True)
    created_at = models.DateTimeField("生成时间", auto_now_add=True)

    class Meta:
        db_table = "ability_map"
        verbose_name = "能力图谱"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.job.name} 能力图谱 ({self.total_abilities}项/{self.total_skills}技能)"


def parse_abilities_to_tree(raw_text: str) -> list:
    """
    将 "能力名---技能1/技能2/技能3" 文本解析为树形JSON
    """
    nodes = []
    for line in raw_text.strip().split("\n"):
        line = line.strip()
        if "---" not in line:
            continue
        parts = line.split("---", 1)
        ability_name = parts[0].strip()
        skills = [s.strip() for s in parts[1].split("/") if s.strip()]

        nodes.append({
            "name": ability_name,
            "enabled": True,
            "children": [{"name": s ,"enabled": True} for s in skills]
        })
    return nodes
