from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class CourseQuestion(models.Model):
    """课程知识点下的试题；发布状态统一由所属课程树控制。"""

    QUESTION_TYPES = [
        ("single", "单选题"),
        ("multiple", "多选题"),
        ("judgment", "判断题"),
        ("short", "简答题"),
    ]
    DIFFICULTIES = [
        ("easy", "简单"),
        ("medium", "中等"),
        ("hard", "困难"),
    ]

    node = models.ForeignKey(
        "curriculum.CourseTreeNode",
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name="所属知识点",
    )
    question_type = models.CharField("题型", max_length=20, choices=QUESTION_TYPES)
    stem = models.TextField("题干")
    options = models.JSONField("选项", default=list, blank=True)
    correct_answer = models.JSONField("正确答案", default=list)
    analysis = models.TextField("答案解析", blank=True)
    difficulty = models.CharField(
        "难度",
        max_length=20,
        choices=DIFFICULTIES,
        default="medium",
    )
    sort_order = models.PositiveIntegerField("排序", default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_course_questions",
        verbose_name="创建人",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "teaching_course_question"
        ordering = ["sort_order", "id"]
        verbose_name = "课程试题"
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=["node", "question_type"], name="question_node_type_idx"),
            models.Index(fields=["node", "difficulty"], name="question_difficulty_idx"),
        ]

    def clean(self):
        errors = {}
        if self.node_id and self.node.node_type != "knowledge":
            errors["node"] = "试题只能关联课程树中的知识点节点。"
        if self.question_type in {"single", "multiple"} and not self.options:
            errors["options"] = "选择题必须提供选项。"
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.get_question_type_display()}：{self.stem[:30]}"
