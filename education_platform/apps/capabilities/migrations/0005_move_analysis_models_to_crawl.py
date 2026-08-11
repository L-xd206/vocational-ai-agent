from django.db import migrations


class Migration(migrations.Migration):
    """只移动 Django 模型状态；保留既有分析表及其中的数据。"""

    dependencies = [
        ("ability", "0004_analysisbatch_capabilitynode_analysisnode_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name="AnalysisNode"),
                migrations.DeleteModel(name="AnalysisBatch"),
            ],
        ),
    ]
