import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """让 crawl App 接管既有分析表，不执行建表或数据复制。"""

    dependencies = [
        ("ability", "0005_move_analysis_models_to_crawl"),
        ("crawl", "0004_alter_joblisting_task"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="AnalysisBatch",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        (
                            "status",
                            models.CharField(
                                choices=[
                                    ("pending", "等待分析"),
                                    ("processing", "分析中"),
                                    ("completed", "分析完成"),
                                    ("failed", "分析失败"),
                                ],
                                db_index=True,
                                default="pending",
                                max_length=20,
                                verbose_name="分析状态",
                            ),
                        ),
                        (
                            "input_listing_count",
                            models.PositiveIntegerField(
                                default=0,
                                verbose_name="输入招聘数据数量",
                            ),
                        ),
                        (
                            "model_name",
                            models.CharField(
                                blank=True,
                                max_length=100,
                                verbose_name="使用的大模型",
                            ),
                        ),
                        (
                            "raw_ai_output",
                            models.TextField(blank=True, verbose_name="AI 原始输出"),
                        ),
                        (
                            "error_message",
                            models.TextField(blank=True, verbose_name="错误信息"),
                        ),
                        ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                        ("started_at", models.DateTimeField(blank=True, null=True, verbose_name="开始时间")),
                        ("finished_at", models.DateTimeField(blank=True, null=True, verbose_name="完成时间")),
                        (
                            "crawl_task",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="analysis_batches",
                                to="crawl.crawltask",
                                verbose_name="来源采集任务",
                            ),
                        ),
                        (
                            "job",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="analysis_batches",
                                to="chain.job",
                                verbose_name="所属岗位",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "AI 分析批次",
                        "verbose_name_plural": "AI 分析批次",
                        "db_table": "analysis_batch",
                        "ordering": ["-created_at"],
                    },
                ),
                migrations.CreateModel(
                    name="AnalysisNode",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        (
                            "node_type",
                            models.CharField(
                                choices=[
                                    ("ability", "岗位能力"),
                                    ("unit", "能力单元"),
                                    ("point", "知识点/技能点"),
                                ],
                                max_length=20,
                                verbose_name="节点类型",
                            ),
                        ),
                        ("name", models.CharField(max_length=200, verbose_name="节点名称")),
                        (
                            "normalized_name",
                            models.CharField(
                                editable=False,
                                max_length=200,
                                verbose_name="标准化名称",
                            ),
                        ),
                        (
                            "decision_status",
                            models.CharField(
                                choices=[
                                    ("not_required", "已存在，无需处理"),
                                    ("pending", "等待处理"),
                                    ("adopted", "已引用"),
                                    ("rejected", "已拒纳"),
                                ],
                                db_index=True,
                                default="pending",
                                max_length=20,
                                verbose_name="处理状态",
                            ),
                        ),
                        (
                            "decision_note",
                            models.TextField(blank=True, verbose_name="处理说明"),
                        ),
                        (
                            "evidence_json",
                            models.JSONField(blank=True, default=list, verbose_name="分析证据"),
                        ),
                        (
                            "sort_order",
                            models.PositiveIntegerField(default=0, verbose_name="同级排序"),
                        ),
                        ("decided_at", models.DateTimeField(blank=True, null=True, verbose_name="处理时间")),
                        ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                        ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                        (
                            "batch",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="nodes",
                                to="crawl.analysisbatch",
                                verbose_name="所属分析批次",
                            ),
                        ),
                        (
                            "college",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="analysis_nodes",
                                to="organizations.college",
                                verbose_name="建议所属学院",
                            ),
                        ),
                        (
                            "matched_node",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="analysis_matches",
                                to="ability.capabilitynode",
                                verbose_name="匹配的正式能力节点",
                            ),
                        ),
                        (
                            "parent",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="children",
                                to="crawl.analysisnode",
                                verbose_name="父分析节点",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "AI 分析节点",
                        "verbose_name_plural": "AI 分析节点",
                        "db_table": "analysis_node",
                        "ordering": ["sort_order", "id"],
                        "indexes": [
                            models.Index(
                                fields=["batch", "parent"],
                                name="ana_node_batch_parent_idx",
                            ),
                            models.Index(
                                fields=["batch", "decision_status"],
                                name="ana_node_batch_state_idx",
                            ),
                        ],
                    },
                ),
            ],
        ),
    ]
