from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("curriculum", "0002_alter_coursetree_textbook"),
    ]

    operations = [
        migrations.AddField(
            model_name="coursetree",
            name="ai_generation_error",
            field=models.TextField(blank=True, verbose_name="AI 生成失败原因"),
        ),
        migrations.AddField(
            model_name="coursetree",
            name="ai_generation_status",
            field=models.CharField(
                choices=[
                    ("pending", "待生成"),
                    ("processing", "生成中"),
                    ("ready", "已生成"),
                    ("error", "生成失败"),
                ],
                default="pending",
                max_length=20,
                verbose_name="AI 生成状态",
            ),
        ),
    ]
