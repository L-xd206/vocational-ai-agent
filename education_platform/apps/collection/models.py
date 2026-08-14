from django.db import models
from django.db.models import Q
from django.core.validators import MinValueValidator


class CrawlSource(models.Model):
    """招聘数据采集来源。"""

    name = models.CharField(
        "来源名称",
        max_length=100,
        unique=True,
    )

    code = models.CharField(
        "来源编码",
        max_length=50,
        unique=True,
    )

    base_url = models.URLField(
        "来源地址",
        max_length=500,
    )

    interval_minutes = models.PositiveIntegerField(
        "采集间隔（分钟）",
        default=1440,
        validators=[MinValueValidator(1)],
    )

    is_enabled = models.BooleanField(
        "是否启用",
        default=True,
    )

    config_json = models.JSONField(
        "附加配置",
        default=dict,
        blank=True,
    )

    last_run_at = models.DateTimeField(
        "上次执行时间",
        null=True,
        blank=True,
    )

    next_run_at = models.DateTimeField(
        "下次执行时间",
        null=True,
        blank=True,
        db_index=True,
    )

    created_at = models.DateTimeField(
        "创建时间",
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        "更新时间",
        auto_now=True,
    )

    class Meta:
        db_table = "crawl_source"
        ordering = ["id"]

    def __str__(self):
        return self.name


class CrawlTask(models.Model):
    """一次岗位数据采集任务。"""

    STATUS_CHOICES = [
        ("pending", "等待执行"),
        ("running", "执行中"),
        ("completed", "执行完成"),
        ("failed", "执行失败"),
    ]

    TRIGGER_CHOICES = [
        ("manual", "手动触发"),
        ("scheduled", "定时触发"),
    ]

    # 原有字段：保留
    job = models.ForeignKey(
        "chain.Job",
        on_delete=models.CASCADE,
        related_name="crawl_tasks",
        verbose_name="岗位",
    )

    # 新增字段
    source = models.ForeignKey(
        CrawlSource,
        on_delete=models.PROTECT,
        related_name="tasks",
        verbose_name="采集来源",
        null=True,
        blank=True,
    )

    # 新增字段
    trigger_type = models.CharField(
        "触发方式",
        max_length=20,
        choices=TRIGGER_CHOICES,
        default="manual",
    )

    # 原有字段：补充 verbose_name 和 db_index 即可
    status = models.CharField(
        "状态",
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )

    # 原有字段：保留
    total_keywords = models.IntegerField(
        "关键词数量",
        default=0,
    )

    # 原有字段：保留
    total_results = models.IntegerField(
        "采集结果数",
        default=0,
    )

    # 新增字段
    new_results = models.IntegerField(
        "新增结果数",
        default=0,
    )

    # 原有字段：暂时保留
    results_json = models.JSONField(
        "原始结果",
        default=list,
    )

    # 新增字段
    error_message = models.TextField(
        "错误信息",
        blank=True,
    )

    # 新增字段
    scheduled_at = models.DateTimeField(
        "计划执行时间",
        null=True,
        blank=True,
    )

    # 新增字段
    started_at = models.DateTimeField(
        "开始时间",
        null=True,
        blank=True,
    )

    # 新增字段
    finished_at = models.DateTimeField(
        "结束时间",
        null=True,
        blank=True,
    )

    # 原有字段：保留
    created_at = models.DateTimeField(
        "创建时间",
        auto_now_add=True,
    )

    class Meta:
        db_table = "crawl_task"
        verbose_name = "采集任务"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=["job", "source"],
                condition=Q(status__in=["pending", "running"]),
                name="uniq_active_crawl_task_per_job_source",
            ),
        ]

    def __str__(self):
        return f"Task #{self.id} - {self.job.name}"


class AnalysisBatch(models.Model):
    """某岗位基于一次采集结果执行的一次 AI 候选能力分析。"""

    STATUS_CHOICES = [
        ("pending", "等待分析"),
        ("processing", "分析中"),
        ("completed", "分析完成"),
        ("skipped", "数据不足，已跳过"),
        ("failed", "分析失败"),
    ]

    job = models.ForeignKey(
        "chain.Job",
        on_delete=models.CASCADE,
        related_name="analysis_batches",
        verbose_name="所属岗位",
    )
    crawl_task = models.ForeignKey(
        CrawlTask,
        on_delete=models.SET_NULL,
        related_name="analysis_batches",
        null=True,
        blank=True,
        verbose_name="来源采集任务",
    )
    status = models.CharField(
        "分析状态",
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )
    input_listing_count = models.PositiveIntegerField("输入招聘数据数量", default=0)
    model_name = models.CharField("使用的大模型", max_length=100, blank=True)
    raw_ai_output = models.TextField("AI 原始输出", blank=True)
    error_message = models.TextField("错误信息", blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    finished_at = models.DateTimeField("完成时间", null=True, blank=True)

    class Meta:
        db_table = "analysis_batch"
        ordering = ["-created_at"]
        verbose_name = "AI 分析批次"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=["crawl_task"],
                condition=Q(crawl_task__isnull=False),
                name="uniq_analysis_batch_per_crawl_task",
            ),
        ]

    def __str__(self):
        return f"{self.job.name} - 分析批次 #{self.pk or '未保存'}"


