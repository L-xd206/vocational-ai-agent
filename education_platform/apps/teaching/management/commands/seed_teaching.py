"""预置教学安排测试数据（幂等，可重复执行）

用法：python manage.py seed_teaching
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.curriculum.api import create_course_tree
from apps.curriculum.models import CourseTreeNode
from apps.organizations.api import get_classes_by_college
from apps.organizations.models import Organization
from apps.teaching.models import CourseQuestion, TeachingArrangement

User = get_user_model()


class Command(BaseCommand):
    help = "预置教学安排测试数据（幂等）"

    def handle(self, *args, **options):
        college = Organization.objects.filter(name="智能制造学院", org_type="学院").first()
        course_owner = User.objects.filter(username="course_owner").first()
        teacher_user = User.objects.filter(username="teacher").first()
        if not college or not course_owner or not teacher_user:
            self.stdout.write("⚠ 缺学院/课程负责人/教师账号，跳过教学安排 seed")
            return
        tree = create_course_tree(
            organization=college,
            name="工业机器人技术基础",
            owner=course_owner,
            is_published=True,
            total_hours=64,
            credits=4,
            course_type="integrated",
        )
        # 章节 + 知识点 + 试题（演示数据，供试题库检索）
        chapter, _ = CourseTreeNode.objects.get_or_create(
            tree=tree, node_type="chapter", name="机器人概述",
            defaults={"parent": None},
        )
        point, _ = CourseTreeNode.objects.get_or_create(
            tree=tree, parent=chapter, node_type="knowledge", name="机器人定义与分类",
        )
        CourseQuestion.objects.get_or_create(
            node=point, question_type="single", stem="工业机器人的基本组成部分不包括以下哪项？",
            defaults={"options": ["A. 机械臂", "B. 驱动系统", "C. 操作系统", "D. 控制系统"], "correct_answer": ["C"], "difficulty": "easy"},
        )
        CourseQuestion.objects.get_or_create(
            node=point, question_type="multiple", stem="下列属于工业机器人分类方式的有？",
            defaults={"options": ["A. 按坐标型式", "B. 按驱动方式", "C. 按控制方式", "D. 按自由度"], "correct_answer": ["A", "B", "C", "D"], "difficulty": "medium"},
        )
        classes = list(get_classes_by_college(college.id))
        if not classes:
            self.stdout.write("⚠ 学院下无班级，跳过教学安排")
            return
        arr, created = TeachingArrangement.objects.get_or_create(
            teacher=teacher_user,
            course_tree=tree,
            semester="2025-2026-1",
        )
        arr.classes.set(classes[:2])
        self.stdout.write(self.style.SUCCESS(
            f"seed_teaching 完成：{'已创建' if created else '已存在'}教学安排，{arr.classes.count()} 个班级"
        ))
