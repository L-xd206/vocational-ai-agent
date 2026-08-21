import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("curriculum", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CourseQuestion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("question_type", models.CharField(choices=[("single", "单选题"), ("multiple", "多选题"), ("judgment", "判断题"), ("short", "简答题")], max_length=20, verbose_name="题型")),
                ("stem", models.TextField(verbose_name="题干")),
                ("options", models.JSONField(blank=True, default=list, verbose_name="选项")),
                ("correct_answer", models.JSONField(default=list, verbose_name="正确答案")),
                ("analysis", models.TextField(blank=True, verbose_name="答案解析")),
                ("difficulty", models.CharField(choices=[("easy", "简单"), ("medium", "中等"), ("hard", "困难")], default="medium", max_length=20, verbose_name="难度")),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="排序")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_course_questions", to=settings.AUTH_USER_MODEL, verbose_name="创建人")),
                ("node", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="questions", to="curriculum.coursetreenode", verbose_name="所属知识点")),
            ],
            options={
                "verbose_name": "课程试题",
                "verbose_name_plural": "课程试题",
                "db_table": "teaching_course_question",
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="coursequestion",
            index=models.Index(fields=["node", "question_type"], name="question_node_type_idx"),
        ),
        migrations.AddIndex(
            model_name="coursequestion",
            index=models.Index(fields=["node", "difficulty"], name="question_difficulty_idx"),
        ),
    ]
