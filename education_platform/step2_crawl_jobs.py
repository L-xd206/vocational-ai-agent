"""兼容入口：岗位爬取已迁移至 apps.collection.tasks。"""
from apps.collection.tasks import crawl_single_job

__all__ = ["crawl_single_job"]
