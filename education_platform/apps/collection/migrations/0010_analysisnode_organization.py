import django.db.models.deletion
from django.db import migrations, models


def migrate_analysis_organizations(apps, schema_editor):
    AnalysisNode = apps.get_model("crawl", "AnalysisNode")
    College = apps.get_model("organizations", "College")

    organizations_by_college = {
        college.id: college.org_id
        for college in College.objects.exclude(org_id=None)
    }
    for node in AnalysisNode.objects.exclude(college_id=None).iterator():
        node.organization_id = organizations_by_college.get(node.college_id)
        node.save(update_fields=["organization"])


class Migration(migrations.Migration):
    dependencies = [
        ("crawl", "0009_normalize_analysis_evidence_and_restore_status"),
        ("organizations", "0004_merge_colleges_into_organizations"),
    ]

    operations = [
        migrations.AddField(
            model_name="analysisnode",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="analysis_nodes",
                to="organizations.organization",
                verbose_name="建议所属组织",
            ),
        ),
        migrations.RunPython(
            migrate_analysis_organizations,
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name="analysisnode",
            name="college",
        ),
    ]
