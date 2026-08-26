"""curriculum 模块对外暴露的接口（跨模块引用统一入口）"""

from .models import CourseTree


def get_visible_course_trees(user):
    """用户可见的课程树（不含发布状态过滤，供试题/资源检索）。

    可见性规则同 views._visible_course_trees：
    - 超级管理员：全部
    - 学院负责人：本学院全部
    - 课程负责人：本学院中自己负责的
    """
    trees = CourseTree.objects.select_related("organization", "owner")
    if user.is_superuser:
        return trees
    profile = getattr(user, "profile", None)
    if not profile or not profile.organization_id:
        return CourseTree.objects.none()
    is_college_manager = bool(profile.role and profile.role.name == "学院负责人")
    if is_college_manager:
        return trees.filter(organization_id=profile.organization_id)
    return trees.filter(organization_id=profile.organization_id, owner=user)


def get_teachable_course_trees(user):
    """用户可见且已发布的课程树（教学安排选课程用）。"""
    return get_visible_course_trees(user).filter(is_published=True).order_by("name", "id")


def create_course_tree(*, organization, name, owner=None, is_published=False, **kwargs):
    """创建或获取课程树（幂等，seed/测试用，走跨模块入口）。"""
    tree, _ = CourseTree.objects.get_or_create(
        organization=organization,
        name=name,
        defaults={"owner": owner, "is_published": is_published, **kwargs},
    )
    return tree
