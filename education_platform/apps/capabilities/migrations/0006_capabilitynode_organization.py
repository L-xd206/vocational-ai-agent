import django.db.models.deletion
from django.db import migrations, models


def migrate_capability_organizations(apps, schema_editor):
    CapabilityNode = apps.get_model("ability", "CapabilityNode")
    College = apps.get_model("organizations", "College")

    organizations_by_college = {
        college.id: college.org_id
        for college in College.objects.exclude(org_id=None)
    }
    for node in CapabilityNode.objects.exclude(college_id=None).iterator():
        node.organization_id = organizations_by_college.get(node.college_id)
        node.save(update_fields=["organization"])


class Migration(migrations.Migration):
    dependencies = [
        ("ability", "0005_move_analysis_models_to_crawl"),
        ("organizations", "0004_merge_colleges_into_organizations"),
    ]

    operations = [
        migrations.AddField(
            model_name="capabilitynode",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="capability_nodes",
                to="organizations.organization",
                verbose_name="所属组织",
            ),
        ),
        migrations.RunPython(
            migrate_capability_organizations,
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name="capabilitynode",
            name="college",
        ),
    ]
