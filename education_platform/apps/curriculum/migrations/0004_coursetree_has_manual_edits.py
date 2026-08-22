from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("curriculum", "0003_coursetree_ai_generation_status_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="coursetree",
            name="has_manual_edits",
            field=models.BooleanField(
                default=False,
                help_text="课程基础信息、任务卡、教学资源或试题被人工修改后置为 True，用于阻止 AI 重新生成时覆盖成果。",
                verbose_name="是否包含人工编辑成果",
            ),
        ),
    ]
