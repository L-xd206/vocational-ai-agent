from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ability", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="abilitymap",
            name="generation_status",
            field=models.CharField(default="ready", max_length=20, verbose_name="生成状态"),
        ),
        migrations.AddField(
            model_name="abilitymap",
            name="generation_error",
            field=models.TextField(blank=True, verbose_name="生成错误"),
        ),
    ]
