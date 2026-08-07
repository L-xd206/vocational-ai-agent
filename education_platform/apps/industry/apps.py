from django.apps import AppConfig


class IndustryConfig(AppConfig):
    name = "apps.industry"
    # 保持既有迁移记录和数据库 app 标签不变。
    label = "chain"
