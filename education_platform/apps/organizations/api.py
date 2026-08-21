"""organizations 模块对外暴露的接口（跨模块引用统一入口）"""

from .models import Organization


def get_college_by_name(name):
    """兼容旧调用：按名称从组织机构中查学院。"""
    return Organization.objects.filter(name=name, org_type="学院").first()


def get_enabled_colleges():
    """兼容旧调用：返回启用的学院类型组织。"""
    return Organization.objects.filter(org_type="学院", is_enabled=True)
