"""学期计划自动派生：监听教学安排的班级变化，同步学生的学期计划。"""

from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from apps.organizations.models import Student
from apps.teaching.models import TeachingArrangement

from .models import LearningPlan


def _teacher_name(arrangement):
    profile = getattr(arrangement.teacher, "profile", None)
    return profile.real_name if profile and profile.real_name else arrangement.teacher.username


def _sync_students_plans(arrangement, class_ids):
    """为指定班级的学生创建/更新学期计划。"""
    students = Student.objects.filter(class_group_id__in=class_ids)
    for student in students:
        LearningPlan.objects.get_or_create(
            student=student,
            course_tree=arrangement.course_tree,
            plan_type=LearningPlan.PlanType.SEMESTER,
            defaults={
                "name": arrangement.course_tree.name,
                "category": "专业核心",
                "total_hours": arrangement.course_tree.total_hours,
                "teacher": _teacher_name(arrangement),
            },
        )


def _remove_students_plans(arrangement, class_ids):
    """移除指定班级学生的学期计划。"""
    LearningPlan.objects.filter(
        student__class_group_id__in=class_ids,
        course_tree=arrangement.course_tree,
        plan_type=LearningPlan.PlanType.SEMESTER,
    ).delete()


@receiver(m2m_changed, sender=TeachingArrangement.classes.through)
def on_arrangement_classes_changed(sender, instance, action, pk_set, **kwargs):
    if action == "post_add" and pk_set:
        _sync_students_plans(instance, pk_set)
    elif action == "post_remove" and pk_set:
        _remove_students_plans(instance, pk_set)
    elif action == "post_clear":
        LearningPlan.objects.filter(
            course_tree=instance.course_tree,
            plan_type=LearningPlan.PlanType.SEMESTER,
        ).delete()
