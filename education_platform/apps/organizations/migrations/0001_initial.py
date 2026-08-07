from django.db import migrations, models


def create_default_colleges(apps, schema_editor):
    College = apps.get_model("organizations", "College")
    College.objects.bulk_create([
        College(name="智能制造学院", sort_order=10),
        College(name="信息工程学院", sort_order=20),
        College(name="实训中心", sort_order=30),
    ])


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="College",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True, verbose_name="学院名称")),
                ("is_enabled", models.BooleanField(default=True, verbose_name="是否启用")),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="排序")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
            ],
            options={
                "ordering": ["sort_order", "id"],
                "db_table": "organization_college",
                "verbose_name": "学院",
                "verbose_name_plural": "学院",
            },
        ),
        migrations.RunPython(create_default_colleges, migrations.RunPython.noop),
    ]