class AnalysisNode(models.Model):
    """岗位采集数据经 AI 分析产生的候选能力节点。"""

    NODE_TYPES = [
        ("ability", "岗位能力"),
        ("unit", "能力单元"),
        ("point", "知识点/技能点"),
    ]
    DECISION_CHOICES = [
        ("not_required", "已存在，无需处理"),
        ("pending", "等待处理"),
        ("adopted", "已引用"),
        ("rejected", "已拒纳"),
        ("restored", "已恢复到新批次"),
    ]

    batch = models.ForeignKey(
        AnalysisBatch,
        on_delete=models.CASCADE,
        related_name="nodes",
        verbose_name="所属分析批次",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="children",
        null=True,
        blank=True,
        verbose_name="父分析节点",
    )
    node_type = models.CharField("节点类型", max_length=20, choices=NODE_TYPES)
    name = models.CharField("节点名称", max_length=200)
    normalized_name = models.CharField("标准化名称", max_length=200, editable=False)
    matched_node = models.ForeignKey(
        "ability.CapabilityNode",
        on_delete=models.SET_NULL,
        related_name="analysis_matches",
        null=True,
        blank=True,
        verbose_name="匹配的正式能力节点",
    )
    college = models.ForeignKey(
        "organizations.College",
        on_delete=models.SET_NULL,
        related_name="analysis_nodes",
        null=True,
        blank=True,
        verbose_name="建议所属学院",
    )
    decision_status = models.CharField(
        "处理状态",
        max_length=20,
        choices=DECISION_CHOICES,
        default="pending",
        db_index=True,
    )
    decision_note = models.TextField("处理说明", blank=True)
    evidence_json = models.JSONField("分析证据", default=list, blank=True)
    sort_order = models.PositiveIntegerField("同级排序", default=0)
    decided_at = models.DateTimeField("处理时间", null=True, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "analysis_node"
        ordering = ["sort_order", "id"]
        verbose_name = "AI 分析节点"
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=["batch", "parent"], name="ana_node_batch_parent_idx"),
            models.Index(fields=["batch", "decision_status"], name="ana_node_batch_state_idx"),
        ]

    @property
    def is_virtual(self):
        return self.matched_node_id is None

    def save(self, *args, **kwargs):
        from apps.capabilities.models import normalise_node_name

        self.normalized_name = normalise_node_name(self.name)
        if self.matched_node_id and self.decision_status == "pending":
            self.decision_status = "not_required"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_node_type_display()}：{self.name}"


class JobListing(models.Model):
    """单条招聘信息。"""

    task = models.ForeignKey(
        CrawlTask,
        on_delete=models.SET_NULL,
        related_name="listings",
        verbose_name="所属采集任务",
        null=True,
        blank=True,
    )

    # 这条招聘信息对应的系统岗位
    job = models.ForeignKey(
        "chain.Job",
        on_delete=models.CASCADE,
        related_name="job_listings",
        verbose_name="所属岗位",
        null=True,
        blank=True,
    )

    # 新增：对应的采集来源配置
    #
    # 注意这里故意叫 crawl_source，
    # 因为原来的 source 字段已经是普通文字字段。
    crawl_source = models.ForeignKey(
        CrawlSource,
        on_delete=models.PROTECT,
        related_name="job_listings",
        verbose_name="采集来源配置",
        null=True,
        blank=True,
    )

    # 用于判断招聘信息是否重复
    #
    # 旧数据还没有指纹，所以暂时允许为空。
    fingerprint = models.CharField(
        "数据指纹",
        max_length=64,
        db_index=True,
        null=True,
        blank=True,
    )

    # 只由任职要求正文生成，用来判断“这份能力信息以前是否分析过”。
    # 它与上面的招聘记录指纹分开：企业或标题改变，不代表能力内容变新。
    content_fingerprint = models.CharField(
        "任职要求内容指纹",
        max_length=64,
        db_index=True,
        blank=True,
        default="",
    )

    # 招聘详情网页地址
    source_url = models.URLField(
        "招聘详情地址",
        max_length=1000,
        blank=True,
    )

    # 原有字段：保留
    title = models.CharField(
        "岗位名称",
        max_length=200,
    )

    # 原有字段：保留
    company = models.CharField(
        "公司",
        max_length=200,
    )

    # 原有字段：保留
    city = models.CharField(
        "城市",
        max_length=100,
        blank=True,
    )

    # 原有字段：保留
    salary = models.CharField(
        "薪资",
        max_length=100,
        blank=True,
    )

    # 原有字段：保留
    education = models.CharField(
        "学历",
        max_length=50,
        blank=True,
    )

    # 原有字段：保留
    requirements = models.TextField(
        "任职要求",
        blank=True,
    )

    # 原有字段：保留
    headcount = models.CharField(
        "招聘人数",
        max_length=20,
        blank=True,
    )

    # 原有字段：保留
    post_date = models.CharField(
        "发布日期",
        max_length=50,
        blank=True,
    )

    # 原有字段：保留。
    # 这里记录网站返回的文字来源，例如“BOSS直聘”。
    source = models.CharField(
        "原始来源名称",
        max_length=100,
        blank=True,
    )

    # 保存网站返回的完整原始数据
    raw_json = models.JSONField(
        "原始数据",
        default=dict,
        blank=True,
    )

    # 第一次发现这条招聘信息的时间
    first_seen_at = models.DateTimeField(
        "首次发现时间",
        auto_now_add=True,
    )

    # 最近一次发现这条招聘信息的时间
    last_seen_at = models.DateTimeField(
        "最近发现时间",
        auto_now=True,
    )

    class Meta:
        db_table = "job_listing"
        verbose_name = "招聘信息"
        verbose_name_plural = "招聘信息"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "job",
                    "crawl_source",
                    "fingerprint",
                ],
                name="unique_listing_per_job_source",
            ),
        ]

    def __str__(self):
        return f"{self.title} - {self.company}"
