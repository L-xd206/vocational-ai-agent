from django.db import migrations


def merge_colleges_into_organizations(apps, schema_editor):
    College = apps.get_model("organizations", "College")
    Organization = apps.get_model("organizations", "Organization")

    for college in College.objects.order_by("sort_order", "id"):
        organization = college.org
        if organization is None:
            organization = Organization.objects.filter(name=college.name).first()
        if organization is None:
            organization = Organization.objects.create(
                name=college.name,
                org_type="学院",
                sort_order=college.sort_order,
                is_enabled=college.is_enabled,
            )
        college.org = organization
        college.save(update_fields=["org"])


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0003_college_add_org_fk"),
    ]

    operations = [
        migrations.RunPython(
            merge_colleges_into_organizations,
            migrations.RunPython.noop,
        ),
    ]
