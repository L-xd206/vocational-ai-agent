"""预置学习计划/学习记录测试数据（幂等，可重复执行）

用法：python manage.py seed_learning
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.organizations.models import Student
from apps.teaching.models import TeachingArrangement

from apps.learning.models import LearningPlan, LearningRecord
from apps.learning.signals import _sync_students_plans

User = get_user_model()


class Command(BaseCommand):
    help = "预置学习计划、学习记录测试数据（幂等）"

    def handle(self, *args, **options):
        student_user = User.objects.filter(username="student").first()
        if not student_user:
            self.stdout.write("⚠ 缺 student 账号，跳过学习 seed")
            return
        # 关联学生档案（organizations seed 创建了学生但未关联账号）
        student = Student.objects.filter(name="张晨希").first() or Student.objects.first()
        if student is None:
            self.stdout.write("⚠ 无学生档案，跳过学习 seed")
            return
        if student.user_id != student_user.id:
            student.user = student_user
            student.save(update_fields=["user"])
            self.stdout.write(f"已关联学生档案：{student.name}")

        # 手动派生学期计划（教学安排已存在时 m2m signal 不会重复触发）
        for arr in TeachingArrangement.objects.prefetch_related("classes"):
            _sync_students_plans(arr, list(arr.classes.values_list("id", flat=True)))

        # 自主学习计划示例（学期计划由教学安排 signal 自动派生）
        plan, created = LearningPlan.objects.get_or_create(
            student=student,
            name="PLC通信联调专项训练",
            plan_type=LearningPlan.PlanType.SELF,
            defaults={
                "category": "自主学习",
                "total_hours": 28,
                "learned_hours": 6,
                "status": LearningPlan.Status.DOING,
                "progress": 21,
                "deadline": "2026-12-15",
            },
        )
        self.stdout.write(f"{'已创建' if created else '已存在'}自主学习计划：{plan.name}")

        # 学习记录时间线
        records = [
            ("入学", "完成入学能力测评，建立学情基线", "入学"),
            ("掌握机器人基础操作", "完成示教编程课程，单元测验 88 分", "里程碑"),
            ("PLC 编程能力达标", "阶段考核 76 分，PLC 编程维度达标", "里程碑"),
        ]
        for title, desc, tag in records:
            r, created = LearningRecord.objects.get_or_create(
                student=student, title=title,
                defaults={"description": desc, "tag": tag},
            )
            self.stdout.write(f"{'已创建' if created else '已存在'}学习记录：{title}")

        self.stdout.write(self.style.SUCCESS(
            f"seed_learning 完成：{LearningPlan.objects.filter(student=student).count()} 计划，"
            f"{LearningRecord.objects.filter(student=student).count()} 记录"
        ))
