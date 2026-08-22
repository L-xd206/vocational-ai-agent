from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("curriculum", "0005_course_publish_change_tracking"),
    ]

    operations = [
        migrations.AddField(
            model_name="coursetreenode",
            name="chapter_content_edited",
            field=models.BooleanField(
                default=False,
                help_text="仅用于章节点，区分学习任务本身是否确认与其下任务卡是否全部完成。",
                verbose_name="学习任务内容是否编辑完成",
            ),
        ),
    ]
