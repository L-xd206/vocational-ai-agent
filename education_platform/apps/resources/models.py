from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Textbook(models.Model):
    """教材知识库中的教材记录。"""

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="textbooks",
        verbose_name="所属组织",
    )
    name = models.CharField("教材名称", max_length=200)
    edition = models.CharField("版本", max_length=100, blank=True)
    publisher = models.CharField("出版社", max_length=200, blank=True)
    isbn = models.CharField("ISBN", max_length=32, blank=True)
    source_file = models.CharField("教材文件地址", max_length=500, blank=True)
    raw_text = models.TextField("教材提取文本", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_textbooks",
        verbose_name="创建人",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "resource_textbook"
        ordering = ["name", "edition", "id"]
        verbose_name = "教材"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name", "edition"],
                name="uniq_org_textbook_edition",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "name"], name="textbook_org_name_idx"),
        ]

    def __str__(self):
        suffix = f"（{self.edition}）" if self.edition else ""
        return f"{self.name}{suffix}"


class TextbookNode(models.Model):
    """教材目录节点；第一版只保留“章 → 知识点”两层。"""

    NODE_TYPES = [
        ("chapter", "章"),
        ("knowledge", "知识点"),
    ]

    textbook = models.ForeignKey(
        Textbook,
        on_delete=models.CASCADE,
        related_name="nodes",
        verbose_name="所属教材",
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
    content = models.TextField("知识内容", blank=True)
    sort_order = models.PositiveIntegerField("同级排序", default=0)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "resource_textbook_node"
        ordering = ["sort_order", "id"]
        verbose_name = "教材知识节点"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=["textbook", "node_type", "name"],
                condition=Q(parent__isnull=True),
                name="uniq_textbook_root_node",
            ),
            models.UniqueConstraint(
                fields=["textbook", "parent", "node_type", "name"],
                condition=Q(parent__isnull=False),
                name="uniq_textbook_child_node",
            ),
        ]
        indexes = [
            models.Index(fields=["textbook", "parent"], name="textbook_node_parent_idx"),
            models.Index(fields=["textbook", "node_type"], name="textbook_node_type_idx"),
        ]

    def clean(self):
        errors = {}
        if self.node_type == "chapter" and self.parent_id is not None:
            errors["parent"] = "章节点必须直接属于教材，不能设置父节点。"
        if self.node_type == "knowledge":
            if self.parent_id is None:
                errors["parent"] = "知识点必须归属于一个章节点。"
            elif self.parent.node_type != "chapter":
                errors["parent"] = "知识点的父节点必须是章。"
            elif self.parent.textbook_id != self.textbook_id:
                errors["parent"] = "父节点必须与当前节点属于同一本教材。"
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.get_node_type_display()}：{self.name}"
