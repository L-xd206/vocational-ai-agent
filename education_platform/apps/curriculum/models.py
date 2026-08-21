from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class CourseTree(models.Model):
    """一条记录代表某个组织收到并转换后的一棵课程树。"""

    COURSE_TYPES = [
        ("theory", "理论"),
        ("practice", "实训"),
        ("integrated", "理实一体"),
    ]

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="course_trees",
        verbose_name="所属组织",
    )
    textbook = models.ForeignKey(
        "resources.Textbook",
        on_delete=models.PROTECT,
        related_name="course_trees",
        verbose_name="对应教材",
    )
    name = models.CharField("课程名称", max_length=200)
    course_type = models.CharField(
        "课程类型",
        max_length=20,
        choices=COURSE_TYPES,
        default="integrated",
    )
    total_hours = models.PositiveIntegerField("学时", default=0)
    credits = models.DecimalField("学分", max_digits=5, decimal_places=1, default=0)
    source_ability = models.ForeignKey(
        "ability.CapabilityNode",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={"node_type": "ability"},
        related_name="generated_course_trees",
        verbose_name="来源岗位能力",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_course_trees",
        verbose_name="课程负责人",
    )
    source_snapshot = models.JSONField(
        "正式树快照",
        default=dict,
        help_text="保存转换时的岗位能力、能力单元和知识点，来源节点删除后仍可追溯。",
    )
    is_published = models.BooleanField("是否发布", default=False)
    published_at = models.DateTimeField("发布时间", null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_course_trees",
        verbose_name="创建人",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "curriculum_course_tree"
        ordering = ["-updated_at", "-id"]
        verbose_name = "课程树"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "source_ability"],
                name="uniq_org_source_ability_tree",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "owner"], name="course_tree_org_owner_idx"),
            models.Index(fields=["organization", "is_published"], name="course_tree_publish_idx"),
        ]

    def clean(self):
        errors = {}
        if self.textbook_id and self.organization_id:
            if self.textbook.organization_id != self.organization_id:
                errors["textbook"] = "课程树和教材必须属于同一个组织。"
        if self.source_ability_id and self.source_ability.node_type != "ability":
            errors["source_ability"] = "课程树来源必须是岗位能力节点。"
        if self.owner_id:
            profile = getattr(self.owner, "profile", None)
            if profile is None or profile.organization_id != self.organization_id:
                errors["owner"] = "课程负责人必须属于当前组织。"
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.organization} - {self.name}"


class CourseTreeNode(models.Model):
    """课程树节点；课程根在 CourseTree，节点表只保存“章 → 知识点”。"""

    NODE_TYPES = [
        ("chapter", "章"),
        ("knowledge", "知识点"),
    ]

    tree = models.ForeignKey(
        CourseTree,
        on_delete=models.CASCADE,
        related_name="nodes",
        verbose_name="所属课程树",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="父节点",
    )
    node_type = models.CharField("节点类型", max_length=20, choices=NODE_TYPES)
    name = models.CharField("节点名称", max_length=200)
    source_node = models.ForeignKey(
        "ability.CapabilityNode",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="course_tree_nodes",
        verbose_name="来源正式树节点",
    )
    textbook_node = models.ForeignKey(
        "resources.TextbookNode",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="course_tree_nodes",
        verbose_name="对应教材节点",
    )
    task_description = models.TextField("学习任务描述", blank=True)
    work_scenario = models.TextField("工作情境", blank=True)
    operation_steps = models.JSONField("操作步骤", default=list, blank=True)
    safety_points = models.JSONField("安全要点", default=list, blank=True)
    resource_links = models.JSONField("教学资源", default=list, blank=True)
    is_edited = models.BooleanField("是否编辑完成", default=False)
    sort_order = models.PositiveIntegerField("同级排序", default=0)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "curriculum_course_tree_node"
        ordering = ["sort_order", "id"]
        verbose_name = "课程树节点"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=["tree", "source_node"],
                name="uniq_course_tree_source_node",
            ),
            models.UniqueConstraint(
                fields=["tree", "node_type", "name"],
                condition=Q(parent__isnull=True),
                name="uniq_course_tree_root_node",
            ),
            models.UniqueConstraint(
                fields=["tree", "parent", "node_type", "name"],
                condition=Q(parent__isnull=False),
                name="uniq_course_tree_child_node",
            ),
        ]
        indexes = [
            models.Index(fields=["tree", "parent"], name="course_node_parent_idx"),
            models.Index(fields=["tree", "node_type"], name="course_node_type_idx"),
        ]

    def clean(self):
        errors = {}
        if self.node_type == "chapter" and self.parent_id is not None:
            errors["parent"] = "章节点必须直接属于课程树。"
        if self.node_type == "knowledge":
            if self.parent_id is None:
                errors["parent"] = "知识点必须归属于一个章节点。"
            elif self.parent.node_type != "chapter":
                errors["parent"] = "知识点的父节点必须是章。"
            elif self.parent.tree_id != self.tree_id:
                errors["parent"] = "父节点必须与当前节点属于同一棵课程树。"
        expected_source_type = "unit" if self.node_type == "chapter" else "point"
        if self.source_node_id and self.source_node.node_type != expected_source_type:
            errors["source_node"] = f"当前节点必须对应 {expected_source_type} 类型的正式树节点。"
        expected_textbook_type = self.node_type
        if self.textbook_node_id:
            if self.textbook_node.node_type != expected_textbook_type:
                errors["textbook_node"] = "教材节点类型与课程树节点类型不一致。"
            elif self.textbook_node.textbook_id != self.tree.textbook_id:
                errors["textbook_node"] = "教材节点必须属于课程树所对应的教材。"
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.get_node_type_display()}：{self.name}"
