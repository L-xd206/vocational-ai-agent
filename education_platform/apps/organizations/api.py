"""organizations 模块对外暴露的接口（跨模块引用统一入口）"""

from .models import College


def get_college_by_name(name):
    """按名称查学院（capabilities 模块在用）"""
    return College.objects.filter(name=name).first()


def get_enabled_colleges():
    """启用的学院列表"""
    return College.objects.filter(is_enabled=True)
