from django.apps import AppConfig


class CrawlConfig(AppConfig):
    name = "apps.collection"
    # 保持既有迁移记录和数据库 app 标签不变。
    label = "crawl"
