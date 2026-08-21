import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("ability", "0006_capabilitynode_organization"),
        ("organizations", "0005_delete_college"),
        ("resources", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CourseTree",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, verbose_name="课程名称")),
                ("course_type", models.CharField(choices=[("theory", "理论"), ("practice", "实训"), ("integrated", "理实一体")], default="integrated", max_length=20, verbose_name="课程类型")),
                ("total_hours", models.PositiveIntegerField(default=0, verbose_name="学时")),
                ("credits", models.DecimalField(decimal_places=1, default=0, max_digits=5, verbose_name="学分")),
                ("source_snapshot", models.JSONField(default=dict, help_text="保存转换时的岗位能力、能力单元和知识点，来源节点删除后仍可追溯。", verbose_name="正式树快照")),
                ("is_published", models.BooleanField(default=False, verbose_name="是否发布")),
                ("published_at", models.DateTimeField(blank=True, null=True, verbose_name="发布时间")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_course_trees", to=settings.AUTH_USER_MODEL, verbose_name="创建人")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="course_trees", to="organizations.organization", verbose_name="所属组织")),
                ("owner", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="owned_course_trees", to=settings.AUTH_USER_MODEL, verbose_name="课程负责人")),
                ("source_ability", models.ForeignKey(blank=True, limit_choices_to={"node_type": "ability"}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="generated_course_trees", to="ability.capabilitynode", verbose_name="来源岗位能力")),
                ("textbook", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="course_trees", to="resources.textbook", verbose_name="对应教材")),
            ],
            options={
                "verbose_name": "课程树",
                "verbose_name_plural": "课程树",
                "db_table": "curriculum_course_tree",
                "ordering": ["-updated_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="CourseTreeNode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("node_type", models.CharField(choices=[("chapter", "章"), ("knowledge", "知识点")], max_length=20, verbose_name="节点类型")),
                ("name", models.CharField(max_length=200, verbose_name="节点名称")),
                ("task_description", models.TextField(blank=True, verbose_name="学习任务描述")),
                ("work_scenario", models.TextField(blank=True, verbose_name="工作情境")),
                ("operation_steps", models.JSONField(blank=True, default=list, verbose_name="操作步骤")),
                ("safety_points", models.JSONField(blank=True, default=list, verbose_name="安全要点")),
                ("resource_links", models.JSONField(blank=True, default=list, verbose_name="教学资源")),
                ("is_edited", models.BooleanField(default=False, verbose_name="是否编辑完成")),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="同级排序")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="children", to="curriculum.coursetreenode", verbose_name="父节点")),
                ("source_node", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="course_tree_nodes", to="ability.capabilitynode", verbose_name="来源正式树节点")),
                ("textbook_node", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="course_tree_nodes", to="resources.textbooknode", verbose_name="对应教材节点")),
                ("tree", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="nodes", to="curriculum.coursetree", verbose_name="所属课程树")),
            ],
            options={
                "verbose_name": "课程树节点",
                "verbose_name_plural": "课程树节点",
                "db_table": "curriculum_course_tree_node",
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="coursetree",
            constraint=models.UniqueConstraint(fields=("organization", "source_ability"), name="uniq_org_source_ability_tree"),
        ),
        migrations.AddIndex(
            model_name="coursetree",
            index=models.Index(fields=["organization", "owner"], name="course_tree_org_owner_idx"),
        ),
        migrations.AddIndex(
            model_name="coursetree",
            index=models.Index(fields=["organization", "is_published"], name="course_tree_publish_idx"),
        ),
        migrations.AddConstraint(
            model_name="coursetreenode",
            constraint=models.UniqueConstraint(fields=("tree", "source_node"), name="uniq_course_tree_source_node"),
        ),
        migrations.AddConstraint(
            model_name="coursetreenode",
            constraint=models.UniqueConstraint(condition=models.Q(("parent__isnull", True)), fields=("tree", "node_type", "name"), name="uniq_course_tree_root_node"),
        ),
        migrations.AddConstraint(
            model_name="coursetreenode",
            constraint=models.UniqueConstraint(condition=models.Q(("parent__isnull", False)), fields=("tree", "parent", "node_type", "name"), name="uniq_course_tree_child_node"),
        ),
        migrations.AddIndex(
            model_name="coursetreenode",
            index=models.Index(fields=["tree", "parent"], name="course_node_parent_idx"),
        ),
        migrations.AddIndex(
            model_name="coursetreenode",
            index=models.Index(fields=["tree", "node_type"], name="course_node_type_idx"),
        ),
    ]
