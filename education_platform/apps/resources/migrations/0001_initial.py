import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("organizations", "0005_delete_college"),
    ]

    operations = [
        migrations.CreateModel(
            name="Textbook",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, verbose_name="教材名称")),
                ("edition", models.CharField(blank=True, max_length=100, verbose_name="版本")),
                ("publisher", models.CharField(blank=True, max_length=200, verbose_name="出版社")),
                ("isbn", models.CharField(blank=True, max_length=32, verbose_name="ISBN")),
                ("source_file", models.CharField(blank=True, max_length=500, verbose_name="教材文件地址")),
                ("raw_text", models.TextField(blank=True, verbose_name="教材提取文本")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_textbooks", to=settings.AUTH_USER_MODEL, verbose_name="创建人")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="textbooks", to="organizations.organization", verbose_name="所属组织")),
            ],
            options={
                "verbose_name": "教材",
                "verbose_name_plural": "教材",
                "db_table": "resource_textbook",
                "ordering": ["name", "edition", "id"],
            },
        ),
        migrations.CreateModel(
            name="TextbookNode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("node_type", models.CharField(choices=[("chapter", "章"), ("knowledge", "知识点")], max_length=20, verbose_name="节点类型")),
                ("name", models.CharField(max_length=200, verbose_name="节点名称")),
                ("content", models.TextField(blank=True, verbose_name="知识内容")),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="同级排序")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="children", to="resources.textbooknode", verbose_name="父节点")),
                ("textbook", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="nodes", to="resources.textbook", verbose_name="所属教材")),
            ],
            options={
                "verbose_name": "教材知识节点",
                "verbose_name_plural": "教材知识节点",
                "db_table": "resource_textbook_node",
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="textbook",
            constraint=models.UniqueConstraint(fields=("organization", "name", "edition"), name="uniq_org_textbook_edition"),
        ),
        migrations.AddIndex(
            model_name="textbook",
            index=models.Index(fields=["organization", "name"], name="textbook_org_name_idx"),
        ),
        migrations.AddConstraint(
            model_name="textbooknode",
            constraint=models.UniqueConstraint(condition=models.Q(("parent__isnull", True)), fields=("textbook", "node_type", "name"), name="uniq_textbook_root_node"),
        ),
        migrations.AddConstraint(
            model_name="textbooknode",
            constraint=models.UniqueConstraint(condition=models.Q(("parent__isnull", False)), fields=("textbook", "parent", "node_type", "name"), name="uniq_textbook_child_node"),
        ),
        migrations.AddIndex(
            model_name="textbooknode",
            index=models.Index(fields=["textbook", "parent"], name="textbook_node_parent_idx"),
        ),
        migrations.AddIndex(
            model_name="textbooknode",
            index=models.Index(fields=["textbook", "node_type"], name="textbook_node_type_idx"),
        ),
    ]
