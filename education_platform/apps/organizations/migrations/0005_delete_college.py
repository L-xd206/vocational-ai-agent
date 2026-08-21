from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0004_merge_colleges_into_organizations"),
        ("accounts", "0002_userprofile_organization"),
        ("ability", "0006_capabilitynode_organization"),
        ("crawl", "0010_analysisnode_organization"),
    ]

    operations = [
        migrations.DeleteModel(
            name="College",
        ),
    ]
