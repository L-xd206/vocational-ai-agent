from django.apps import AppConfig


class CapabilitiesConfig(AppConfig):
    name = "apps.capabilities"
    # 保持既有迁移记录和数据库 app 标签不变。
    label = "ability"
