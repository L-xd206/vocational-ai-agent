import hashlib
import re
import unicodedata

from django.db import migrations, models


def _content_fingerprint(text):
    normalized = unicodedata.normalize("NFKC", str(text or "")).casefold()
    normalized = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", normalized)
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def backfill_content_fingerprints(apps, schema_editor):
    JobListing = apps.get_model("crawl", "JobListing")
    for listing in JobListing.objects.only("id", "requirements").iterator():
        listing.content_fingerprint = _content_fingerprint(listing.requirements)
        listing.save(update_fields=["content_fingerprint"])


class Migration(migrations.Migration):
    dependencies = [("crawl", "0007_seed_mohrss_source")]

    operations = [
        migrations.AddField(
            model_name="joblisting",
            name="content_fingerprint",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                max_length=64,
                verbose_name="任职要求内容指纹",
            ),
        ),
        migrations.RunPython(backfill_content_fingerprints, migrations.RunPython.noop),
    ]
