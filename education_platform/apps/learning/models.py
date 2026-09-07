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

    def __str__(self):
        return f"{self.student.name} - {self.get_plan_type_display()}"


class PlanCourse(models.Model):
    """计划所含的课程（一个计划可含多门课，可排序）。"""

    plan = models.ForeignKey(
        LearningPlan, on_delete=models.CASCADE,
        related_name="courses", verbose_name="所属计划",
    )
    course_tree = models.ForeignKey(
        "curriculum.CourseTree", on_delete=models.CASCADE,
        related_name="plan_courses", verbose_name="课程",
    )
    sort_order = models.PositiveIntegerField("排序", default=0)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "learning_plan_course"
        ordering = ["sort_order", "id"]
        verbose_name = "计划课程"
        verbose_name_plural = verbose_name
        unique_together = [("plan", "course_tree")]

    def __str__(self):
        return f"{self.plan} 含 {self.course_tree.name}"


class PlanPoint(models.Model):
    """计划中选中的知识点（计划调整加入，支撑部分选择）。"""

    plan_course = models.ForeignKey(
        PlanCourse, on_delete=models.CASCADE,
        related_name="points", verbose_name="所属计划课程",
    )
    node = models.ForeignKey(
        "curriculum.CourseTreeNode", on_delete=models.CASCADE,
        related_name="plan_points", verbose_name="知识点",
    )
    sort_order = models.PositiveIntegerField("排序", default=0)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "learning_plan_point"
        ordering = ["sort_order", "id"]
        verbose_name = "计划知识点"
        verbose_name_plural = verbose_name
        unique_together = [("plan_course", "node")]

    def __str__(self):
        return f"{self.plan_course} · {self.node.name}"


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


class LearningProgress(models.Model):
    """学习进度：学生在某知识点上是否完成（有记录=已完成）。"""

    student = models.ForeignKey(
        "organizations.Student", on_delete=models.CASCADE,
        related_name="learning_progresses", verbose_name="学生",
    )
    node = models.ForeignKey(
        "curriculum.CourseTreeNode", on_delete=models.CASCADE,
        related_name="learning_progresses", verbose_name="知识点",
    )
    completed_at = models.DateTimeField("完成时间", auto_now_add=True)

    class Meta:
        db_table = "learning_progress"
        unique_together = [("student", "node")]
        verbose_name = "学习进度"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.student.name} 完成 {self.node.name}"


class AssessmentRun(models.Model):
    """一次测评（随堂练习/章节测验/课程综合测验）。"""

    class Scope(models.TextChoices):
        POINT = "point", "知识点"
        CHAPTER = "chapter", "章节"
        COURSE = "course", "课程"

    student = models.ForeignKey(
        "organizations.Student", on_delete=models.CASCADE,
        related_name="assessment_runs", verbose_name="学生",
    )
    plan = models.ForeignKey(
        LearningPlan, on_delete=models.CASCADE, null=True, blank=True,
        related_name="assessment_runs", verbose_name="来源学习计划",
    )
    scope = models.CharField("测评范围", max_length=20, choices=Scope.choices)
    node = models.ForeignKey(
        "curriculum.CourseTreeNode", on_delete=models.CASCADE, null=True, blank=True,
        related_name="assessment_runs", verbose_name="关联节点",
    )
    title = models.CharField("测评标题", max_length=200)
    # 题面快照（抽题时固化的题目 id 列表），防止题库变化影响已交测评
    question_ids = models.JSONField("题目id快照", default=list)
    score = models.PositiveIntegerField("得分", default=0)
    total = models.PositiveIntegerField("总分", default=0)
    correct_count = models.PositiveIntegerField("答对数", default=0)
    wrong_count = models.PositiveIntegerField("答错数", default=0)
    submitted_at = models.DateTimeField("提交时间", auto_now_add=True)

    class Meta:
        db_table = "learning_assessment_run"
        ordering = ["-submitted_at"]
        verbose_name = "测评记录"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.student.name} - {self.title} ({self.score}/{self.total})"


class AssessmentAnswer(models.Model):
    """测评中某道题的作答明细（学生选择 + 对错）。"""

    run = models.ForeignKey(
        AssessmentRun, on_delete=models.CASCADE,
        related_name="answers", verbose_name="所属测评",
    )
    question = models.ForeignKey(
        "teaching.CourseQuestion", on_delete=models.CASCADE,
        related_name="assessment_answers", verbose_name="题目",
    )
    node = models.ForeignKey(
        "curriculum.CourseTreeNode", on_delete=models.CASCADE,
        null=True, blank=True, related_name="assessment_answers", verbose_name="知识点",
    )
    chosen = models.JSONField("学生答案", default=list)
    is_correct = models.BooleanField("是否正确", default=False)

    class Meta:
        db_table = "learning_assessment_answer"
        verbose_name = "测评作答"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.run} Q{self.question_id} {'✓' if self.is_correct else '✗'}"
