from django.db import migrations, models


def normalize_analysis_evidence(apps, schema_editor):
    AnalysisNode = apps.get_model("crawl", "AnalysisNode")
    for node in AnalysisNode.objects.only("id", "evidence_json").iterator():
        value = node.evidence_json
        if value in (None, ""):
            normalized = []
        elif isinstance(value, list):
            normalized = value
        else:
            normalized = [value]
        if normalized != value:
            node.evidence_json = normalized
            node.save(update_fields=["evidence_json"])


class Migration(migrations.Migration):
    dependencies = [("crawl", "0008_joblisting_content_fingerprint")]

    operations = [
        migrations.RunPython(
            normalize_analysis_evidence,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="analysisnode",
            name="decision_status",
            field=models.CharField(
                choices=[
                    ("not_required", "已存在，无需处理"),
                    ("pending", "等待处理"),
                    ("adopted", "已引用"),
                    ("rejected", "已拒纳"),
                    ("restored", "已恢复到新批次"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
                verbose_name="处理状态",
            ),
        ),
    ]
