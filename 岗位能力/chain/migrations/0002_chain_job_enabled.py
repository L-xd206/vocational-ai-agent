from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("chain", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="chain",
            name="is_enabled",
            field=models.BooleanField(default=True, verbose_name="是否启用"),
        ),
        migrations.AddField(
            model_name="job",
            name="is_enabled",
            field=models.BooleanField(default=True, verbose_name="是否启用"),
        ),
    ]
