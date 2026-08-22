from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("curriculum", "0004_coursetree_has_manual_edits"),
    ]

    operations = [
        migrations.AddField(
            model_name="coursetree",
            name="has_unpublished_changes",
            field=models.BooleanField(
                default=False,
                help_text="课程发布后发生内容修改时置为 True，再次发布成功后清零。",
                verbose_name="是否存在发布后更新",
            ),
        ),
        migrations.AddField(
            model_name="coursetreenode",
            name="changed_since_publish",
            field=models.BooleanField(
                default=False,
                help_text="用于在课程树中标识本节点包含尚未重新发布的修改。",
                verbose_name="发布后是否修改",
            ),
        ),
    ]
