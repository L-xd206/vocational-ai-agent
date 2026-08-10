"""招聘采集结果的标准化、去重与保存服务。"""

import hashlib

from .models import JobListing


def build_listing_fingerprint(item):
    """根据稳定字段生成 SHA-256 指纹，用于跨批次去重。"""
    parts = [
        item.get("title", ""),
        item.get("company", ""),
        item.get("city", ""),
        item.get("source_url", ""),
        str(item.get("requirements", ""))[:200],
    ]
    raw = "|".join(str(value or "").strip().casefold() for value in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def save_crawl_result(task, item):
    """保存或更新一条招聘信息，返回 (记录, 是否首次创建)。"""
    fingerprint = build_listing_fingerprint(item)
    defaults = {
        "task": task,
        "title": item.get("title", ""),
        "company": item.get("company", ""),
        "city": item.get("city", ""),
        "salary": item.get("salary", ""),
        "education": item.get("education", ""),
        "requirements": item.get("requirements", ""),
        "headcount": item.get("headcount", ""),
        "post_date": item.get("date", item.get("post_date", "")),
        "source": item.get("source", ""),
        "source_url": item.get("source_url", ""),
        "raw_json": item,
    }
    listing, created = JobListing.objects.update_or_create(
        job=task.job,
        crawl_source=task.source,
        fingerprint=fingerprint,
        defaults=defaults,
    )
    return listing, created
