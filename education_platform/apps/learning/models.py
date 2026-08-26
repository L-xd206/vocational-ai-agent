from django.db import models


class LearningPlan(models.Model):
    """学习计划。学期计划来自教学安排自动派生，自主学习/AI推荐由学生维护。"""

    class PlanType(models.TextChoices):
        SEMESTER = "semester", "学期计划"
        SELF = "self", "自主学习"
        AI = "ai", "AI推荐"

    class Status(models.TextChoices):
        TODO = "todo", "未开始"
        DOING = "doing", "进行中"
        DONE = "done", "已完成"

    student = models.ForeignKey(
        "organizations.Student", on_delete=models.CASCADE,
        related_name="learning_plans", verbose_name="学生",
    )
    name = models.CharField("计划名称", max_length=100)
    course_tree = models.ForeignKey(
        "curriculum.CourseTree", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="learning_plans", verbose_name="课程树",
    )
    plan_type = models.CharField(
        "计划类型", max_length=20, choices=PlanType.choices, default=PlanType.SELF,
    )
    category = models.CharField("分类", max_length=50, blank=True)
    status = models.CharField(
        "状态", max_length=20, choices=Status.choices, default=Status.TODO,
    )
    progress = models.PositiveIntegerField("进度", default=0)
    learned_hours = models.PositiveIntegerField("已学学时", default=0)
    total_hours = models.PositiveIntegerField("总学时", default=0)
    deadline = models.DateField("截止日期", null=True, blank=True)
    teacher = models.CharField("教师", max_length=50, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "learning_plan"
        ordering = ["-created_at"]
        verbose_name = "学习计划"
        verbose_name_plural = verbose_name
        unique_together = [("student", "course_tree", "plan_type")]

    def __str__(self):
        return f"{self.student.name} - {self.get_plan_type_display()}"


class PlanDeleteLog(models.Model):
    """学习计划删除日志（软删痕迹，自主学习/AI推荐删除时记录原因）。"""

    student = models.ForeignKey(
        "organizations.Student", on_delete=models.CASCADE,
        related_name="plan_delete_logs", verbose_name="学生",
    )
    plan_name = models.CharField("计划名称", max_length=100)
    category = models.CharField("分类", max_length=50, blank=True)
    progress = models.PositiveIntegerField("进度", default=0)
    reason = models.CharField("删除原因", max_length=200)
    deleted_at = models.DateTimeField("删除时间", auto_now_add=True)

    class Meta:
        db_table = "learning_plan_delete_log"
        ordering = ["-deleted_at"]
        verbose_name = "学习计划删除日志"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.student.name} 删除 {self.plan_name}"


class LearningRecord(models.Model):
    """学习记录时间线（入学/里程碑/成就/测评事件）。"""

    student = models.ForeignKey(
        "organizations.Student", on_delete=models.CASCADE,
        related_name="learning_records", verbose_name="学生",
    )
    title = models.CharField("标题", max_length=100)
    description = models.CharField("描述", max_length=500, blank=True)
    tag = models.CharField("标签", max_length=20, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "learning_record"
        ordering = ["-created_at"]
        verbose_name = "学习记录"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.student.name} - {self.title}"
