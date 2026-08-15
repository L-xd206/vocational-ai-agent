"""accounts 模块对外暴露的接口（跨模块引用统一入口）"""

from .models import Role


def get_role_by_id(role_id):
    """按 id 查角色（notifications 受众等跨模块引用用）"""
    return Role.objects.filter(pk=role_id).first()


def get_enabled_roles():
    """启用的角色列表"""
    return Role.objects.filter(is_enabled=True)
