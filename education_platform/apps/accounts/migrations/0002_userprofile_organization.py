import django.db.models.deletion
from django.db import migrations, models


def migrate_departments_to_organizations(apps, schema_editor):
    UserProfile = apps.get_model("accounts", "UserProfile")
    Organization = apps.get_model("organizations", "Organization")

    for profile in UserProfile.objects.exclude(dept="").iterator():
        name = profile.dept.strip()
        if not name:
            continue
        organization = Organization.objects.filter(name=name).first()
        if organization is None:
            organization = Organization.objects.create(
                name=name,
                org_type="部门",
            )
        profile.organization = organization
        profile.save(update_fields=["organization"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("organizations", "0004_merge_colleges_into_organizations"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="user_profiles",
                to="organizations.organization",
                verbose_name="所属组织",
            ),
        ),
        migrations.RunPython(
            migrate_departments_to_organizations,
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name="userprofile",
            name="dept",
        ),
    ]
