import json

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.accounts.models import Role, UserProfile
from apps.curriculum.models import CourseTree, CourseTreeNode
from apps.organizations.models import Class, Organization, Student
from apps.resources.models import Textbook

from .models import CourseQuestion, TeachingArrangement


User = get_user_model()


class CourseQuestionModelTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="智能制造学院", org_type="学院")
        textbook = Textbook.objects.create(organization=self.organization, name="工业机器人技术基础")
        self.owner = User.objects.create_user(username="question_owner", password="edu@123")
        UserProfile.objects.create(user=self.owner, organization=self.organization)
        self.tree = CourseTree.objects.create(
            organization=self.organization,
            textbook=textbook,
            name="工业机器人技术基础",
            owner=self.owner,
        )
        self.chapter = CourseTreeNode.objects.create(
            tree=self.tree,
            node_type="chapter",
            name="机器人基础",
        )
        self.knowledge = CourseTreeNode.objects.create(
            tree=self.tree,
            parent=self.chapter,
            node_type="knowledge",
            name="机器人定义与分类",
        )

    def test_question_can_only_attach_to_knowledge_node(self):
        question = CourseQuestion(
            node=self.chapter,
            question_type="judgment",
            stem="工业机器人属于自动化装备。",
            correct_answer=[True],
        )
        with self.assertRaises(ValidationError):
            question.full_clean()

    def test_choice_question_requires_options(self):
        question = CourseQuestion(
            node=self.knowledge,
            question_type="single",
            stem="以下哪项属于工业机器人？",
            correct_answer=["A"],
        )
        with self.assertRaises(ValidationError):
            question.full_clean()

    def test_course_owner_can_save_questions_for_task_card(self):
        self.tree.is_published = True
        self.tree.save(update_fields=["is_published", "updated_at"])
        self.client.login(username="question_owner", password="edu@123")
        response = self.client.post(
            f"/api/teaching/nodes/{self.knowledge.id}/questions",
            data='''{"questions":[{"question_type":"single","stem":"哪项属于工业机器人？","options":["A. 自动化装备","B. 手工工具"],"correct_answer":["A"],"analysis":"工业机器人属于自动化装备。"}]}''',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CourseQuestion.objects.filter(node=self.knowledge).count(), 1)
        question = CourseQuestion.objects.get(node=self.knowledge)
        self.assertEqual(question.correct_answer, ["A"])
        self.tree.refresh_from_db()
        self.knowledge.refresh_from_db()
        self.assertFalse(self.tree.is_published)
        self.assertTrue(self.tree.has_unpublished_changes)
        self.assertTrue(self.knowledge.changed_since_publish)
        self.assertTrue(response.json()["republish_required"])

    def test_choice_question_requires_continuous_labels_and_valid_answer(self):
        question = CourseQuestion(
            node=self.knowledge,
            question_type="single",
            stem="编号不连续的试题",
            options=["A. 选项一", "C. 选项二"],
            correct_answer=["B"],
        )
        with self.assertRaises(ValidationError):
            question.full_clean()

    def test_subjective_question_requires_answer_or_rubric(self):
        question = CourseQuestion(
            node=self.knowledge,
            question_type="short",
            stem="请说明机器人分类。",
            correct_answer=[],
            analysis="",
        )
        with self.assertRaises(ValidationError):
            question.full_clean()

    def test_other_authenticated_teacher_cannot_read_or_write_questions(self):
        other_teacher = User.objects.create_user(username="other_teacher", password="edu@123")
        UserProfile.objects.create(user=other_teacher, organization=self.organization)
        self.client.login(username="other_teacher", password="edu@123")

        read_response = self.client.get(
            f"/api/teaching/nodes/{self.knowledge.id}/questions"
        )
        write_response = self.client.post(
            f"/api/teaching/nodes/{self.knowledge.id}/questions",
            data='{"questions":[]}',
            content_type="application/json",
        )

        self.assertEqual(read_response.status_code, 403)
        self.assertEqual(write_response.status_code, 403)


