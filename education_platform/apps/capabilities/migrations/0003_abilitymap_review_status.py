from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ability", "0002_abilitymap_generation_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="abilitymap",
            name="review_status",
            field=models.CharField(
                choices=[("pending", "待审核"), ("confirmed", "已确认"), ("rejected", "已退回")],
                default="pending",
                max_length=20,
                verbose_name="审核状态",
            ),
        ),
        migrations.AddField(
            model_name="abilitymap",
            name="review_note",
            field=models.TextField(blank=True, verbose_name="审核意见"),
        ),
        migrations.AddField(
            model_name="abilitymap",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="审核时间"),
        ),
    ]
