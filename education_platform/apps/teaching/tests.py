from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.curriculum.models import CourseTree, CourseTreeNode
from apps.organizations.models import Organization
from apps.resources.models import Textbook

from .models import CourseQuestion


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