class TeachingArrangementApiTests(TestCase):
    """教学安排：课程/班级下拉、列表统计、新增去重、调整班级、成员"""

    def setUp(self):
        self.college = Organization.objects.create(name="智能制造学院", org_type="学院")
        self.major = Organization.objects.create(name="工业机器人技术", org_type="专业", parent=self.college)
        self.cls1 = Class.objects.create(name="机器人2401班", code="CLS-TA-01", major="工业机器人技术", grade="2024级", org=self.major)
        self.cls2 = Class.objects.create(name="机器人2402班", code="CLS-TA-02", major="工业机器人技术", grade="2024级", org=self.major)
        Student.objects.create(name="张同学", student_id="TA001", class_group=self.cls1)
        Student.objects.create(name="李同学", student_id="TA002", class_group=self.cls2)

        self.teacher = User.objects.create_user(username="teacher", password="edu@123")
        role = Role.objects.create(name="课程负责人")
        UserProfile.objects.create(user=self.teacher, role=role, organization=self.college)

        self.published_tree = CourseTree.objects.create(
            organization=self.college, name="工业机器人技术基础",
            owner=self.teacher, is_published=True, total_hours=64, credits=4,
        )
        self.draft_tree = CourseTree.objects.create(
            organization=self.college, name="未发布课程", owner=self.teacher, is_published=False,
        )

        self.client = Client()
        self.client.login(username="teacher", password="edu@123")

    def test_unauthenticated(self):
        c = Client()
        self.assertEqual(c.get("/api/teaching-arrangements").status_code, 401)

    def test_course_options_only_published_own(self):
        r = self.client.get("/api/teaching-arrangements/course-options")
        ids = {c["id"] for c in r.json()["courses"]}
        self.assertIn(self.published_tree.id, ids)
        self.assertNotIn(self.draft_tree.id, ids)  # 未发布不出现

    def test_class_options(self):
        r = self.client.get("/api/teaching-arrangements/class-options")
        self.assertEqual(len(r.json()["classes"]), 2)

    def test_create_and_stats(self):
        r = self.client.post("/api/teaching-arrangements", data=json.dumps({
            "course_tree_id": self.published_tree.id,
            "semester": "2025-2026-1",
            "class_ids": [self.cls1.id, self.cls2.id],
        }), content_type="application/json")
        self.assertEqual(r.status_code, 201)
        d = self.client.get("/api/teaching-arrangements").json()
        self.assertEqual(d["stats"]["course_count"], 1)
        self.assertEqual(d["stats"]["class_count"], 2)
        self.assertEqual(d["stats"]["student_count"], 2)

    def test_create_dedup_merges_classes(self):
        self.client.post("/api/teaching-arrangements", data=json.dumps({
            "course_tree_id": self.published_tree.id, "semester": "2025-2026-1", "class_ids": [self.cls1.id],
        }), content_type="application/json")
        r = self.client.post("/api/teaching-arrangements", data=json.dumps({
            "course_tree_id": self.published_tree.id, "semester": "2025-2026-1", "class_ids": [self.cls2.id],
        }), content_type="application/json")
        self.assertEqual(r.status_code, 200)  # 合并（非新建）
        self.assertEqual(TeachingArrangement.objects.count(), 1)
        self.assertEqual(TeachingArrangement.objects.get().classes.count(), 2)

    def test_create_reject_unpublished(self):
        r = self.client.post("/api/teaching-arrangements", data=json.dumps({
            "course_tree_id": self.draft_tree.id, "semester": "2025-2026-1", "class_ids": [self.cls1.id],
        }), content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_update_classes(self):
        self.client.post("/api/teaching-arrangements", data=json.dumps({
            "course_tree_id": self.published_tree.id, "semester": "2025-2026-1",
            "class_ids": [self.cls1.id, self.cls2.id],
        }), content_type="application/json")
        arr = TeachingArrangement.objects.get()
        r = self.client.patch(f"/api/teaching-arrangements/{arr.id}", data=json.dumps({
            "class_ids": [self.cls1.id],
        }), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        arr.refresh_from_db()
        self.assertEqual(arr.classes.count(), 1)

    def test_update_classes_require_one(self):
        self.client.post("/api/teaching-arrangements", data=json.dumps({
            "course_tree_id": self.published_tree.id, "semester": "2025-2026-1", "class_ids": [self.cls1.id],
        }), content_type="application/json")
        arr = TeachingArrangement.objects.get()
        r = self.client.patch(f"/api/teaching-arrangements/{arr.id}", data=json.dumps({
            "class_ids": [],
        }), content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_members(self):
        self.client.post("/api/teaching-arrangements", data=json.dumps({
            "course_tree_id": self.published_tree.id, "semester": "2025-2026-1", "class_ids": [self.cls1.id],
        }), content_type="application/json")
        arr = TeachingArrangement.objects.get()
        r = self.client.get(f"/api/teaching-arrangements/{arr.id}/members")
        members = r.json()["members"]
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0]["class_name"], "机器人2401班")
        self.assertEqual(len(members[0]["students"]), 1)


class QuestionBankApiTests(TestCase):
    """课程试题检索：跨课程/章节/知识点列表、关键词、题型、课程筛选"""

    def setUp(self):
        self.college = Organization.objects.create(name="智能制造学院", org_type="学院")
        self.teacher = User.objects.create_user(username="teacher", password="edu@123")
        role = Role.objects.create(name="课程负责人")
        UserProfile.objects.create(user=self.teacher, role=role, organization=self.college)
        self.tree = CourseTree.objects.create(
            organization=self.college, name="工业机器人技术基础", owner=self.teacher, is_published=True,
        )
        self.chapter = CourseTreeNode.objects.create(tree=self.tree, node_type="chapter", name="机器人概述")
        self.point = CourseTreeNode.objects.create(
            tree=self.tree, parent=self.chapter, node_type="knowledge", name="机器人定义",
        )
        CourseQuestion.objects.create(
            node=self.point, question_type="single", stem="工业机器人的基本组成部分不包括？",
            options=["A. 机械臂", "B. 驱动系统"], correct_answer=["A"],
        )
        CourseQuestion.objects.create(
            node=self.point, question_type="multiple", stem="机器人的分类方式有？",
            options=["A. 坐标", "B. 驱动"], correct_answer=["A", "B"],
        )
        self.client = Client()
        self.client.login(username="teacher", password="edu@123")

    def test_unauthenticated(self):
        c = Client()
        self.assertEqual(c.get("/api/teaching/questions").status_code, 401)

    def test_list(self):
        r = self.client.get("/api/teaching/questions")
        self.assertEqual(r.json()["total"], 2)

    def test_search_keyword(self):
        r = self.client.get("/api/teaching/questions?keyword=组成部分")
        self.assertEqual(r.json()["total"], 1)

    def test_filter_type(self):
        r = self.client.get("/api/teaching/questions?question_type=multiple")
        self.assertEqual(r.json()["total"], 1)

    def test_filter_course(self):
        r = self.client.get(f"/api/teaching/questions?course_tree_id={self.tree.id}")
        self.assertEqual(r.json()["total"], 2)

    def test_has_path(self):
        r = self.client.get("/api/teaching/questions")
        item = r.json()["questions"][0]
        self.assertIn("工业机器人技术基础", item["path"])
        self.assertIn("机器人概述", item["path"])
