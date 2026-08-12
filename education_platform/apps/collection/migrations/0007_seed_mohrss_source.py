from datetime import timedelta

from django.db import migrations
from django.utils import timezone


def create_mohrss_source(apps, schema_editor):
    """当前仅初始化中国公共招聘网；模型与调度器仍支持多采集源。"""
    CrawlSource = apps.get_model("crawl", "CrawlSource")
    CrawlSource.objects.update_or_create(
        code="mohrss",
        defaults={
            "name": "中国公共招聘网",
            "base_url": "http://job.mohrss.gov.cn",
            "interval_minutes": 1440,
            "is_enabled": True,
            "config_json": {"pages": 3, "timeout": 20},
            "next_run_at": timezone.now() + timedelta(days=1),
        },
    )


def remove_mohrss_source(apps, schema_editor):
    CrawlSource = apps.get_model("crawl", "CrawlSource")
    source = CrawlSource.objects.filter(code="mohrss").first()
    if source and not source.tasks.exists():
        source.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("crawl", "0006_alter_analysisbatch_status_and_more"),
    ]

    operations = [
        migrations.RunPython(create_mohrss_source, remove_mohrss_source),
    ]

