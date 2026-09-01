import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.curriculum.models import CourseTree
from apps.organizations.models import Class, Organization, Student
from apps.teaching.models import TeachingArrangement

from .models import LearningPlan, LearningRecord, PlanDeleteLog

User = get_user_model()


class LearningPlanApiTests(TestCase):
    """学习计划：列表统计、新增自主学习、删除（带原因/软删）、学期计划自动派生"""

    def setUp(self):
        self.college = Organization.objects.create(name="智能制造学院", org_type="学院")
        self.major = Organization.objects.create(name="工业机器人技术", org_type="专业", parent=self.college)
        self.cls = Class.objects.create(
            name="机器人2401班", code="CLS-LRN-01", major="工业机器人技术", grade="2024级", org=self.major,
        )
        # 学生（user 关联，用于登录）
        self.student_user = User.objects.create_user(username="stu1", password="edu@123")
        self.student = Student.objects.create(
            name="张同学", student_id="LRN001", major="工业机器人技术", grade="2024级",
            class_group=self.cls, user=self.student_user,
        )
        # 教师 + 课程树 + 教学安排（add 班级时触发 signal 派生学期计划）
        self.teacher = User.objects.create_user(username="teacher", password="edu@123")
        self.tree = CourseTree.objects.create(
            organization=self.college, name="工业机器人技术基础",
            owner=self.teacher, is_published=True, total_hours=64,
        )
        self.arr = TeachingArrangement.objects.create(
            teacher=self.teacher, course_tree=self.tree, semester="2025-2026-1",
        )
        self.arr.classes.add(self.cls)

        self.client = Client()
        self.client.login(username="stu1", password="edu@123")

    def test_unauthenticated(self):
        c = Client()
        self.assertEqual(c.get("/api/learning-plans").status_code, 401)

    def test_semester_plan_auto_derived(self):
        # 教学安排班级 add 后，自动派生学生的学期计划
        plans = LearningPlan.objects.filter(student=self.student)
        self.assertEqual(plans.count(), 1)
        p = plans.get()
        self.assertEqual(p.plan_type, LearningPlan.PlanType.SEMESTER)
        self.assertEqual(p.name, "工业机器人技术基础")
        self.assertEqual(p.total_hours, 64)

    def test_list_and_overview(self):
        r = self.client.get("/api/learning-plans")
        d = r.json()
        self.assertEqual(len(d["plans"]), 1)
        self.assertEqual(d["overview"]["remain_hours"], 64)  # 未开始，剩余 64 学时
        self.assertFalse(d["plans"][0]["can_delete"])  # 学期计划不可删

    def test_create_self_plan(self):
        r = self.client.post("/api/learning-plans", data=json.dumps({
            "name": "PLC通信联调专项训练", "total_hours": 28, "deadline": "2026-12-15",
        }), content_type="application/json")
        self.assertEqual(r.status_code, 201)
        self.assertTrue(LearningPlan.objects.filter(
            student=self.student, plan_type=LearningPlan.PlanType.SELF,
        ).exists())

    def test_delete_self_plan_with_reason(self):
        plan = LearningPlan.objects.create(
            student=self.student, name="自选训练", plan_type=LearningPlan.PlanType.SELF, total_hours=10,
        )
        r = self.client.delete(f"/api/learning-plans/{plan.id}", data=json.dumps({
            "reason": "内容重复",
        }), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(LearningPlan.objects.filter(pk=plan.id).exists())
        self.assertTrue(PlanDeleteLog.objects.filter(plan_name="自选训练", reason="内容重复").exists())

    def test_delete_without_reason_blocked(self):
        plan = LearningPlan.objects.create(
            student=self.student, name="自选训练", plan_type=LearningPlan.PlanType.SELF, total_hours=10,
        )
        r = self.client.delete(f"/api/learning-plans/{plan.id}", data=json.dumps({"reason": ""}), content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_delete_semester_blocked(self):
        semester_plan = LearningPlan.objects.get(student=self.student, plan_type=LearningPlan.PlanType.SEMESTER)
        r = self.client.delete(f"/api/learning-plans/{semester_plan.id}", data=json.dumps({"reason": "x"}), content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertTrue(LearningPlan.objects.filter(pk=semester_plan.id).exists())


class LearningProfileApiTests(TestCase):
    """学习档案：统计 + 学习记录时间线"""

    def setUp(self):
        self.college = Organization.objects.create(name="智能制造学院", org_type="学院")
        self.major = Organization.objects.create(name="工业机器人技术", org_type="专业", parent=self.college)
        self.cls = Class.objects.create(
            name="机器人2401班", code="CLS-PRO-01", major="工业机器人技术", grade="2024级", org=self.major,
        )
        self.student_user = User.objects.create_user(username="stu2", password="edu@123")
        self.student = Student.objects.create(
            name="李同学", student_id="PRO001", major="工业机器人技术", grade="2024级",
            class_group=self.cls, user=self.student_user,
        )
        LearningPlan.objects.create(
            student=self.student, name="训练计划", plan_type=LearningPlan.PlanType.SELF,
            total_hours=20, learned_hours=5,
        )
        LearningRecord.objects.create(student=self.student, title="入学", description="完成入学测评", tag="入学")
        self.client = Client()
        self.client.login(username="stu2", password="edu@123")

    def test_profile(self):
        r = self.client.get("/api/learning-profile")
        d = r.json()
        self.assertEqual(d["stats"]["plan_count"], 1)
        self.assertEqual(d["stats"]["learned_hours"], 5)
        self.assertEqual(d["stats"]["assessment_count"], 0)  # 占位
        self.assertEqual(d["student"]["name"], "李同学")
        self.assertEqual(len(d["records"]), 1)
        self.assertEqual(d["records"][0]["title"], "入学")

    def test_unauthenticated(self):
        c = Client()
        self.assertEqual(c.get("/api/learning-profile").status_code, 401)
