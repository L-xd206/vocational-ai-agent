from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
import re


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
        options = self.options if isinstance(self.options, list) else []
        answers = self.correct_answer if isinstance(self.correct_answer, list) else []
        if not isinstance(self.options, list):
            errors["options"] = "选项必须是数组。"
        if not isinstance(self.correct_answer, list):
            errors["correct_answer"] = "参考答案必须是数组。"
        if not self.stem.strip():
            errors["stem"] = "题目内容不能为空。"
        elif len(self.stem.strip()) > 2000:
            errors["stem"] = "题目内容不能超过 2000 字。"

        if self.question_type in {"single", "multiple"}:
            if not 2 <= len(options) <= 6:
                errors["options"] = "单选题和多选题必须填写 2 至 6 个选项。"
            labels = []
            texts = []
            for option in options:
                match = re.match(r"^\s*([A-F])\s*[.、:：]\s*(.+)$", str(option), flags=re.IGNORECASE)
                if not match:
                    errors["options"] = "每个选项必须采用“ A. 选项内容 ”格式。"
                    break
                labels.append(match.group(1).upper())
                texts.append(match.group(2).strip().casefold())
            expected = [chr(ord("A") + index) for index in range(len(options))]
            if labels and labels != expected:
                errors["options"] = "选项编号必须从 A 开始连续排列。"
            if len(texts) != len(set(texts)):
                errors["options"] = "选项内容不能重复。"
            normalized_answers = [str(answer).strip().upper() for answer in answers if str(answer).strip()]
            if not normalized_answers:
                errors["correct_answer"] = "选择题必须填写正确答案。"
            elif any(answer not in labels for answer in normalized_answers):
                errors["correct_answer"] = "正确答案必须是已有选项的编号。"
            elif self.question_type == "single" and len(normalized_answers) != 1:
                errors["correct_answer"] = "单选题必须且只能有一个正确答案。"
            elif self.question_type == "multiple" and len(normalized_answers) < 2:
                errors["correct_answer"] = "多选题至少需要两个正确答案。"
        elif self.question_type == "judgment":
            normalized_answers = [str(answer).strip().lower() for answer in answers if str(answer).strip()]
            if options:
                errors["options"] = "判断题不需要填写选项。"
            if len(normalized_answers) != 1 or normalized_answers[0] not in {"true", "false", "正确", "错误", "对", "错"}:
                errors["correct_answer"] = "判断题答案只能填写“正确”或“错误”。"
        elif self.question_type == "short":
            if options:
                errors["options"] = "主观题不需要填写选项。"
            if not answers and not self.analysis.strip():
                errors["correct_answer"] = "主观题至少要填写参考答案或评分标准。"
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.get_question_type_display()}：{self.stem[:30]}"
